"""
automations/update_modelo_rentabilidad.py
==========================================
Crea y actualiza la hoja "Modelo Unitario Rentabilidad - Amazon" con datos
REALES de ventas y fees de Amazon, separando el modelo teorico del real.

FLUJO DE USO:
  1. Primera vez -> corre con --setup
     - Crea la hoja "Modelo Unitario Rentabilidad - Amazon"
     - Copia las filas de "Modelo Unitario de Rentabilidad" (datos manuales)
     - Deja columna "Amazon SKU" vacia para que TU la llenes en el sheet
  2. Llena la columna B (Amazon SKU) en el sheet con el SKU real de Amazon
     Ejemplo: Producto "5231" -> Amazon SKU "BT-CX89-PS3K"
  3. Cada semana/mes -> corre normalmente (sin flags)
     - Lee "Ventas Amazon" y "Gastos Amazon"
     - Calcula metricas reales por SKU de Amazon
     - Actualiza columnas H-R con datos reales

Columnas del sheet resultado:
  A: Producto              | interno (ej. 5231)
  B: Amazon SKU            | SKU real en Amazon (ej. BT-CX89-PS3K) — usuario llena 1 vez
  C: Metodo de venta       | FBA / FBM / DIRECTO
  D: Precio compra COP     | manual
  E: Precio compra USD     | manual
  F: Envio CO->USA         | manual
  G: Empaque               | manual
  H: Publicidad Manual(USD)| OPCIONAL — usuario llena el total de ads del periodo para este producto
                           | Si esta vacio, el script distribuye la publicidad proporcional al ingreso
  I: Publicidad/ud REAL    | calculado (usa col H si esta llena, sino proporcional a ingresos)
  J: Comision/ud REAL      | calculado de Gastos Amazon (Commission fee)
  K: Cupon/ud REAL         | calculado (CouponParticipationFee + CouponPerformanceFee, proporcional)
  L: Fee FBA/ud REAL       | calculado de Gastos Amazon (FBA fees)
  M: Costo Total REAL      | E+F+G+I+J+K+L
  N: Precio Venta REAL     | promedio real de Ventas Amazon (ya incluye descuento de cupon)
  O: Ganancias REAL        | N-M
  P: MARGIN REAL           | O/N * 100
  Q: ROI REAL              | O/(E+F+G) * 100  (retorno sobre capital invertido)
  R: Unidades vendidas     | del periodo analizado
  S: Periodo               | ej. "01/01/2026 - 14/03/2026"
  T: Ultima actualizacion

Uso:
    python automations/update_modelo_rentabilidad.py --setup       # primera vez
    python automations/update_modelo_rentabilidad.py               # actualizar (30 dias)
    python automations/update_modelo_rentabilidad.py --days 90     # ultimos 90 dias
    python automations/update_modelo_rentabilidad.py --ytd         # acumulado del ano

Automatizacion (Windows Task Scheduler):
    Programa   : C:/Python314/python.exe
    Argumentos : automations/update_modelo_rentabilidad.py
    Iniciar en : C:/Users/Usuario/Desktop/Dashboard_Moraes
    Frecuencia : Lunes 10:05 AM
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from utils.sheets_client import get_worksheet
from utils.notifier import send_telegram

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────

BOGOTA_TZ         = ZoneInfo("America/Bogota")
SHEET_MODELO_ORIG = "Modelo Unitario de Rentabilidad"
SHEET_MODELO_REAL = "Modelo Unitario Rentabilidad - Amazon"
SHEET_VENTAS      = "Ventas Amazon"
SHEET_GASTOS      = "Gastos Amazon"

# Indices de columnas en "Modelo Unitario de Rentabilidad" (fila 1 = headers)
# A=0 Producto, B=1 Metodo, C=2 COP, D=3 USD, E=4 Envio, F=5 Empaque
ORIG_PRODUCTO = 0
ORIG_METODO   = 1
ORIG_COP      = 2
ORIG_USD      = 3
ORIG_ENVIO    = 4
ORIG_EMPAQUE  = 5

# Fee types de FBA
FBA_FEE_TYPES = {
    "FBAPerUnitFulfillmentFee",
    "FBAWeightBasedFee",
    "FBAPerOrderFulfillmentFee",
}

# Colores de la hoja
COLOR_TITULO  = {"red": 0.13, "green": 0.13, "blue": 0.13}
COLOR_TEXTO   = {"red": 1.0,  "green": 1.0,  "blue": 1.0}
COLOR_HEADER  = {"red": 0.85, "green": 0.10, "blue": 0.10}
COLOR_MANUAL  = {"red": 0.95, "green": 0.95, "blue": 0.80}  # amarillo claro = manual
COLOR_REAL    = {"red": 0.80, "green": 0.95, "blue": 0.80}  # verde claro = real Amazon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "..", "modelo_rentabilidad_log.txt"),
            encoding="utf-8"
        ),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# LECTURA DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_num(val: str) -> float:
    """Convierte string con $, comas o % a float."""
    try:
        return float(
            str(val)
            .replace("$", "")
            .replace(",", "")
            .replace("%", "")
            .strip()
        )
    except (ValueError, AttributeError):
        return 0.0


def load_modelo_original() -> list[dict]:
    """
    Lee 'Modelo Unitario de Rentabilidad' y devuelve lista de dicts
    con los campos manuales (una entrada por fila de producto).
    Solo filas con Producto no vacio.
    """
    ws = get_worksheet(SHEET_MODELO_ORIG)
    data = ws.get_all_values()
    # Fila 1 = headers, fila 2+ = datos
    headers = data[0]
    rows = data[1:]

    productos = []
    for row in rows:
        if not row or not row[ORIG_PRODUCTO].strip():
            continue
        productos.append({
            "producto":  row[ORIG_PRODUCTO].strip(),
            "metodo":    row[ORIG_METODO].strip()   if len(row) > ORIG_METODO   else "",
            "cop":       row[ORIG_COP].strip()      if len(row) > ORIG_COP      else "",
            "usd":       row[ORIG_USD].strip()      if len(row) > ORIG_USD      else "",
            "envio":     row[ORIG_ENVIO].strip()    if len(row) > ORIG_ENVIO    else "",
            "empaque":   row[ORIG_EMPAQUE].strip()  if len(row) > ORIG_EMPAQUE  else "",
        })
    log.info(f"Modelo original: {len(productos)} filas de productos")
    return productos


def load_ventas(desde: datetime, hasta: datetime) -> dict:
    """
    Lee 'Ventas Amazon' y devuelve dict organizado por SKU y metodo de fulfillment:

      {
        amazon_sku: {
          "FBA": { "unidades_netas": int, "ingreso_total": float, "precios": [float] },
          "FBM": { "unidades_netas": int, "ingreso_total": float, "precios": [float] },
        }
      }

    Unidades NETAS = unidades vendidas - unidades devueltas (REF-).
    Precio promedio se calcula solo sobre ventas positivas (no devoluciones).
    """
    ws = get_worksheet(SHEET_VENTAS)
    data = ws.get_all_values()
    headers = data[2]   # fila 3 = headers en Ventas Amazon
    rows = data[3:]

    idx = {h: i for i, h in enumerate(headers)}
    col_order  = idx.get("Order ID", 0)
    col_fecha  = idx.get("Fecha", 1)
    col_sku    = idx.get("SKU", 4)
    col_qty    = idx.get("Cantidad", 5)
    col_precio = idx.get("Ingreso Total (USD)", 7)
    col_fulfil = idx.get("Fulfillment", 8)   # FBA o FBM

    def _init_metodo():
        return {"unidades_netas": 0, "ingreso_total": 0.0, "precios": []}

    result = {}
    for row in rows:
        if not row or not row[col_sku].strip():
            continue
        try:
            fecha = datetime.strptime(row[col_fecha].strip()[:10], "%Y-%m-%d")
        except Exception:
            continue
        if not (desde.replace(tzinfo=None) <= fecha <= hasta.replace(tzinfo=None)):
            continue

        sku      = row[col_sku].strip()
        order    = row[col_order].strip()
        qty      = abs(int(_parse_num(row[col_qty])))   # siempre positivo
        precio   = _parse_num(row[col_precio])
        # Las filas REF- en el sheet tienen fulfillment "FBM" hardcoded;
        # las ventas normales tienen el fulfillment real de la orden.
        fulfil   = row[col_fulfil].strip().upper() if len(row) > col_fulfil else "FBM"
        if fulfil not in ("FBA", "FBM"):
            fulfil = "FBM"

        if sku not in result:
            result[sku] = {"FBA": _init_metodo(), "FBM": _init_metodo()}

        if order.startswith("REF-"):
            # Devolucion: resta 1 unidad neta e impacta el ingreso
            result[sku][fulfil]["unidades_netas"] -= qty
            result[sku][fulfil]["ingreso_total"]  += precio   # precio ya es negativo
        else:
            result[sku][fulfil]["unidades_netas"] += qty
            result[sku][fulfil]["ingreso_total"]  += precio
            if precio > 0:
                precio_unit = precio / qty if qty > 0 else precio
                result[sku][fulfil]["precios"].append(precio_unit)

    # Calcular precio promedio por (sku, fulfillment)
    for sku, metodos in result.items():
        for m, d in metodos.items():
            precios = d["precios"]
            d["precio_promedio"] = round(sum(precios) / len(precios), 2) if precios else 0.0

    total_uds = sum(
        d["unidades_netas"]
        for metodos in result.values()
        for d in metodos.values()
    )
    log.info(f"Ventas cargadas: {total_uds} unidades netas en {len(result)} SKU(s)")
    return result


def load_gastos(desde: datetime, hasta: datetime) -> dict:
    """
    Lee 'Gastos Amazon' y devuelve dict con fees reales:
      {
        "por_sku":          { sku: { "commission": float, "fba": float } },
        "publicidad_total": float,   <- total AdvertisingFee del periodo
        "cupon_fees_total": float,   <- total CouponParticipationFee + CouponPerformanceFee
      }
    """
    ws = get_worksheet(SHEET_GASTOS)
    data = ws.get_all_values()
    headers = data[1]   # fila 2 = headers en Gastos Amazon
    rows = data[2:]

    idx = {h: i for i, h in enumerate(headers)}
    col_fecha  = idx.get("Fecha", 1)
    col_tipo   = idx.get("Tipo de Fee", 3)
    col_sku    = idx.get("SKU", 4)
    col_monto  = idx.get("Monto (USD)", 5)

    por_sku          = {}
    publicidad_total = 0.0
    cupon_fees_total = 0.0   # CouponParticipationFee + CouponPerformanceFee

    for row in rows:
        if not row or not row[col_tipo].strip():
            continue

        sku   = row[col_sku].strip()
        tipo  = row[col_tipo].strip()
        monto = _parse_num(row[col_monto])

        # ── Fees globales (SKU=N/A) que se incluyen ANTES del filtro de fecha ──
        # Amazon a veces no devuelve PostedDate para estos, quedan como "N/A" en el sheet.
        if tipo == "AdvertisingFee":
            # Publicidad total del periodo; se distribuye proporcional (o manual en col H)
            publicidad_total += abs(monto)
            continue

        if tipo in ("CouponParticipationFee", "CouponPerformanceFee"):
            # Gastos extra por usar cupones (distintos al descuento en precio, que ya
            # esta reflejado en el precio_promedio de Ventas Amazon).
            # Se distribuyen proporcional al ingreso igual que la publicidad.
            cupon_fees_total += abs(monto)
            continue

        # ── Resto de fees: filtrar por fecha ────────────────────────────────────
        try:
            fecha = datetime.strptime(row[col_fecha].strip()[:10], "%Y-%m-%d")
        except Exception:
            continue
        if not (desde.replace(tzinfo=None) <= fecha <= hasta.replace(tzinfo=None)):
            continue

        if sku == "N/A" or not sku:
            continue   # fees globales restantes (storage, subscription, etc.)

        if sku not in por_sku:
            por_sku[sku] = {"commission": 0.0, "fba": 0.0}

        if tipo == "Commission":
            por_sku[sku]["commission"] += abs(monto)
        elif tipo in FBA_FEE_TYPES:
            por_sku[sku]["fba"] += abs(monto)

    log.info(f"Gastos cargados: {len(por_sku)} SKU(s) con fees, "
             f"publicidad: ${publicidad_total:.2f}, cupones: ${cupon_fees_total:.2f}")
    return {
        "por_sku":          por_sku,
        "publicidad_total": publicidad_total,
        "cupon_fees_total": cupon_fees_total,
    }

# ─────────────────────────────────────────────────────────────────────────────
# CALCULOS POR SKU
# ─────────────────────────────────────────────────────────────────────────────

def calcular_metricas_reales(
    amazon_sku: str,
    metodo: str,
    usd_compra: float,
    envio: float,
    empaque: float,
    ventas: dict,
    gastos: dict,
    pub_manual: float = 0.0,   # col H del sheet — total ads del periodo para este producto
                                # Si > 0 se usa directo; si == 0 se distribuye proporcional
) -> dict | None:
    """
    Calcula las metricas reales para un SKU + metodo de fulfillment especifico.
    Retorna None si no hay datos de ventas para ese SKU/metodo en el periodo.

    ventas: { sku: { "FBA": {...}, "FBM": {...} } }
    Se usa solo el metodo que corresponde a esta fila del modelo.

    pub_manual: si el usuario llenó la col H con el total de publicidad para este
    producto en el periodo, se usa ese valor en lugar de la distribución proporcional.
    Esto es util cuando la publicidad estuvo repartida entre varios productos
    (algunos sin ventas) y la distribución por ingreso no sería correcta.
    """
    metodo_key = "FBA" if "FBA" in metodo.upper() else "FBM"

    datos_sku = ventas.get(amazon_sku)
    if not datos_sku:
        return None

    datos_venta = datos_sku.get(metodo_key, {})
    unidades    = datos_venta.get("unidades_netas", 0)

    if unidades <= 0:
        return None   # sin ventas netas para este metodo en el periodo

    ingreso_sku  = datos_venta.get("ingreso_total", 0.0)
    precio_venta = datos_venta.get("precio_promedio", 0.0)

    # ── Fees del SKU (Commission y FBA vienen de ShipmentEventList) ───────────
    fees_sku   = gastos["por_sku"].get(amazon_sku, {"commission": 0.0, "fba": 0.0})
    commission = fees_sku["commission"]
    fba_fees   = fees_sku["fba"]

    # ── Publicidad ────────────────────────────────────────────────────────────
    if pub_manual > 0:
        # El usuario especificó cuánto se gastó en ads para ESTE producto
        publicidad_sku = pub_manual
        log.info(f"    {amazon_sku}: usando publicidad manual ${pub_manual:.2f}")
    else:
        # Distribuir el total de ads proporcional al ingreso generado por este SKU/metodo
        ingreso_total_todos = sum(
            d_m.get("ingreso_total", 0.0)
            for d_s in ventas.values()
            for d_m in d_s.values()
            if d_m.get("ingreso_total", 0.0) > 0
        )
        if ingreso_total_todos > 0 and ingreso_sku > 0:
            pct_ingreso = ingreso_sku / ingreso_total_todos
        else:
            pct_ingreso = 1.0 / max(len(ventas), 1)
        publicidad_sku = gastos["publicidad_total"] * pct_ingreso

    # ── Cupon fees ────────────────────────────────────────────────────────────
    # CouponParticipationFee + CouponPerformanceFee son cargos extras de Amazon
    # por el programa de cupones. El descuento al comprador YA está reflejado en
    # el precio_promedio de Ventas Amazon; esto es el costo adicional de la plataforma.
    # Se distribuye proporcional al ingreso (igual que publicidad).
    ingreso_total_todos = sum(
        d_m.get("ingreso_total", 0.0)
        for d_s in ventas.values()
        for d_m in d_s.values()
        if d_m.get("ingreso_total", 0.0) > 0
    )
    if ingreso_total_todos > 0 and ingreso_sku > 0:
        pct_ingreso_cupon = ingreso_sku / ingreso_total_todos
    else:
        pct_ingreso_cupon = 1.0 / max(len(ventas), 1)
    cupon_sku = gastos.get("cupon_fees_total", 0.0) * pct_ingreso_cupon

    # ── Metricas por unidad ───────────────────────────────────────────────────
    pub_ud   = round(publicidad_sku / unidades, 2) if unidades > 0 else 0.0
    com_ud   = round(commission     / unidades, 2) if unidades > 0 else 0.0
    cupon_ud = round(cupon_sku      / unidades, 2) if unidades > 0 else 0.0
    fba_ud   = round(fba_fees       / unidades, 2) if unidades > 0 else 0.0

    # FBM no paga fee de fulfillment FBA
    if metodo_key == "FBM":
        fba_ud = 0.0

    costo_total = round(usd_compra + envio + empaque + pub_ud + com_ud + cupon_ud + fba_ud, 2)
    ganancias   = round(precio_venta - costo_total, 2)
    margen      = round((ganancias / precio_venta * 100), 2) if precio_venta > 0 else 0.0
    capital_inv = usd_compra + envio + empaque
    roi         = round((ganancias / capital_inv * 100), 2)  if capital_inv > 0 else 0.0

    return {
        "pub_ud":       pub_ud,
        "com_ud":       com_ud,
        "cupon_ud":     cupon_ud,
        "fba_ud":       fba_ud,
        "costo_total":  costo_total,
        "precio_venta": precio_venta,
        "ganancias":    ganancias,
        "margen":       margen,
        "roi":          roi,
        "unidades":     unidades,
    }

# ─────────────────────────────────────────────────────────────────────────────
# SETUP — CREAR HOJA POR PRIMERA VEZ
# ─────────────────────────────────────────────────────────────────────────────

HEADERS_REAL = [
    # ── Datos manuales (A-H) ─────────────────────────────────────────────────
    "Producto", "Amazon SKU", "Metodo de venta",
    "Precio compra (COP)", "Precio compra (USD)", "Envio CO->USA", "Empaque",
    "Publicidad Manual (USD)",          # H — usuario llena total ads del periodo; si vacio = proporcional
    # ── Datos calculados REALES (I-T) ────────────────────────────────────────
    "Publicidad/ud REAL",               # I
    "Comision/ud REAL",                 # J
    "Cupon/ud REAL",                    # K — CouponParticipationFee + CouponPerformanceFee proporcional
    "Fee FBA/ud REAL",                  # L
    "Costo Total REAL",                 # M
    "Precio Venta REAL",                # N — precio promedio real (ya incluye descuento cupon)
    "Ganancias REAL",                   # O
    "MARGIN REAL",                      # P
    "ROI REAL",                         # Q
    "Unidades vendidas",                # R
    "Periodo",                          # S
    "Ultima actualizacion",             # T
]

def setup_sheet(productos: list[dict]):
    """
    Crea la hoja 'Modelo Unitario Rentabilidad - Amazon' con las filas del
    modelo original y la columna Amazon SKU vacia para que el usuario complete.
    """
    from utils.sheets_client import get_worksheet as _gw
    import gspread
    from google.oauth2.service_account import Credentials

    # Verificar si ya existe
    ws_orig = get_worksheet(SHEET_MODELO_ORIG)
    spreadsheet = ws_orig.spreadsheet

    existing = [ws.title for ws in spreadsheet.worksheets()]
    if SHEET_MODELO_REAL in existing:
        log.warning(
            f"La hoja '{SHEET_MODELO_REAL}' ya existe. "
            "Usa el modo normal (sin --setup) para actualizar. "
            "Si quieres recrearla, elimina la hoja manualmente primero."
        )
        return False

    log.info(f"Creando hoja '{SHEET_MODELO_REAL}'...")
    ws = spreadsheet.add_worksheet(
        title=SHEET_MODELO_REAL,
        rows=max(50, len(productos) + 5),
        cols=len(HEADERS_REAL) + 2,
    )

    # Fila 1: Titulo
    ws.update([["MODELO UNITARIO RENTABILIDAD — AMAZON (DATOS REALES)"]], "A1")
    ws.merge_cells(f"A1:{chr(64 + len(HEADERS_REAL))}1")
    ws.format("A1", {
        "backgroundColor": COLOR_TITULO,
        "textFormat": {
            "foregroundColor": COLOR_TEXTO,
            "bold": True,
            "fontSize": 13,
        },
        "horizontalAlignment": "CENTER",
    })

    # Fila 2: Headers
    ws.update([HEADERS_REAL], "A2")
    ws.format(f"A2:{chr(64 + len(HEADERS_REAL))}2", {
        "backgroundColor": COLOR_HEADER,
        "textFormat": {"foregroundColor": COLOR_TEXTO, "bold": True},
        "horizontalAlignment": "CENTER",
    })

    # Colorear columnas manuales (A-H = cols 1-8) vs reales (I-T = cols 9-20)
    ws.format("A2:H2", {
        "backgroundColor": {"red": 0.90, "green": 0.70, "blue": 0.10},  # naranja = manual
        "textFormat": {"foregroundColor": COLOR_TEXTO, "bold": True},
    })
    ws.format("I2:T2", {
        "backgroundColor": {"red": 0.13, "green": 0.55, "blue": 0.13},  # verde = Amazon real
        "textFormat": {"foregroundColor": COLOR_TEXTO, "bold": True},
    })

    # Filas de datos — copiar info manual, dejar B y H vacias para que usuario llene
    data_rows = []
    for p in productos:
        row = [
            p["producto"],   # A
            "",              # B — Amazon SKU (usuario llena)
            p["metodo"],     # C
            p["cop"],        # D
            p["usd"],        # E
            p["envio"],      # F
            p["empaque"],    # G
            "",              # H — Publicidad Manual USD (usuario llena, opcional)
            # I-T: vacio hasta que el usuario complete col B y se corra el script
            "", "", "", "", "", "", "", "", "", "", "", "",
        ]
        data_rows.append(row)

    if data_rows:
        ws.update(data_rows, "A3", value_input_option="USER_ENTERED")

    # Congelar primeras 2 filas
    ws.freeze(rows=2)

    # Notas en headers para guiar al usuario
    ws.update(
        [["Amazon SKU\n(completar manualmente)"]],
        "B2",
        value_input_option="USER_ENTERED"
    )
    ws.update(
        [["Publicidad Manual (USD)\n(opcional — total ads del periodo para este producto)"]],
        "H2",
        value_input_option="USER_ENTERED"
    )

    log.info(f"Hoja '{SHEET_MODELO_REAL}' creada con {len(productos)} productos.")
    log.info("=" * 60)
    log.info("SIGUIENTE PASO: Abre el sheet y completa la columna B")
    log.info("(Amazon SKU) con el SKU real de cada producto en Amazon.")
    log.info("Ejemplo: Producto '5231' -> Amazon SKU 'BT-CX89-PS3K'")
    log.info("Despues corre el script sin --setup para actualizar con datos reales.")
    log.info("=" * 60)
    return True

# ─────────────────────────────────────────────────────────────────────────────
# UPDATE — ACTUALIZAR CON DATOS REALES
# ─────────────────────────────────────────────────────────────────────────────

def update_sheet(ventas: dict, gastos: dict, desde: datetime, hasta: datetime):
    """
    Lee la hoja existente, obtiene el mapeo Amazon SKU de col B,
    calcula metricas reales y actualiza columnas H-R.
    """
    ws = get_worksheet(SHEET_MODELO_REAL)
    data = ws.get_all_values()

    # Fila 2 = headers, fila 3+ = datos
    if len(data) < 3:
        log.error("La hoja esta vacia. Corre primero con --setup.")
        return 0

    periodo_str = f"{desde.strftime('%d/%m/%Y')} - {hasta.strftime('%d/%m/%Y')}"
    ahora_str   = datetime.now(BOGOTA_TZ).strftime("%d/%m/%Y %H:%M")

    updates      = []
    actualizados = 0
    sin_sku      = 0
    sin_ventas   = 0

    for i, row in enumerate(data[2:], start=3):  # fila 3 en adelante
        if not row or not row[0].strip():
            continue

        producto    = row[0].strip()
        amazon_sku  = row[1].strip() if len(row) > 1 else ""
        metodo      = row[2].strip() if len(row) > 2 else ""
        usd_compra  = _parse_num(row[4]) if len(row) > 4 else 0.0
        envio       = _parse_num(row[5]) if len(row) > 5 else 0.0
        empaque     = _parse_num(row[6]) if len(row) > 6 else 0.0
        # col H (index 7): publicidad manual en USD — si el usuario lo llenó, se usa directo
        pub_manual  = _parse_num(row[7]) if len(row) > 7 else 0.0

        # Sin Amazon SKU: no se puede calcular
        if not amazon_sku:
            sin_sku += 1
            updates.append({
                "range": f"I{i}:T{i}",
                "values": [["—"] * 12],
            })
            continue

        # Solo FBA y FBM tienen fees de Amazon; DIRECTO no
        if "DIRECTO" in metodo.upper():
            updates.append({
                "range": f"I{i}:T{i}",
                "values": [["N/A (DIRECTO)"] + [""] * 11],
            })
            continue

        # Calcular metricas reales
        m = calcular_metricas_reales(
            amazon_sku, metodo, usd_compra, envio, empaque, ventas, gastos,
            pub_manual=pub_manual,
        )

        if m is None:
            sin_ventas += 1
            metodo_label = "FBA" if "FBA" in metodo.upper() else "FBM"
            updates.append({
                "range": f"I{i}:T{i}",
                "values": [[f"Sin ventas {metodo_label} en periodo"] + [""] * 11],
            })
            log.warning(f"  {producto} ({amazon_sku}): sin ventas en el periodo")
            continue

        pub_label = f"${pub_manual:.2f} manual" if pub_manual > 0 else f"${m['pub_ud']:.2f}/ud proporcional"
        updates.append({
            "range": f"I{i}:T{i}",
            "values": [[
                m["pub_ud"],        # I — Publicidad/ud
                m["com_ud"],        # J — Comision/ud
                m["cupon_ud"],      # K — Cupon/ud
                m["fba_ud"],        # L — Fee FBA/ud
                m["costo_total"],   # M — Costo Total
                m["precio_venta"],  # N — Precio Venta
                m["ganancias"],     # O — Ganancias
                f"{m['margen']:.2f}%",  # P — Margin
                f"{m['roi']:.2f}%",     # Q — ROI
                m["unidades"],      # R — Unidades
                periodo_str,        # S — Periodo
                ahora_str,          # T — Ultima actualizacion
            ]],
        })
        actualizados += 1
        log.info(
            f"  {producto} ({amazon_sku}) [{metodo}] | {m['unidades']} uds | "
            f"Precio: ${m['precio_venta']:.2f} | Pub: {pub_label} | "
            f"Cupon: ${m['cupon_ud']:.2f}/ud | "
            f"Margen: {m['margen']:.1f}% | ROI: {m['roi']:.1f}%"
        )

    # Escribir todas las actualizaciones en batch
    if updates:
        ws.spreadsheet.values_batch_update({
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": f"'{SHEET_MODELO_REAL}'!{u['range']}", "values": u["values"]}
                for u in updates
            ],
        })

    log.info(f"Actualizados: {actualizados} | Sin Amazon SKU: {sin_sku} | "
             f"Sin ventas en periodo: {sin_ventas}")
    return actualizados

# ─────────────────────────────────────────────────────────────────────────────
# RECREATE — borrar y recrear la hoja conservando SKU mappings
# ─────────────────────────────────────────────────────────────────────────────

def recreate_sheet(productos: list[dict]):
    """
    Migración de layout: lee los Amazon SKUs y publicidad manual que el usuario
    ya llenó en la hoja existente, la borra, la recrea con la estructura nueva
    (A-T, incluyendo col H Publicidad Manual y col K Cupon/ud) y re-inyecta
    los mappings salvados.

    Úsalo cuando cambia el layout de columnas para no perder el trabajo manual.
    """
    ws_orig = get_worksheet(SHEET_MODELO_ORIG)
    spreadsheet = ws_orig.spreadsheet

    # ── Leer datos salvables de la hoja existente ────────────────────────────
    saved_skus  = {}   # { producto_nombre: amazon_sku }
    saved_pubs  = {}   # { producto_nombre: pub_manual_usd }

    existing = [ws.title for ws in spreadsheet.worksheets()]
    if SHEET_MODELO_REAL in existing:
        ws_old  = spreadsheet.worksheet(SHEET_MODELO_REAL)
        old_data = ws_old.get_all_values()
        # Fila 3+ = datos (fila 1=titulo, fila 2=headers)
        for row in old_data[2:]:
            if not row or not row[0].strip():
                continue
            prod = row[0].strip()
            sku  = row[1].strip() if len(row) > 1 else ""
            # col H puede ser "Publicidad Manual (USD)" (nuevo) o "Publicidad/ud REAL" (viejo)
            # Solo salvamos si parece un número razonable y la col tiene label manual
            pub_raw = row[7].strip() if len(row) > 7 else ""
            try:
                pub_val = float(pub_raw.replace("$", "").replace(",", ""))
            except (ValueError, AttributeError):
                pub_val = 0.0

            if sku:
                saved_skus[prod] = sku
                log.info(f"  Salvando: {prod} -> {sku}")
            if pub_val > 0:
                saved_pubs[prod] = pub_val

        log.info(f"SKUs salvados: {len(saved_skus)} | Pubs manuales salvadas: {len(saved_pubs)}")

        # Borrar hoja vieja
        log.info(f"Borrando hoja '{SHEET_MODELO_REAL}'...")
        spreadsheet.del_worksheet(ws_old)
    else:
        log.info("La hoja no existe aun, se creara desde cero.")

    # ── Crear hoja nueva con estructura actualizada ──────────────────────────
    ok = setup_sheet(productos)
    if not ok:
        log.error("Error al crear la hoja nueva.")
        return False

    # ── Re-inyectar Amazon SKUs y publicidad manual salvados ─────────────────
    if saved_skus or saved_pubs:
        ws_new   = spreadsheet.worksheet(SHEET_MODELO_REAL)
        new_data = ws_new.get_all_values()

        reinyect_updates = []
        for i, row in enumerate(new_data[2:], start=3):
            if not row or not row[0].strip():
                continue
            prod = row[0].strip()
            sku  = saved_skus.get(prod, "")
            pub  = saved_pubs.get(prod, "")

            if sku:
                reinyect_updates.append({
                    "range": f"'{SHEET_MODELO_REAL}'!B{i}",
                    "values": [[sku]],
                })
            if pub:
                reinyect_updates.append({
                    "range": f"'{SHEET_MODELO_REAL}'!H{i}",
                    "values": [[pub]],
                })

        if reinyect_updates:
            ws_new.spreadsheet.values_batch_update({
                "valueInputOption": "USER_ENTERED",
                "data": reinyect_updates,
            })
            log.info(f"Re-inyectados {len(saved_skus)} SKUs y {len(saved_pubs)} valores de publicidad manual.")

    return True


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="MORAES - Actualizar Modelo Unitario de Rentabilidad con datos reales de Amazon"
    )
    parser.add_argument("--setup",    action="store_true",
                        help="Primera vez: crea la hoja y copia datos del modelo teorico")
    parser.add_argument("--recreate", action="store_true",
                        help="Migrar layout: borra la hoja, la recrea y restaura SKUs/publicidad manual")
    parser.add_argument("--days",     type=int, default=30,
                        help="Dias hacia atras para calcular metricas (default: 30)")
    parser.add_argument("--ytd",      action="store_true",
                        help="Usar datos del ano en curso (YTD)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("MORAES - Modelo Unitario Rentabilidad (Datos Reales Amazon)")
    log.info("=" * 60)

    ahora = datetime.now(BOGOTA_TZ)

    # ── Modo SETUP ──────────────────────────────────────────────────────────
    if args.setup:
        log.info("Modo SETUP: creando hoja 'Modelo Unitario Rentabilidad - Amazon'...")
        productos = load_modelo_original()
        ok = setup_sheet(productos)
        if ok:
            send_telegram(
                f"<b>📊 MORAES — Modelo Rentabilidad</b>\n"
                f"<i>{ahora.strftime('%d/%m/%Y %I:%M %p')} (Bogotá)</i>\n"
                f"─────────────────────\n"
                f"✅ Hoja <b>'{SHEET_MODELO_REAL}'</b> creada con {len(productos)} productos.\n"
                f"📝 <b>Siguiente paso:</b> Abre el sheet y llena la columna B "
                f"(Amazon SKU) para cada producto FBA/FBM.\n"
                f"Ejemplo: <code>5231 -> BT-CX89-PS3K</code>"
            )
        return

    # ── Modo RECREATE ────────────────────────────────────────────────────────
    if args.recreate:
        log.info("Modo RECREATE: migrando layout (salvando SKUs y recreando hoja)...")
        productos = load_modelo_original()
        ok = recreate_sheet(productos)
        if not ok:
            log.error("Fallo el recreate. Revisa los logs.")
            return
        log.info("Hoja recreada. Continuando con update de datos reales (YTD)...")
        args.ytd = True   # al recrear siempre actualiza YTD para tener datos completos

    # ── Rango de fechas ─────────────────────────────────────────────────────
    if args.ytd:
        desde = ahora.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        hasta = ahora
        periodo_label = f"YTD {ahora.year}"
    else:
        desde = ahora - timedelta(days=args.days)
        hasta = ahora
        periodo_label = f"Ultimos {args.days} dias"

    log.info(f"Periodo: {desde.strftime('%d/%m/%Y')} -> {hasta.strftime('%d/%m/%Y')} ({periodo_label})")

    # ── Cargar datos ─────────────────────────────────────────────────────────
    log.info("Cargando Ventas Amazon...")
    ventas = load_ventas(desde, hasta)

    log.info("Cargando Gastos Amazon...")
    gastos = load_gastos(desde, hasta)

    # ── Actualizar sheet ──────────────────────────────────────────────────────
    log.info("Actualizando modelo de rentabilidad real...")
    actualizados = update_sheet(ventas, gastos, desde, hasta)

    # ── Notificacion Telegram ─────────────────────────────────────────────────
    total_unidades = sum(
        d_m.get("unidades_netas", 0)
        for d_s in ventas.values()
        for d_m in d_s.values()
    )
    total_ingresos = sum(
        d_m.get("ingreso_total", 0.0)
        for d_s in ventas.values()
        for d_m in d_s.values()
    )

    if actualizados > 0:
        msg = (
            f"<b>📊 MORAES — Modelo Rentabilidad Actualizado</b>\n"
            f"<i>{ahora.strftime('%d/%m/%Y %I:%M %p')} (Bogotá)</i>\n"
            f"─────────────────────\n"
            f"📅 Periodo: <b>{periodo_label}</b>\n"
            f"✅ {actualizados} producto(s) actualizado(s) con datos reales\n"
            f"📦 {total_unidades} unidades vendidas → ${total_ingresos:,.2f} USD\n"
            f"─────────────────────\n"
            f"Ver hoja: <i>{SHEET_MODELO_REAL}</i>"
        )
    else:
        msg = (
            f"<b>📊 MORAES — Modelo Rentabilidad</b>\n"
            f"<i>{ahora.strftime('%d/%m/%Y %I:%M %p')} (Bogotá)</i>\n"
            f"─────────────────────\n"
            f"⚠️ No se actualizaron productos.\n"
            f"Verifica que la columna B (Amazon SKU) este llena en el sheet."
        )

    send_telegram(msg)

    log.info("=" * 60)
    log.info("Completado.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
