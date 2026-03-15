"""
automations/monthly_report.py
==============================
Genera reporte mensual P&L de MORAES y lo envia por Email (PDF) + Telegram.

Contenido:
  - P&L del mes (ventas, gastos, ganancia, margen)
  - Comparativa vs mes anterior (delta %)
  - Acumulado YTD (enero 1 -> ultimo dia del mes reportado)
  - Rentabilidad por SKU desde "Modelo Unitario Rentabilidad - Amazon"
  - Inventario critico al cierre del mes
  - Top 5 productos del mes

Uso:
    python automations/monthly_report.py                    # mes anterior
    python automations/monthly_report.py --test             # datos ficticios
    python automations/monthly_report.py --month 2026-02    # mes especifico (YYYY-MM)
    python automations/monthly_report.py --no-inventory     # sin consulta SP-API

Automatizacion (Windows Task Scheduler):
    Programa   : C:/Python314/python.exe
    Argumentos : automations/monthly_report.py
    Iniciar en : C:/Users/Usuario/Desktop/Dashboard_Moraes
    Frecuencia : Mensual, dia 1 de cada mes, 8:00 AM
"""

import os
import sys
import argparse
import calendar
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from io import BytesIO

import requests
import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from utils.sheets_client import get_worksheet
from utils.notifier import send_telegram

load_dotenv()

# -----------------------------------------------------------------------------
# CONFIGURACION
# -----------------------------------------------------------------------------

BOGOTA_TZ    = ZoneInfo("America/Bogota")
SHEET_VENTAS = "Ventas Amazon"
SHEET_GASTOS = "Gastos Amazon"
SHEET_MODELO = "Modelo Unitario Rentabilidad - Amazon"

INVENTORY_THRESHOLD = 10   # unidades: stock critico al cierre
HEADER_ROW_IDX      = 2    # fila 3 (0-based) tiene headers en Ventas Amazon

TELEGRAM_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID")
GMAIL_USER        = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo",  6: "Junio",   7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "..", "monthly_report_log.txt"),
            encoding="utf-8"
        ),
    ],
)
log = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# LECTURA DE DATOS
# -----------------------------------------------------------------------------

def load_ventas_amazon() -> pd.DataFrame:
    """
    Carga la hoja 'Ventas Amazon'.
    Estructura: fila 1=titulo, fila 2=vacia, fila 3=headers, fila 4+=datos.
    """
    ws   = get_worksheet(SHEET_VENTAS)
    data = ws.get_all_values()
    if len(data) <= HEADER_ROW_IDX + 1:
        return pd.DataFrame()
    headers = data[HEADER_ROW_IDX]
    rows    = data[HEADER_ROW_IDX + 1:]
    df = pd.DataFrame(rows, columns=headers)
    df = df[df["Order ID"].str.strip() != ""]
    df["Fecha"]              = pd.to_datetime(df["Fecha"], errors="coerce")
    df["Ingreso Total (USD)"] = pd.to_numeric(df["Ingreso Total (USD)"], errors="coerce").fillna(0)
    df["Cantidad"]            = pd.to_numeric(df["Cantidad"], errors="coerce").fillna(0)
    return df


def load_gastos_amazon() -> pd.DataFrame:
    """
    Carga la hoja 'Gastos Amazon'.
    Estructura: fila 1=titulo, fila 2=headers, fila 3+=datos.
    """
    GASTOS_HDR = 1
    try:
        ws   = get_worksheet(SHEET_GASTOS)
        data = ws.get_all_values()
        if len(data) <= GASTOS_HDR + 1:
            return pd.DataFrame()
        headers = data[GASTOS_HDR]
        rows    = data[GASTOS_HDR + 1:]
        df = pd.DataFrame(rows, columns=headers)

        id_col = headers[0]
        df = df[df[id_col].str.strip() != ""]

        monto_col = next((c for c in df.columns if "monto" in c.lower()), None)
        if monto_col:
            df[monto_col] = pd.to_numeric(
                df[monto_col].astype(str).str.replace("$", "").str.replace(",", ""),
                errors="coerce"
            ).fillna(0)

        fecha_col = next((c for c in df.columns if "fecha" in c.lower()), None)
        if fecha_col:
            df[fecha_col] = pd.to_datetime(df[fecha_col], errors="coerce")

        return df
    except Exception as e:
        log.warning(f"No se pudo cargar '{SHEET_GASTOS}': {e}")
        return pd.DataFrame()


def load_rentabilidad_sku() -> list[dict]:
    """
    Lee 'Modelo Unitario Rentabilidad - Amazon' y devuelve lista de dicts
    con las metricas reales por SKU (columnas N-R del sheet).
    Fila 1=titulo, Fila 2=headers, Fila 3+=datos.
    """
    try:
        ws   = get_worksheet(SHEET_MODELO)
        data = ws.get_all_values()
        if len(data) < 3:
            log.warning(f"Hoja '{SHEET_MODELO}' vacia o sin datos.")
            return []

        headers = data[1]   # fila 2 = headers
        rows    = data[2:]  # fila 3+ = datos

        idx = {h.strip(): i for i, h in enumerate(headers)}
        col_prod    = idx.get("Producto", 0)
        col_sku     = idx.get("Amazon SKU", 1)
        col_metodo  = idx.get("Metodo de venta", 2)
        col_precio  = idx.get("Precio Venta REAL", None)
        col_ganancia = idx.get("Ganancias REAL", None)
        col_margen  = idx.get("MARGIN REAL", None)
        col_roi     = idx.get("ROI REAL", None)
        col_uds     = idx.get("Unidades vendidas", None)
        col_periodo = idx.get("Periodo", None)

        def _num(row, col):
            if col is None or col >= len(row):
                return 0.0
            try:
                return float(str(row[col]).replace("$", "").replace("%", "").replace(",", "").strip())
            except (ValueError, AttributeError):
                return 0.0

        result = []
        for row in rows:
            if not row or not row[col_prod].strip():
                continue
            producto = row[col_prod].strip()
            sku      = row[col_sku].strip()  if len(row) > col_sku else ""
            metodo   = row[col_metodo].strip() if len(row) > col_metodo else ""
            periodo  = row[col_periodo].strip() if col_periodo and len(row) > col_periodo else ""

            precio   = _num(row, col_precio)
            ganancia = _num(row, col_ganancia)
            margen   = _num(row, col_margen)
            roi      = _num(row, col_roi)
            uds      = int(_num(row, col_uds))

            # Solo incluir filas con datos reales calculados
            if precio == 0 and ganancia == 0:
                continue

            result.append({
                "producto": producto,
                "sku":      sku,
                "metodo":   metodo,
                "precio":   precio,
                "ganancia": ganancia,
                "margen":   margen,
                "roi":      roi,
                "uds":      uds,
                "periodo":  periodo,
            })

        log.info(f"Rentabilidad SKU cargada: {len(result)} productos")
        return sorted(result, key=lambda x: x["ganancia"], reverse=True)
    except Exception as e:
        log.warning(f"No se pudo cargar '{SHEET_MODELO}': {e}")
        return []


def get_inventory_snapshot(threshold: int = INVENTORY_THRESHOLD) -> tuple[list[dict], list[dict]]:
    """
    Consulta inventario FBA via SP-API.
    Retorna (todos_los_items, items_criticos_bajo_threshold).
    En caso de error retorna ([], []).
    """
    try:
        from sp_api.api import Inventories
        from utils.amazon_client import CREDENTIALS, MARKETPLACE

        log.info("Consultando inventario FBA para snapshot de cierre de mes...")
        api = Inventories(credentials=CREDENTIALS, marketplace=MARKETPLACE)
        resp = api.get_inventory_summary_marketplace()
        summaries = resp.payload if isinstance(resp.payload, list) else resp.payload.get("inventories", [])

        items = []
        for item in summaries:
            qty = item.get("fulfillableQuantity", 0) or item.get("totalQuantity", 0) or 0
            items.append({
                "sku":         item.get("sellerSku", ""),
                "asin":        item.get("asin", ""),
                "nombre":      item.get("productName", item.get("sellerSku", "")),
                "disponible":  int(qty),
                "en_transito": item.get("inboundReceivingQuantity", 0) or 0,
            })

        criticos = [i for i in items if i["disponible"] < threshold]
        log.info(f"Inventario: {len(items)} SKUs | {len(criticos)} criticos (< {threshold} uds)")
        return items, criticos
    except ImportError:
        log.warning("sp_api no instalado. Saltando snapshot de inventario.")
        return [], []
    except Exception as e:
        log.warning(f"No se pudo obtener inventario FBA: {e}")
        return [], []

# -----------------------------------------------------------------------------
# RANGOS DE FECHAS
# -----------------------------------------------------------------------------

def get_month_range(reference_date: datetime = None) -> tuple[datetime, datetime]:
    """
    Devuelve (primer_dia, ultimo_dia) del MES ANTERIOR al reference_date.
    Si reference_date es None usa hoy.
    """
    if reference_date is None:
        reference_date = datetime.now(BOGOTA_TZ)
    first_this_month = reference_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_prev        = first_this_month - timedelta(days=1)
    first_prev       = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_prev        = last_prev.replace(hour=23, minute=59, second=59, microsecond=0)
    return first_prev, last_prev


def get_ytd_range(up_to: datetime) -> tuple[datetime, datetime]:
    """
    Devuelve (1 enero del año de up_to, ultimo dia de up_to normalizado a fin de dia).
    """
    start = up_to.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    end   = up_to.replace(hour=23, minute=59, second=59, microsecond=0)
    return start, end


def filter_by_range(df: pd.DataFrame, fecha_col: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Filtra DataFrame por rango de fechas, manejando tz-naive vs tz-aware."""
    if df.empty or fecha_col not in df.columns:
        return pd.DataFrame()
    start_naive = pd.Timestamp(start).tz_convert(None) if pd.Timestamp(start).tzinfo else pd.Timestamp(start)
    end_naive   = pd.Timestamp(end).tz_convert(None)   if pd.Timestamp(end).tzinfo   else pd.Timestamp(end)
    col  = pd.to_datetime(df[fecha_col], errors="coerce").dt.tz_localize(None)
    mask = (col >= start_naive) & (col <= end_naive)
    return df[mask].copy()

# -----------------------------------------------------------------------------
# CALCULOS
# -----------------------------------------------------------------------------

def calc_metrics(df_ventas: pd.DataFrame, df_gastos: pd.DataFrame) -> dict:
    """Calcula metricas P&L del periodo dado."""
    if not df_ventas.empty:
        df_sales   = df_ventas[~df_ventas["Order ID"].str.startswith("REF-", na=False)]
        df_refunds = df_ventas[df_ventas["Order ID"].str.startswith("REF-", na=False)]
    else:
        df_sales = df_refunds = pd.DataFrame()

    total_bruto       = df_sales["Ingreso Total (USD)"].sum()   if not df_sales.empty   else 0
    total_devoluciones = df_refunds["Ingreso Total (USD)"].sum() if not df_refunds.empty else 0
    total_ventas      = total_bruto + total_devoluciones

    total_unidades = int(df_sales["Cantidad"].sum()) if not df_sales.empty else 0
    num_ordenes    = len(df_sales)                   if not df_sales.empty else 0
    ticket_prom    = total_bruto / num_ordenes        if num_ordenes > 0   else 0

    monto_col = None
    if not df_gastos.empty:
        monto_col = next((c for c in df_gastos.columns if "monto" in c.lower()), None)
    total_gastos = abs(df_gastos[monto_col].sum()) if monto_col and not df_gastos.empty else 0

    ganancia = total_ventas - total_gastos
    margen   = (ganancia / total_ventas * 100) if total_ventas > 0 else 0

    top_productos = []
    if not df_sales.empty and "Producto" in df_sales.columns:
        top_productos = (
            df_sales.groupby("Producto")["Ingreso Total (USD)"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
            .reset_index()
            .values.tolist()
        )

    return {
        "total_ventas":       total_ventas,
        "total_ventas_bruto": total_bruto,
        "total_devoluciones": abs(total_devoluciones),
        "total_unidades":     total_unidades,
        "num_ordenes":        num_ordenes,
        "ticket_promedio":    ticket_prom,
        "total_gastos":       total_gastos,
        "ganancia":           ganancia,
        "margen":             margen,
        "top_productos":      top_productos,
    }


def _delta(curr: float, prev: float) -> float:
    if prev == 0:
        return 100.0 if curr > 0 else 0.0
    return (curr - prev) / abs(prev) * 100

# -----------------------------------------------------------------------------
# GENERACION DEL PDF
# -----------------------------------------------------------------------------

ORANGE = (228, 121, 17)
DARK   = (30, 30, 30)
GREY   = (80, 80, 80)
LGREY  = (150, 150, 150)
GREEN  = (0, 150, 0)
RED    = (200, 0, 0)
WHITE  = (255, 255, 255)


class ReporteMensualPDF(FPDF):

    def header(self):
        self.set_fill_color(*ORANGE)
        self.rect(0, 0, 210, 18, "F")
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 14)
        self.set_y(4)
        self.cell(0, 10, "MORAES LEATHER - Reporte Mensual P&L", align="C")
        self.set_text_color(0, 0, 0)
        self.ln(14)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*LGREY)
        ts = datetime.now(ZoneInfo("America/Bogota")).strftime("%d/%m/%Y %H:%M")
        self.cell(0, 10, f"Generado automaticamente el {ts} (Bogota) | Pagina {self.page_no()}", align="C")

    def section_title(self, title: str):
        self.set_fill_color(245, 245, 245)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, f"  {title}", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def metric_row(self, label: str, value: str, highlight: bool = False):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*GREY)
        self.cell(110, 7, f"  {label}")
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*ORANGE if highlight else DARK)
        self.cell(0, 7, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)

    def delta_row(self, label: str, value: str, delta: float, invert: bool = False):
        """
        invert=True: delta negativo es bueno (ej. reduccion de gastos).
        """
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*GREY)
        self.cell(110, 7, f"  {label}")
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*DARK)
        self.cell(40, 7, value)

        good  = delta > 0 if not invert else delta < 0
        bad   = delta < 0 if not invert else delta > 0
        color = GREEN if good else (RED if bad else (100, 100, 100))
        sign  = "+" if delta > 0 else ""
        self.set_text_color(*color)
        self.set_font("Helvetica", "I", 9)
        self.cell(0, 7, f"{sign}{delta:.1f}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)

    def comparison_table(self, items: list[tuple]):
        """
        items: [(label, curr_val, prev_val, is_currency), ...]
        Dibuja tabla de comparacion 4 columnas.
        """
        # Header
        self.set_fill_color(*ORANGE)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 9)
        self.cell(60, 7, "  Metrica",    fill=True)
        self.cell(40, 7, "Este mes",     fill=True, align="C")
        self.cell(40, 7, "Mes anterior", fill=True, align="C")
        self.cell(0,  7, "Delta",        fill=True, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)

        for i, (label, curr, prev, is_currency) in enumerate(items):
            bg = (252, 252, 252) if i % 2 == 0 else (245, 245, 245)
            self.set_fill_color(*bg)
            curr_str = f"${curr:,.2f}" if is_currency else str(int(curr))
            prev_str = f"${prev:,.2f}" if is_currency else str(int(prev))
            d = _delta(curr, prev)
            color = GREEN if d > 0 else (RED if d < 0 else (100, 100, 100))
            sign  = "+" if d > 0 else ""

            self.set_font("Helvetica", "", 9)
            self.set_text_color(*GREY)
            self.cell(60, 7, f"  {label}", fill=True)
            self.set_text_color(*DARK)
            self.set_font("Helvetica", "B", 9)
            self.cell(40, 7, curr_str, fill=True, align="C")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(100, 100, 100)
            self.cell(40, 7, prev_str, fill=True, align="C")
            self.set_text_color(*color)
            self.set_font("Helvetica", "B", 9)
            self.cell(0, 7, f"{sign}{d:.1f}%", fill=True, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_text_color(0, 0, 0)
        self.ln(4)

    def sku_table(self, skus: list[dict]):
        """Tabla de rentabilidad por SKU."""
        if not skus:
            self.set_font("Helvetica", "I", 9)
            self.set_text_color(*LGREY)
            self.cell(0, 7, "  Sin datos del modelo de rentabilidad.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_text_color(0, 0, 0)
            return

        # Header
        self.set_fill_color(*ORANGE)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 8)
        self.cell(42, 7, "  Producto",    fill=True)
        self.cell(14, 7, "Metodo",        fill=True, align="C")
        self.cell(22, 7, "P. Venta",      fill=True, align="C")
        self.cell(22, 7, "Ganancia/ud",   fill=True, align="C")
        self.cell(20, 7, "Margen",        fill=True, align="C")
        self.cell(18, 7, "ROI",           fill=True, align="C")
        self.cell(0,  7, "Uds",           fill=True, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)

        for i, s in enumerate(skus):
            bg = (252, 252, 252) if i % 2 == 0 else (245, 245, 245)
            self.set_fill_color(*bg)
            nombre = str(s["producto"])[:28] + "..." if len(str(s["producto"])) > 28 else str(s["producto"])
            margen_color = GREEN if s["margen"] >= 20 else (RED if s["margen"] < 10 else DARK)

            self.set_font("Helvetica", "", 8)
            self.set_text_color(*GREY)
            self.cell(42, 7, f"  {nombre}", fill=True)
            self.set_text_color(*DARK)
            self.cell(14, 7, s["metodo"][:5], fill=True, align="C")
            self.set_font("Helvetica", "B", 8)
            self.cell(22, 7, f"${s['precio']:.2f}",   fill=True, align="C")
            self.cell(22, 7, f"${s['ganancia']:.2f}", fill=True, align="C")
            self.set_text_color(*margen_color)
            self.cell(20, 7, f"{s['margen']:.1f}%",   fill=True, align="C")
            self.set_text_color(*DARK)
            self.cell(18, 7, f"{s['roi']:.1f}%",      fill=True, align="C")
            self.cell(0,  7, str(s["uds"]),            fill=True, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_text_color(0, 0, 0)
        self.ln(3)

    def inventory_table(self, criticos: list[dict]):
        """Tabla de inventario critico."""
        if not criticos:
            self.set_font("Helvetica", "I", 9)
            self.set_text_color(0, 150, 0)
            self.cell(0, 7, "  Todo el inventario FBA esta por encima del umbral.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_text_color(0, 0, 0)
            return

        # Header
        self.set_fill_color(*RED)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 9)
        self.cell(50, 7, "  SKU",         fill=True)
        self.cell(70, 7, "Producto",      fill=True)
        self.cell(30, 7, "Disponible",    fill=True, align="C")
        self.cell(0,  7, "En Transito",   fill=True, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)

        for i, item in enumerate(criticos):
            bg = (255, 245, 245) if i % 2 == 0 else (252, 235, 235)
            self.set_fill_color(*bg)
            nombre = str(item["nombre"])[:42] + "..." if len(str(item["nombre"])) > 42 else str(item["nombre"])
            disp   = item["disponible"]
            qty_color = (200, 0, 0) if disp == 0 else (200, 100, 0)

            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*DARK)
            self.cell(50, 7, f"  {item['sku']}", fill=True)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*GREY)
            self.cell(70, 7, nombre, fill=True)
            self.set_text_color(*qty_color)
            self.set_font("Helvetica", "B", 9)
            self.cell(30, 7, str(disp), fill=True, align="C")
            self.set_text_color(*DARK)
            self.set_font("Helvetica", "", 9)
            self.cell(0, 7, str(item.get("en_transito", 0)), fill=True, align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_text_color(0, 0, 0)
        self.ln(3)


def generate_pdf(
    mes_start:    datetime,
    mes_end:      datetime,
    metrics:      dict,
    metrics_prev: dict,
    metrics_ytd:  dict,
    sku_data:     list[dict],
    inv_criticos: list[dict],
    inv_disponible: bool = True,
) -> bytes:
    """Genera el PDF del reporte mensual y devuelve bytes."""
    pdf = ReporteMensualPDF()
    pdf.add_page()

    mes_label  = f"{MESES_ES[mes_start.month]} {mes_start.year}"
    prev_label = _prev_month_label(mes_start)

    # -- Encabezado de periodo ------------------------------------------------
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*LGREY)
    pdf.cell(0, 6, f"Periodo: {mes_start.strftime('%d/%m/%Y')} al {mes_end.strftime('%d/%m/%Y')}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    # -- 1. P&L del mes -------------------------------------------------------
    pdf.section_title(f"1. P&L -- {mes_label}")
    d_ventas   = _delta(metrics["total_ventas"],   metrics_prev["total_ventas"])
    d_gastos   = _delta(metrics["total_gastos"],   metrics_prev["total_gastos"])
    d_ganancia = _delta(metrics["ganancia"],        metrics_prev["ganancia"])
    d_uds      = _delta(metrics["total_unidades"], metrics_prev["total_unidades"])

    pdf.delta_row("Ingresos Netos (USD)",   f"${metrics['total_ventas']:.2f}",   d_ventas)
    pdf.metric_row("  Ventas Brutas",       f"${metrics['total_ventas_bruto']:.2f}")
    if metrics["total_devoluciones"] > 0:
        pdf.metric_row("  Devoluciones",    f"-${metrics['total_devoluciones']:.2f}")
    pdf.delta_row("Total Gastos (USD)",     f"${metrics['total_gastos']:.2f}",   d_gastos, invert=True)
    pdf.delta_row("Ganancia Neta (USD)",    f"${metrics['ganancia']:.2f}",       d_ganancia)
    pdf.metric_row("Margen de Ganancia",    f"{metrics['margen']:.1f}%",         highlight=True)
    pdf.delta_row("Unidades Vendidas",      str(metrics["total_unidades"]),      d_uds)
    pdf.metric_row("Ordenes",               str(metrics["num_ordenes"]))
    pdf.metric_row("Ticket Promedio",       f"${metrics['ticket_promedio']:.2f}")
    pdf.ln(4)

    # -- 2. Comparativa vs mes anterior ---------------------------------------
    pdf.section_title(f"2. Comparativa: {mes_label} vs {prev_label}")
    cmp_items = [
        ("Ventas Netas",     metrics["total_ventas"],   metrics_prev["total_ventas"],   True),
        ("Gastos",           metrics["total_gastos"],   metrics_prev["total_gastos"],   True),
        ("Ganancia Neta",    metrics["ganancia"],       metrics_prev["ganancia"],       True),
        ("Margen (%)",       metrics["margen"],         metrics_prev["margen"],         False),
        ("Unidades",         metrics["total_unidades"], metrics_prev["total_unidades"], False),
        ("Ticket Promedio",  metrics["ticket_promedio"],metrics_prev["ticket_promedio"],True),
    ]
    pdf.comparison_table(cmp_items)

    # -- 3. Acumulado YTD -----------------------------------------------------
    pdf.section_title(f"3. Acumulado YTD {mes_start.year} (Ene 1 -> {mes_end.strftime('%d/%m')})")
    pdf.metric_row("Ingresos Netos YTD",  f"${metrics_ytd['total_ventas']:.2f}")
    pdf.metric_row("Gastos YTD",          f"${metrics_ytd['total_gastos']:.2f}")
    pdf.metric_row("Ganancia Neta YTD",   f"${metrics_ytd['ganancia']:.2f}", highlight=True)
    pdf.metric_row("Margen Promedio YTD", f"{metrics_ytd['margen']:.1f}%")
    pdf.metric_row("Unidades YTD",        str(metrics_ytd["total_unidades"]))
    pdf.metric_row("Ordenes YTD",         str(metrics_ytd["num_ordenes"]))
    pdf.ln(4)

    # -- 4. Top 5 productos del mes -------------------------------------------
    pdf.section_title(f"4. Top Productos -- {mes_label}")
    if metrics["top_productos"]:
        pdf.set_fill_color(*ORANGE)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(130, 7, "  Producto", fill=True)
        pdf.cell(0,   7, "Ingresos",   fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        for i, (prod, ing) in enumerate(metrics["top_productos"]):
            pdf.set_fill_color(252, 252, 252) if i % 2 == 0 else pdf.set_fill_color(245, 245, 245)
            nombre = str(prod)[:62] + "..." if len(str(prod)) > 62 else str(prod)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*GREY)
            pdf.cell(130, 7, f"  {nombre}", fill=True)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*DARK)
            pdf.cell(0, 7, f"${ing:.2f}", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*LGREY)
        pdf.cell(0, 7, "  Sin ventas registradas en el mes.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # -- 5. Rentabilidad por SKU ---------------------------------------------
    pdf.add_page()
    pdf.section_title("5. Rentabilidad por SKU (Modelo Unitario Real)")
    if sku_data:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*LGREY)
        periodo_sku = sku_data[0].get("periodo", "")
        if periodo_sku:
            pdf.cell(0, 5, f"  Periodo del modelo: {periodo_sku}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
    pdf.sku_table(sku_data)

    # -- 6. Inventario critico al cierre -------------------------------------
    if inv_disponible:
        pdf.section_title(f"6. Inventario Critico al Cierre (umbral: < {INVENTORY_THRESHOLD} uds)")
        pdf.inventory_table(inv_criticos)
    else:
        pdf.section_title("6. Inventario Critico al Cierre")
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*LGREY)
        pdf.cell(0, 7, "  Consulta SP-API omitida (usa --no-inventory para desactivar).",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    return bytes(pdf.output())


def _prev_month_label(mes_start: datetime) -> str:
    """Devuelve el nombre del mes anterior al mes_start, ej. 'Enero 2026'."""
    if mes_start.month == 1:
        return f"{MESES_ES[12]} {mes_start.year - 1}"
    return f"{MESES_ES[mes_start.month - 1]} {mes_start.year}"

# -----------------------------------------------------------------------------
# NOTIFICACIONES
# -----------------------------------------------------------------------------

def send_telegram_summary(
    mes_label:    str,
    metrics:      dict,
    metrics_prev: dict,
    metrics_ytd:  dict,
    inv_criticos: list[dict],
):
    d_ventas   = _delta(metrics["total_ventas"],  metrics_prev["total_ventas"])
    d_ganancia = _delta(metrics["ganancia"],       metrics_prev["ganancia"])
    d_uds      = _delta(metrics["total_unidades"], metrics_prev["total_unidades"])

    def _sign(v): return "+" if v >= 0 else ""

    inv_lines = ""
    if inv_criticos:
        criticos_txt = "\n".join(
            f"  ⚠️ {i['sku']}: {i['disponible']} uds" for i in inv_criticos[:5]
        )
        inv_lines = f"\n\n🔴 <b>Inventario critico ({len(inv_criticos)} SKU(s)):</b>\n{criticos_txt}"

    msg = (
        f"<b>MORAES -- Reporte Mensual P&L</b>\n"
        f"<i>{mes_label}</i>\n"
        f"---------------------\n"
        f"💰 Ventas:   <b>${metrics['total_ventas']:.2f}</b>  ({_sign(d_ventas)}{d_ventas:.1f}% vs mes ant.)\n"
        f"💸 Gastos:   <b>${metrics['total_gastos']:.2f}</b>\n"
        f"✅ Ganancia: <b>${metrics['ganancia']:.2f}</b>  ({_sign(d_ganancia)}{d_ganancia:.1f}%)\n"
        f"📊 Margen:   <b>{metrics['margen']:.1f}%</b>\n"
        f"📦 Uds:      <b>{metrics['total_unidades']}</b>  ({_sign(d_uds)}{d_uds:.1f}%)\n"
        f"---------------------\n"
        f"📅 <b>YTD {mes_label.split()[-1]}</b>\n"
        f"   Ventas:  ${metrics_ytd['total_ventas']:.2f}\n"
        f"   Ganancia: ${metrics_ytd['ganancia']:.2f}  ({metrics_ytd['margen']:.1f}%)"
        f"{inv_lines}\n\n"
        f"PDF completo enviado al correo."
    )

    send_telegram(msg)


def send_email_with_pdf(pdf_bytes: bytes, mes_label: str, metrics: dict, metrics_ytd: dict):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        log.warning("Gmail no configurado.")
        return

    filename = f"MORAES_PL_{mes_label.replace(' ', '_')}.pdf"
    subject  = f"MORAES -- Reporte Mensual P&L: {mes_label}"

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = GMAIL_USER

    body = MIMEText(f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px">
    <h2 style="color:#e47911">MORAES Leather -- Reporte Mensual P&L</h2>
    <h3 style="color:#333">{mes_label}</h3>
    <table style="border-collapse:collapse;margin-bottom:16px">
        <tr><td style="padding:5px 14px;color:#666">Ventas Netas</td>
            <td style="padding:5px;font-weight:bold">${metrics['total_ventas']:.2f} USD</td></tr>
        <tr style="background:#f9f9f9"><td style="padding:5px 14px;color:#666">Gastos</td>
            <td style="padding:5px;font-weight:bold">${metrics['total_gastos']:.2f} USD</td></tr>
        <tr><td style="padding:5px 14px;color:#666">Ganancia Neta</td>
            <td style="padding:5px;font-weight:bold;color:#e47911">${metrics['ganancia']:.2f} USD</td></tr>
        <tr style="background:#f9f9f9"><td style="padding:5px 14px;color:#666">Margen</td>
            <td style="padding:5px;font-weight:bold">{metrics['margen']:.1f}%</td></tr>
        <tr><td style="padding:5px 14px;color:#666">Unidades</td>
            <td style="padding:5px;font-weight:bold">{metrics['total_unidades']}</td></tr>
    </table>
    <h4 style="color:#555">Acumulado YTD</h4>
    <table style="border-collapse:collapse">
        <tr><td style="padding:5px 14px;color:#666">Ventas YTD</td>
            <td style="padding:5px;font-weight:bold">${metrics_ytd['total_ventas']:.2f} USD</td></tr>
        <tr style="background:#f9f9f9"><td style="padding:5px 14px;color:#666">Ganancia YTD</td>
            <td style="padding:5px;font-weight:bold;color:#e47911">${metrics_ytd['ganancia']:.2f} USD</td></tr>
        <tr><td style="padding:5px 14px;color:#666">Margen Promedio YTD</td>
            <td style="padding:5px;font-weight:bold">{metrics_ytd['margen']:.1f}%</td></tr>
    </table>
    <p style="color:#999;font-size:12px;margin-top:16px">Reporte completo adjunto en PDF.</p>
    </body></html>
    """, "html")
    msg.attach(body)

    attachment = MIMEBase("application", "octet-stream")
    attachment.set_payload(pdf_bytes)
    encoders.encode_base64(attachment)
    attachment.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(attachment)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        log.info(f"PDF enviado por email: {filename}")
    except Exception as e:
        log.error(f"Error enviando email: {e}")

# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MORAES -- Reporte Mensual P&L")
    parser.add_argument("--test",          action="store_true",
                        help="Datos ficticios para probar el script")
    parser.add_argument("--month",         type=str,
                        help="Mes especifico YYYY-MM (default: mes anterior)")
    parser.add_argument("--no-inventory",  action="store_true",
                        help="Omitir consulta de inventario FBA (SP-API)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("MORAES -- Reporte Mensual P&L")
    log.info("=" * 60)

    # -- Datos ficticios para test --------------------------------------------
    if args.test:
        log.info("Modo TEST activado")
        mes_start = datetime.now(BOGOTA_TZ).replace(day=1) - timedelta(days=1)
        mes_start = mes_start.replace(day=1, hour=0, minute=0, second=0)
        mes_end   = mes_start.replace(
            day=calendar.monthrange(mes_start.year, mes_start.month)[1],
            hour=23, minute=59, second=59
        )
        metrics = {
            "total_ventas": 4_820.50, "total_ventas_bruto": 5_010.00, "total_devoluciones": 189.50,
            "total_unidades": 62, "num_ordenes": 54,
            "ticket_promedio": 92.78, "total_gastos": 1_620.00,
            "ganancia": 3_200.50, "margen": 66.4,
            "top_productos": [
                ["434 - Deluxe Two Bottle Wine Carrier", 1_980.00],
                ["5231 - Golf Club Case Holder", 1_310.50],
                ["432 - Single Bottle Wine Carrier", 830.00],
                ["601 - Laptop Bag 15",              420.00],
                ["820 - Passport Holder",             280.00],
            ],
        }
        metrics_prev = {
            "total_ventas": 4_100.00, "total_ventas_bruto": 4_200.00, "total_devoluciones": 100.00,
            "total_unidades": 51, "num_ordenes": 45,
            "ticket_promedio": 93.33, "total_gastos": 1_450.00,
            "ganancia": 2_650.00, "margen": 64.6,
            "top_productos": [],
        }
        metrics_ytd = {
            "total_ventas": 9_300.00, "total_ventas_bruto": 9_600.00, "total_devoluciones": 300.00,
            "total_unidades": 118, "num_ordenes": 105,
            "ticket_promedio": 91.43, "total_gastos": 3_100.00,
            "ganancia": 6_200.00, "margen": 66.7,
            "top_productos": [],
        }
        sku_data = [
            {"producto": "434 - Deluxe Wine Carrier", "sku": "434-WINE-2B", "metodo": "FBA",
             "precio": 89.99, "ganancia": 38.50, "margen": 42.8, "roi": 68.5, "uds": 22,
             "periodo": "01/01/2026 - 28/02/2026"},
            {"producto": "5231 - Golf Club Case",     "sku": "5231-GOLF",   "metodo": "FBA",
             "precio": 74.99, "ganancia": 29.10, "margen": 38.8, "roi": 55.2, "uds": 18,
             "periodo": "01/01/2026 - 28/02/2026"},
            {"producto": "432 - Single Wine Carrier", "sku": "432-WINE-1B", "metodo": "FBM",
             "precio": 62.00, "ganancia": 22.40, "margen": 36.1, "roi": 48.0, "uds": 13,
             "periodo": "01/01/2026 - 28/02/2026"},
        ]
        inv_criticos = [
            {"sku": "5231-GOLF",   "asin": "B0TEST1", "nombre": "Golf Club Case Holder",     "disponible": 3,  "en_transito": 0},
            {"sku": "820-PASSPORT","asin": "B0TEST2", "nombre": "Passport Holder Leather",   "disponible": 0,  "en_transito": 12},
        ]
        inv_disponible = True

    else:
        # -- Rango del mes ----------------------------------------------------
        if args.month:
            ref_year, ref_month = map(int, args.month.split("-"))
            # El "mes anterior" a YYYY-MM+1 es YYYY-MM
            first_target = datetime(ref_year, ref_month, 1, tzinfo=BOGOTA_TZ)
            # Forzar que get_month_range devuelva ese mes
            ref_date = (first_target + timedelta(days=32)).replace(day=1)
        else:
            ref_date = None

        mes_start, mes_end = get_month_range(ref_date)
        log.info(f"Mes reportado: {mes_start.strftime('%d/%m/%Y')} - {mes_end.strftime('%d/%m/%Y')}")

        # Mes anterior al reportado (para delta %)
        prev_end_dt = mes_start - timedelta(days=1)
        prev_start, prev_end = get_month_range(
            (mes_start + timedelta(days=32)).replace(day=1)  # trick: siguiente mes
            if False else mes_start
        )
        # Correcto: prev del mes reportado = mes anterior a mes_start
        prev_end2   = (mes_start - timedelta(days=1)).replace(hour=23, minute=59, second=59)
        prev_start2 = prev_end2.replace(day=1, hour=0, minute=0, second=0)
        log.info(f"Mes anterior: {prev_start2.strftime('%d/%m/%Y')} - {prev_end2.strftime('%d/%m/%Y')}")

        # YTD: 1 enero -> ultimo dia del mes reportado
        ytd_start, ytd_end = get_ytd_range(mes_end)
        log.info(f"YTD: {ytd_start.strftime('%d/%m/%Y')} - {ytd_end.strftime('%d/%m/%Y')}")

        # -- Cargar datos -----------------------------------------------------
        log.info("Cargando datos de Google Sheets...")
        df_ventas = load_ventas_amazon()
        df_gastos = load_gastos_amazon()
        log.info(f"  Ventas: {len(df_ventas)} filas | Gastos: {len(df_gastos)} filas")

        gastos_fecha_col = (
            next((c for c in df_gastos.columns if "fecha" in c.lower()), "")
            if not df_gastos.empty else ""
        )

        # Filtrar mes reportado
        df_v_mes   = filter_by_range(df_ventas, "Fecha",      mes_start,   mes_end)
        df_g_mes   = filter_by_range(df_gastos, gastos_fecha_col, mes_start, mes_end) if gastos_fecha_col else pd.DataFrame()
        # Filtrar mes anterior
        df_v_prev  = filter_by_range(df_ventas, "Fecha",      prev_start2, prev_end2)
        df_g_prev  = filter_by_range(df_gastos, gastos_fecha_col, prev_start2, prev_end2) if gastos_fecha_col else pd.DataFrame()
        # Filtrar YTD
        df_v_ytd   = filter_by_range(df_ventas, "Fecha",      ytd_start,   ytd_end)
        df_g_ytd   = df_gastos.copy()  # todos los gastos del sheet = YTD real

        log.info(f"  Mes actual  -> Ventas: {len(df_v_mes)} | Gastos: {len(df_g_mes)}")
        log.info(f"  Mes anterior-> Ventas: {len(df_v_prev)} | Gastos: {len(df_g_prev)}")
        log.info(f"  YTD         -> Ventas: {len(df_v_ytd)} | Gastos: {len(df_g_ytd)}")

        metrics      = calc_metrics(df_v_mes,  df_g_mes)
        metrics_prev = calc_metrics(df_v_prev, df_g_prev)
        metrics_ytd  = calc_metrics(df_v_ytd,  df_g_ytd)

        # -- Rentabilidad por SKU ---------------------------------------------
        log.info("Cargando rentabilidad por SKU...")
        sku_data = load_rentabilidad_sku()

        # -- Inventario FBA ---------------------------------------------------
        if args.no_inventory:
            log.info("--no-inventory: saltando consulta SP-API")
            inv_criticos   = []
            inv_disponible = False
        else:
            _, inv_criticos = get_inventory_snapshot(INVENTORY_THRESHOLD)
            inv_disponible  = True

    # -- Generar PDF ----------------------------------------------------------
    mes_label = f"{MESES_ES[mes_start.month]} {mes_start.year}"
    log.info(f"Generando PDF para {mes_label}...")

    pdf_bytes = generate_pdf(
        mes_start     = mes_start,
        mes_end       = mes_end,
        metrics       = metrics,
        metrics_prev  = metrics_prev,
        metrics_ytd   = metrics_ytd,
        sku_data      = sku_data,
        inv_criticos  = inv_criticos,
        inv_disponible = inv_disponible,
    )

    # Guardar copia local
    pdf_filename = f"MORAES_PL_{mes_label.replace(' ', '_')}.pdf"
    with open(pdf_filename, "wb") as f:
        f.write(pdf_bytes)
    log.info(f"PDF guardado: {pdf_filename}")

    # -- Enviar ---------------------------------------------------------------
    send_email_with_pdf(pdf_bytes, mes_label, metrics, metrics_ytd)
    send_telegram_summary(mes_label, metrics, metrics_prev, metrics_ytd, inv_criticos)

    log.info("=" * 60)
    log.info(f"Reporte mensual {mes_label} completado.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
