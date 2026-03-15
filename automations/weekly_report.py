"""
automations/weekly_report.py
=============================
Genera reporte semanal de rentabilidad MORAES y lo envia por Email (PDF) + Telegram.

Uso:
    python automations/weekly_report.py              # semana anterior
    python automations/weekly_report.py --test       # prueba con datos ficticios
    python automations/weekly_report.py --week 2026-03-10  # semana especifica (lunes)

Automatizacion (Windows Task Scheduler):
    Programa   : C:/Python314/python.exe
    Argumentos : automations/weekly_report.py
    Iniciar en : C:/Users/Usuario/Desktop/Dashboard_Moraes
    Frecuencia : Semanal, lunes 7:00 AM
"""

import os
import sys
import argparse
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

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────

BOGOTA_TZ = ZoneInfo("America/Bogota")
SHEET_VENTAS   = "Ventas Amazon"
SHEET_GASTOS   = "Gastos Amazon"
SHEET_VENDIDOS = "Vendidos"

# Las hojas automatizadas tienen: fila 1=titulo, fila 2=vacia, fila 3=headers, fila 4+=datos
HEADER_ROW_IDX = 2   # índice 0-based de la fila de headers

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "..", "weekly_report_log.txt"),
            encoding="utf-8"
        ),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# LECTURA DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

def load_ventas_amazon() -> pd.DataFrame:
    """
    Carga la hoja 'Ventas Amazon' (sincronizada por sync_amazon_sheets.py).
    Estructura: fila 1=titulo, fila 2=vacia, fila 3=headers, fila 4+=datos.
    """
    ws = get_worksheet(SHEET_VENTAS)
    data = ws.get_all_values()
    if len(data) <= HEADER_ROW_IDX + 1:
        return pd.DataFrame()
    headers = data[HEADER_ROW_IDX]        # fila 3 (0-indexed: 2)
    rows    = data[HEADER_ROW_IDX + 1:]   # fila 4 en adelante
    df = pd.DataFrame(rows, columns=headers)
    df = df[df["Order ID"].str.strip() != ""]
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df["Ingreso Total (USD)"] = pd.to_numeric(df["Ingreso Total (USD)"], errors="coerce").fillna(0)
    df["Cantidad"] = pd.to_numeric(df["Cantidad"], errors="coerce").fillna(0)
    return df


def load_gastos_amazon() -> pd.DataFrame:
    """
    Carga la hoja 'Gastos Amazon' (sincronizada por sync_gastos_amazon.py).
    Estructura: fila 1=titulo, fila 2=headers, fila 3+=datos.
    (Sin fila vacía intermedia, a diferencia de Ventas Amazon)
    Columnas: Transaction ID | Fecha | Order ID | Tipo de Fee | SKU | Monto (USD) | Descripcion
    """
    GASTOS_HDR = 1   # índice 0-based: fila 2 tiene los headers
    try:
        ws = get_worksheet(SHEET_GASTOS)
        data = ws.get_all_values()
        if len(data) <= GASTOS_HDR + 1:
            return pd.DataFrame()
        headers = data[GASTOS_HDR]
        rows    = data[GASTOS_HDR + 1:]
        df = pd.DataFrame(rows, columns=headers)

        # Filtrar filas vacías
        id_col = headers[0]
        df = df[df[id_col].str.strip() != ""]

        # Convertir tipos
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
        log.warning(f"No se pudo cargar hoja '{SHEET_GASTOS}': {e}")
        return pd.DataFrame()


def get_week_range(reference_date: datetime = None):
    """
    Devuelve (lunes, domingo) de la semana anterior al reference_date.
    Si reference_date es None, usa hoy.
    """
    if reference_date is None:
        reference_date = datetime.now(BOGOTA_TZ)
    # Ir al lunes de esta semana, luego retroceder 7 dias
    days_since_monday = reference_date.weekday()
    this_monday = reference_date - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(days=7)
    last_sunday = last_monday + timedelta(days=6)
    return (
        last_monday.replace(hour=0, minute=0, second=0, microsecond=0),
        last_sunday.replace(hour=23, minute=59, second=59),
    )


def filter_by_week(df: pd.DataFrame, fecha_col: str, start: datetime, end: datetime) -> pd.DataFrame:
    """
    Filtra un DataFrame por rango de fechas.
    Normaliza tz para evitar TypeError entre tz-naive y tz-aware.
    """
    if df.empty or fecha_col not in df.columns:
        return pd.DataFrame()
    # Convertir start/end a tz-naive para comparar con columnas sin tz
    start_naive = pd.Timestamp(start).tz_localize(None) if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert(None)
    end_naive   = pd.Timestamp(end).tz_localize(None)   if pd.Timestamp(end).tzinfo is None   else pd.Timestamp(end).tz_convert(None)
    col = pd.to_datetime(df[fecha_col], errors="coerce").dt.tz_localize(None)
    mask = (col >= start_naive) & (col <= end_naive)
    return df[mask].copy()

# ─────────────────────────────────────────────────────────────────────────────
# CALCULOS
# ─────────────────────────────────────────────────────────────────────────────

def calc_metrics(df_ventas_week: pd.DataFrame, df_gastos_week: pd.DataFrame) -> dict:
    """Calcula metricas principales de la semana."""
    # ── Ventas ────────────────────────────────────────────────────────────────
    # Solo filas de ventas reales (excluir devoluciones REF- del conteo de ordenes)
    if not df_ventas_week.empty:
        df_sales = df_ventas_week[~df_ventas_week["Order ID"].str.startswith("REF-", na=False)]
        df_refunds = df_ventas_week[df_ventas_week["Order ID"].str.startswith("REF-", na=False)]
    else:
        df_sales = pd.DataFrame()
        df_refunds = pd.DataFrame()

    total_ventas_bruto = df_sales["Ingreso Total (USD)"].sum() if not df_sales.empty else 0
    total_devoluciones = df_refunds["Ingreso Total (USD)"].sum() if not df_refunds.empty else 0
    total_ventas = total_ventas_bruto + total_devoluciones  # devoluciones ya son negativas

    total_unidades = int(df_sales["Cantidad"].sum()) if not df_sales.empty else 0
    num_ordenes = len(df_sales) if not df_sales.empty else 0
    ticket_promedio = total_ventas_bruto / num_ordenes if num_ordenes > 0 else 0

    # ── Gastos (Amazon fees) ──────────────────────────────────────────────────
    monto_col = None
    if not df_gastos_week.empty:
        monto_col = next((c for c in df_gastos_week.columns if "monto" in c.lower()), None)
    # Los montos ya son negativos en la hoja; sumamos en valor absoluto
    if monto_col and not df_gastos_week.empty:
        raw_gastos = df_gastos_week[monto_col].sum()
        total_gastos = abs(raw_gastos)   # siempre positivo para mostrar
    else:
        total_gastos = 0

    # ── Rentabilidad ──────────────────────────────────────────────────────────
    ganancia = total_ventas - total_gastos
    margen = (ganancia / total_ventas * 100) if total_ventas > 0 else 0

    # ── Top productos ─────────────────────────────────────────────────────────
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
        "total_ventas": total_ventas,
        "total_ventas_bruto": total_ventas_bruto,
        "total_devoluciones": abs(total_devoluciones),
        "total_unidades": total_unidades,
        "num_ordenes": num_ordenes,
        "ticket_promedio": ticket_promedio,
        "total_gastos": total_gastos,
        "ganancia": ganancia,
        "margen": margen,
        "top_productos": top_productos,
    }

# ─────────────────────────────────────────────────────────────────────────────
# GENERACION DEL PDF
# ─────────────────────────────────────────────────────────────────────────────

class ReportePDF(FPDF):
    title = "MORAES LEATHER - Reporte Semanal"   # se puede sobreescribir

    def header(self):
        self.set_fill_color(228, 121, 17)  # Naranja Amazon
        self.rect(0, 0, 210, 18, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.set_y(4)
        self.cell(0, 10, self.title, align="C")
        self.set_text_color(0, 0, 0)
        self.ln(14)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Generado automaticamente el {datetime.now().strftime('%d/%m/%Y %H:%M')} | Pagina {self.page_no()}", align="C")

    def section_title(self, title: str):
        self.set_fill_color(245, 245, 245)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, f"  {title}", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def metric_row(self, label: str, value: str, highlight: bool = False):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(80, 80, 80)
        self.cell(100, 7, f"  {label}")
        if highlight:
            self.set_font("Helvetica", "B", 10)
            self.set_text_color(228, 121, 17)
        else:
            self.set_font("Helvetica", "B", 10)
            self.set_text_color(30, 30, 30)
        self.cell(0, 7, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)

    def delta_row(self, label: str, value: str, delta: float):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(80, 80, 80)
        self.cell(100, 7, f"  {label}")
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 30, 30)
        self.cell(50, 7, value)
        # Delta en verde o rojo
        if delta > 0:
            self.set_text_color(0, 150, 0)
            delta_str = f"+{delta:.1f}%"
        elif delta < 0:
            self.set_text_color(200, 0, 0)
            delta_str = f"{delta:.1f}%"
        else:
            self.set_text_color(100, 100, 100)
            delta_str = "0%"
        self.set_font("Helvetica", "I", 9)
        self.cell(0, 7, delta_str, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)


def generate_pdf(
    metrics: dict,
    metrics_prev: dict,
    week_start: datetime,
    week_end: datetime,
    period_label: str = None,
) -> bytes:
    """Genera el PDF del reporte y devuelve bytes."""
    pdf = ReportePDF()
    pdf.title = f"MORAES LEATHER - {period_label}" if period_label else "MORAES LEATHER - Reporte Semanal"
    pdf.add_page()

    # ── Período ──────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 100, 100)
    label = period_label or f"Semana: {week_start.strftime('%d/%m/%Y')} al {week_end.strftime('%d/%m/%Y')}"
    pdf.cell(0, 6, label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # ── Resumen de Ventas ────────────────────────────────────────────────────
    pdf.section_title("RESUMEN DE VENTAS")
    delta_ventas = _delta(metrics["total_ventas"], metrics_prev["total_ventas"])
    delta_uds = _delta(metrics["total_unidades"], metrics_prev["total_unidades"])
    pdf.delta_row("Ingresos Netos (USD)", f"${metrics['total_ventas']:.2f}", delta_ventas)
    pdf.metric_row("  Ventas Brutas", f"${metrics['total_ventas_bruto']:.2f} USD")
    if metrics["total_devoluciones"] > 0:
        pdf.metric_row("  Devoluciones", f"-${metrics['total_devoluciones']:.2f} USD")
    pdf.delta_row("Unidades Vendidas", str(metrics["total_unidades"]), delta_uds)
    pdf.metric_row("Ordenes", str(metrics["num_ordenes"]))
    pdf.metric_row("Ticket Promedio", f"${metrics['ticket_promedio']:.2f} USD")
    pdf.ln(4)

    # ── Ganancias y Margenes ─────────────────────────────────────────────────
    pdf.section_title("GANANCIAS Y MARGENES")
    delta_gastos = _delta(metrics["total_gastos"], metrics_prev["total_gastos"])
    delta_ganancia = _delta(metrics["ganancia"], metrics_prev["ganancia"])
    pdf.delta_row("Total Gastos", f"${metrics['total_gastos']:.2f} USD", -delta_gastos)
    pdf.delta_row("Ganancia Neta", f"${metrics['ganancia']:.2f} USD", delta_ganancia)
    pdf.metric_row("Margen de Ganancia", f"{metrics['margen']:.1f}%", highlight=True)
    pdf.ln(4)

    # ── Top Productos ────────────────────────────────────────────────────────
    pdf.section_title("TOP PRODUCTOS DE LA SEMANA")
    if metrics["top_productos"]:
        pdf.set_fill_color(228, 121, 17)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(120, 7, "  Producto", fill=True)
        pdf.cell(0, 7, "Ingresos", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

        for i, (producto, ingreso) in enumerate(metrics["top_productos"]):
            pdf.set_fill_color(252, 252, 252) if i % 2 == 0 else pdf.set_fill_color(245, 245, 245)
            pdf.set_font("Helvetica", "", 9)
            nombre = str(producto)[:55] + "..." if len(str(producto)) > 55 else str(producto)
            pdf.cell(120, 7, f"  {nombre}", fill=True)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 7, f"${ingreso:.2f}", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 7, "  Sin ventas registradas esta semana", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # ── Comparacion semana anterior ──────────────────────────────────────────
    pdf.section_title("COMPARACION CON SEMANA ANTERIOR")
    items_comp = [
        ("Ventas", metrics["total_ventas"], metrics_prev["total_ventas"]),
        ("Gastos", metrics["total_gastos"], metrics_prev["total_gastos"]),
        ("Ganancia", metrics["ganancia"], metrics_prev["ganancia"]),
        ("Unidades", metrics["total_unidades"], metrics_prev["total_unidades"]),
    ]
    for label, curr, prev in items_comp:
        prev_str = f"${prev:.2f}" if label != "Unidades" else str(int(prev))
        curr_str = f"${curr:.2f}" if label != "Unidades" else str(int(curr))
        delta = _delta(curr, prev)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(60, 7, f"  {label}")
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(40, 7, curr_str)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(40, 7, f"(ant: {prev_str})")
        if delta > 0:
            pdf.set_text_color(0, 150, 0)
        elif delta < 0:
            pdf.set_text_color(200, 0, 0)
        else:
            pdf.set_text_color(100, 100, 100)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 7, f"{'+' if delta > 0 else ''}{delta:.1f}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    return bytes(pdf.output())


def _delta(curr: float, prev: float) -> float:
    """Calcula variacion porcentual."""
    if prev == 0:
        return 100.0 if curr > 0 else 0.0
    return (curr - prev) / abs(prev) * 100

# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICACIONES
# ─────────────────────────────────────────────────────────────────────────────

def send_telegram_summary(metrics: dict, week_start: datetime, week_end: datetime, metrics_prev: dict):
    """Envia resumen corto por Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram no configurado.")
        return

    ganancia_emoji = "green" if metrics["ganancia"] >= 0 else "red"
    delta_v = _delta(metrics["total_ventas"], metrics_prev["total_ventas"])
    delta_g = _delta(metrics["ganancia"], metrics_prev["ganancia"])

    msg = (
        f"<b>MORAES - Reporte Semanal</b>\n"
        f"<i>{week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m/%Y')}</i>\n\n"
        f"Ventas:   <b>${metrics['total_ventas']:.2f}</b>  ({'+' if delta_v >= 0 else ''}{delta_v:.1f}% vs sem. ant.)\n"
        f"Gastos:   <b>${metrics['total_gastos']:.2f}</b>\n"
        f"Ganancia: <b>${metrics['ganancia']:.2f}</b>  ({'+' if delta_g >= 0 else ''}{delta_g:.1f}%)\n"
        f"Margen:   <b>{metrics['margen']:.1f}%</b>\n"
        f"Unidades: <b>{metrics['total_unidades']}</b>\n\n"
        f"PDF completo enviado al correo."
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        if resp.status_code == 200:
            log.info("Resumen enviado por Telegram")
        else:
            log.error(f"Error Telegram: {resp.text}")
    except Exception as e:
        log.error(f"Error Telegram: {e}")


def send_email_with_pdf(pdf_bytes: bytes, metrics: dict, week_start: datetime, week_end: datetime):
    """Envia el PDF por email."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        log.warning("Gmail no configurado.")
        return

    subject = f"MORAES - Reporte Semanal {week_start.strftime('%d/%m')} al {week_end.strftime('%d/%m/%Y')}"
    filename = f"MORAES_Reporte_{week_start.strftime('%Y%m%d')}.pdf"

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER

    body = MIMEText(f"""
    <html><body style="font-family:Arial,sans-serif">
    <h2 style="color:#e47911">MORAES Leather - Reporte Semanal</h2>
    <p>Semana: <b>{week_start.strftime('%d/%m/%Y')}</b> al <b>{week_end.strftime('%d/%m/%Y')}</b></p>
    <table style="border-collapse:collapse">
        <tr><td style="padding:4px 12px;color:#666">Ventas Totales</td>
            <td style="padding:4px;font-weight:bold">${metrics['total_ventas']:.2f} USD</td></tr>
        <tr><td style="padding:4px 12px;color:#666">Gastos</td>
            <td style="padding:4px;font-weight:bold">${metrics['total_gastos']:.2f} USD</td></tr>
        <tr><td style="padding:4px 12px;color:#666">Ganancia Neta</td>
            <td style="padding:4px;font-weight:bold;color:#e47911">${metrics['ganancia']:.2f} USD</td></tr>
        <tr><td style="padding:4px 12px;color:#666">Margen</td>
            <td style="padding:4px;font-weight:bold">{metrics['margen']:.1f}%</td></tr>
    </table>
    <p style="color:#999;font-size:12px">Reporte completo adjunto en PDF.</p>
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

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MORAES - Reporte semanal / YTD")
    parser.add_argument("--test", action="store_true", help="Usa datos ficticios para probar")
    parser.add_argument("--week", type=str, help="Fecha del lunes de la semana YYYY-MM-DD")
    parser.add_argument("--ytd",  action="store_true", help="Reporte acumulado del año (enero 1 a hoy)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("MORAES - Generando reporte semanal")
    log.info("=" * 60)

    if args.test:
        log.info("Modo TEST activado")
        metrics = {
            "total_ventas": 1192.60, "total_ventas_bruto": 1247.50, "total_devoluciones": 54.90,
            "total_unidades": 18, "num_ordenes": 14,
            "ticket_promedio": 89.11, "total_gastos": 423.00, "ganancia": 769.60,
            "margen": 64.5,
            "top_productos": [
                ["434 - Deluxe Two Bottle Wine Carrier", 540.00],
                ["5231 - Golf Club Case Holder", 327.60],
                ["432 - Single Bottle Wine Carrier", 210.00],
            ],
        }
        metrics_prev = {
            "total_ventas": 980.00, "total_ventas_bruto": 980.00, "total_devoluciones": 0,
            "total_unidades": 13, "num_ordenes": 11,
            "ticket_promedio": 89.09, "total_gastos": 380.00, "ganancia": 600.00,
            "margen": 61.2, "top_productos": [],
        }
        week_start = datetime.now(BOGOTA_TZ) - timedelta(days=7)
        week_end = datetime.now(BOGOTA_TZ) - timedelta(days=1)
    elif args.ytd:
        # ── Modo YTD: 1 ene del año actual → hoy ──────────────────────────────
        hoy = datetime.now(BOGOTA_TZ)
        week_start = hoy.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        week_end   = hoy.replace(hour=23, minute=59, second=59)
        prev_start = week_start.replace(year=week_start.year - 1)
        prev_end   = week_end.replace(year=week_end.year - 1)

        log.info(f"Modo YTD: {week_start.strftime('%d/%m/%Y')} - {week_end.strftime('%d/%m/%Y')}")
        log.info("Cargando datos de Google Sheets...")
        df_ventas = load_ventas_amazon()
        df_gastos = load_gastos_amazon()
        log.info(f"  Ventas: {len(df_ventas)} filas | Gastos Amazon: {len(df_gastos)} filas")

        # YTD: ventas filtradas por año, gastos = TODAS las filas del sheet
        # (el sheet solo contiene datos del año actual; filas con fecha N/A también se incluyen)
        df_v_curr = filter_by_week(df_ventas, "Fecha", week_start, week_end)
        df_g_curr = df_gastos.copy()   # todas las filas = total real del año
        df_v_prev = filter_by_week(df_ventas, "Fecha", prev_start, prev_end)
        df_g_prev = pd.DataFrame()    # sin datos del año anterior

        log.info(f"  YTD actual  -> Ventas: {len(df_v_curr)} | Gastos: {len(df_g_curr)}")
        log.info(f"  YTD anterior-> Ventas: {len(df_v_prev)} | Gastos: {len(df_g_prev)}")

        metrics      = calc_metrics(df_v_curr, df_g_curr)
        metrics_prev = calc_metrics(df_v_prev, df_g_prev)

        ano = hoy.year
        period_label = f"Acumulado {ano} (YTD: 01/01 al {hoy.strftime('%d/%m')})"
        log.info("Generando PDF YTD...")
        pdf_bytes = generate_pdf(metrics, metrics_prev, week_start, week_end, period_label=period_label)

        pdf_path = f"MORAES_YTD_{ano}.pdf"
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        log.info(f"PDF guardado: {pdf_path}")

        send_email_with_pdf(pdf_bytes, metrics, week_start, week_end)
        send_telegram_summary(metrics, week_start, week_end, metrics_prev)

        log.info("=" * 60)
        log.info("Reporte YTD completado.")
        log.info("=" * 60)
        return
    else:
        # Rango de semanas
        if args.week:
            ref = datetime.strptime(args.week, "%Y-%m-%d").replace(tzinfo=BOGOTA_TZ)
            week_start = ref
            week_end = ref + timedelta(days=6)
            prev_start = ref - timedelta(days=7)
            prev_end = ref - timedelta(days=1)
        else:
            week_start, week_end = get_week_range()
            prev_start, prev_end = get_week_range(week_start - timedelta(days=1))

        log.info(f"Semana actual: {week_start.strftime('%d/%m/%Y')} - {week_end.strftime('%d/%m/%Y')}")
        log.info(f"Semana anterior: {prev_start.strftime('%d/%m/%Y')} - {prev_end.strftime('%d/%m/%Y')}")

        # Cargar datos
        log.info("Cargando datos de Google Sheets...")
        df_ventas = load_ventas_amazon()
        df_gastos = load_gastos_amazon()

        log.info(f"  Ventas: {len(df_ventas)} filas | Gastos Amazon: {len(df_gastos)} filas")

        # Columna de fecha en gastos
        gastos_fecha_col = next((c for c in df_gastos.columns if "fecha" in c.lower()), "") if not df_gastos.empty else ""

        # Filtrar por semana
        df_v_curr = filter_by_week(df_ventas, "Fecha", week_start, week_end)
        df_g_curr = filter_by_week(df_gastos, gastos_fecha_col, week_start, week_end) if gastos_fecha_col else pd.DataFrame()

        df_v_prev = filter_by_week(df_ventas, "Fecha", prev_start, prev_end)
        df_g_prev = filter_by_week(df_gastos, gastos_fecha_col, prev_start, prev_end) if gastos_fecha_col else pd.DataFrame()

        log.info(f"  Semana actual  -> Ventas: {len(df_v_curr)} | Gastos: {len(df_g_curr)}")
        log.info(f"  Semana anterior-> Ventas: {len(df_v_prev)} | Gastos: {len(df_g_prev)}")

        metrics = calc_metrics(df_v_curr, df_g_curr)
        metrics_prev = calc_metrics(df_v_prev, df_g_prev)

    # Generar PDF
    log.info("Generando PDF...")
    pdf_bytes = generate_pdf(metrics, metrics_prev, week_start, week_end)

    # Guardar copia local
    pdf_path = f"MORAES_Reporte_{week_start.strftime('%Y%m%d')}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    log.info(f"PDF guardado: {pdf_path}")

    # Enviar
    send_email_with_pdf(pdf_bytes, metrics, week_start, week_end)
    send_telegram_summary(metrics, week_start, week_end, metrics_prev)

    log.info("=" * 60)
    log.info("Reporte completado.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
