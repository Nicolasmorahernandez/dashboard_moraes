"""
automations/sync_pedidos.py
============================
Sincroniza el estado real de las ordenes de Amazon SP-API a la hoja
"Ordenes Amazon" en Google Sheets.

DIFERENCIA con sync_amazon_sheets.py (Ventas Amazon):
  - Ventas Amazon: registros financieros, append-only, 1 fila por item.
  - Ordenes Amazon: tracking de estado, 1 fila por ORDEN, ACTUALIZA filas
    existentes cuando el estado cambia (Pending -> Shipped -> Delivered).

Columnas de "Ordenes Amazon":
  A: Order ID          | B: Fecha Compra     | C: Producto (titulo principal)
  D: SKU(s)            | E: ASIN(s)          | F: Unidades (total)
  G: Total (USD)       | H: Fulfillment      | I: Estado
  J: Marketplace       | K: Fecha Envio      | L: Entrega Estimada
  M: Ultima Actualizacion

Uso:
    python automations/sync_pedidos.py --setup          # primera vez: crea la hoja
    python automations/sync_pedidos.py                  # sync ultimos 30 dias
    python automations/sync_pedidos.py --days 60        # sync ultimos 60 dias
    python automations/sync_pedidos.py --date 2026-01-01

Automatizacion (Windows Task Scheduler):
    Programa   : C:/Python314/python.exe
    Argumentos : automations/sync_pedidos.py
    Iniciar en : C:/Users/Usuario/Desktop/Dashboard_Moraes
    Frecuencia : Diario, 7:00 AM
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from utils.sheets_client import get_worksheet
from utils.notifier import send_telegram
from utils.amazon_client import CREDENTIALS, MARKETPLACE, validate_credentials

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────

BOGOTA_TZ  = ZoneInfo("America/Bogota")
SHEET_NAME = "Ordenes Amazon"
HEADER_ROW = 3    # fila 3 (1-based) tiene los headers
DATA_START = 4    # datos desde fila 4

HEADERS = [
    "Order ID", "Fecha Compra", "Producto", "SKU(s)", "ASIN(s)",
    "Unidades", "Total (USD)", "Fulfillment", "Estado",
    "Marketplace", "Fecha Envio", "Entrega Estimada", "Ultima Actualizacion",
]

# Indices de columna (0-based) para updates
COL_ESTADO   = 8   # I
COL_FECHA_E  = 10  # K - Fecha Envio
COL_ENTREGA  = 11  # L - Entrega Estimada
COL_UPD      = 12  # M - Ultima Actualizacion

# Mapeo de estado Amazon -> etiqueta legible
ESTADO_MAP = {
    "Pending":          "Pendiente",
    "Unshipped":        "Pendiente",
    "PartiallyShipped": "Enviado parcial",
    "Shipped":          "Enviado",
    "Delivered":        "Entregado",
    "Canceled":         "Cancelado",
    "Unfulfillable":    "No disponible",
}

MARKETPLACE_NAMES = {
    "ATVPDKIKX0DER": "Amazon.com",
    "A2EUQ1WTGCTBG2": "Amazon.ca",
    "A1AM78C64UM0Y8": "Amazon.com.mx",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "..", "sync_pedidos_log.txt"),
            encoding="utf-8"
        ),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# SETUP — CREAR HOJA
# ─────────────────────────────────────────────────────────────────────────────

def setup_sheet():
    """Crea la hoja 'Ordenes Amazon' con titulo, headers y formato."""
    ws_ref = get_worksheet("Ventas Amazon")   # referencia para abrir el spreadsheet
    spreadsheet = ws_ref.spreadsheet

    existing = [ws.title for ws in spreadsheet.worksheets()]
    if SHEET_NAME in existing:
        log.warning(f"La hoja '{SHEET_NAME}' ya existe. Usa el modo sync normal.")
        return False

    log.info(f"Creando hoja '{SHEET_NAME}'...")
    ws = spreadsheet.add_worksheet(title=SHEET_NAME, rows=500, cols=len(HEADERS) + 2)

    # Fila 1: Titulo
    ws.update([["ORDENES AMAZON — ESTADO EN TIEMPO REAL"]], "A1")
    ws.merge_cells(f"A1:{chr(64 + len(HEADERS))}1")
    ws.format("A1", {
        "backgroundColor": {"red": 0.13, "green": 0.13, "blue": 0.13},
        "textFormat": {
            "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
            "bold": True, "fontSize": 13,
        },
        "horizontalAlignment": "CENTER",
    })

    # Fila 2: vacia

    # Fila 3: Headers
    ws.update([HEADERS], "A3")
    ws.format(f"A3:{chr(64 + len(HEADERS))}3", {
        "backgroundColor": {"red": 0.89, "green": 0.47, "blue": 0.07},
        "textFormat": {
            "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
            "bold": True,
        },
        "horizontalAlignment": "CENTER",
    })

    # Congelar primeras 3 filas
    ws.freeze(rows=3)

    log.info(f"Hoja '{SHEET_NAME}' creada. Corre el script sin --setup para sincronizar.")
    send_telegram(
        f"<b>MORAES -- Ordenes Amazon</b>\n"
        f"Hoja <b>'{SHEET_NAME}'</b> creada correctamente.\n"
        f"Corre el sync para poblar con datos reales."
    )
    return True

# ─────────────────────────────────────────────────────────────────────────────
# AMAZON SP-API
# ─────────────────────────────────────────────────────────────────────────────

def get_orders(since: datetime) -> list[dict]:
    """Obtiene ordenes desde Amazon con paginacion."""
    from sp_api.api import Orders
    from sp_api.base import SellingApiException

    api = Orders(credentials=CREDENTIALS, marketplace=MARKETPLACE)
    all_orders = []
    next_token = None
    page = 1
    since_iso = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info(f"Consultando ordenes desde {since_iso}...")

    while True:
        try:
            if next_token:
                resp = api.get_orders(NextToken=next_token)
            else:
                resp = api.get_orders(
                    CreatedAfter=since_iso,
                    OrderStatuses=["Pending", "Unshipped", "PartiallyShipped", "Shipped", "Canceled"],
                    MarketplaceIds=[MARKETPLACE.marketplace_id],
                )
            orders = resp.payload.get("Orders", [])
            all_orders.extend(orders)
            log.info(f"  Pagina {page}: {len(orders)} ordenes")
            next_token = resp.payload.get("NextToken")
            if not next_token:
                break
            page += 1
            time.sleep(0.5)
        except SellingApiException as e:
            log.error(f"Error SP-API: {e}")
            break

    log.info(f"Total ordenes: {len(all_orders)}")
    return all_orders


def get_order_items(order_id: str) -> list[dict]:
    """Obtiene los items de una orden."""
    from sp_api.api import Orders
    from sp_api.base import SellingApiException
    try:
        api = Orders(credentials=CREDENTIALS, marketplace=MARKETPLACE)
        resp = api.get_order_items(order_id=order_id)
        return resp.payload.get("OrderItems", [])
    except SellingApiException as e:
        log.warning(f"  Items de {order_id}: {e}")
        return []


def _fmt_date(iso_str: str) -> str:
    """Convierte ISO a fecha Bogota YYYY-MM-DD. Retorna '' si falla."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(BOGOTA_TZ)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso_str[:10]

# ─────────────────────────────────────────────────────────────────────────────
# SHEETS — LECTURA Y ESCRITURA
# ─────────────────────────────────────────────────────────────────────────────

def load_existing_orders(ws) -> dict[str, int]:
    """
    Lee la hoja y devuelve {order_id: row_number_1based} para filas de datos.
    """
    col_a = ws.col_values(1)   # Order ID esta en col A
    existing = {}
    for i, val in enumerate(col_a[DATA_START - 1:], start=DATA_START):
        v = val.strip()
        if v:
            existing[v] = i
    return existing


def build_order_row(order: dict, items: list[dict]) -> list:
    """Construye una fila [Order ID, Fecha, Producto, SKUs, ASINs, Uds, Total, FBA/FBM, Estado, Mkp, Envio, Entrega, Actualizado]."""
    order_id    = order.get("AmazonOrderId", "")
    fecha       = _fmt_date(order.get("PurchaseDate", ""))
    fulfillment = "FBA" if order.get("FulfillmentChannel", "") == "AFN" else "FBM"
    estado_raw  = order.get("OrderStatus", "")
    estado      = ESTADO_MAP.get(estado_raw, estado_raw)
    marketplace = MARKETPLACE_NAMES.get(order.get("MarketplaceId", ""), order.get("MarketplaceId", ""))
    fecha_envio = _fmt_date(order.get("LastUpdateDate", "") if estado_raw in ("Shipped", "Delivered") else "")
    entrega_est = _fmt_date(
        (order.get("PromisedDeliveryDate") or
         order.get("EarliestDeliveryDate") or
         order.get("LatestDeliveryDate") or "")
    )
    ahora = datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d %H:%M")

    # Agregar items
    total_uds = 0
    total_usd = 0.0
    skus  = []
    asins = []
    titulo_principal = ""

    for item in items:
        qty = int(item.get("QuantityOrdered", 1))
        total_uds += qty
        try:
            precio = float(item.get("ItemPrice", {}).get("Amount", 0))
        except (ValueError, TypeError):
            precio = 0.0
        total_usd += precio

        sku  = item.get("SellerSKU", "")
        asin = item.get("ASIN", "")
        if sku and sku not in skus:
            skus.append(sku)
        if asin and asin not in asins:
            asins.append(asin)
        if not titulo_principal and item.get("Title"):
            t = item["Title"]
            titulo_principal = t[:60] if len(t) > 60 else t

    return [
        order_id,                        # A
        fecha,                           # B
        titulo_principal or order_id,    # C
        ", ".join(skus),                 # D
        ", ".join(asins),                # E
        total_uds,                       # F
        round(total_usd, 2),             # G
        fulfillment,                     # H
        estado,                          # I
        marketplace,                     # J
        fecha_envio,                     # K
        entrega_est,                     # L
        ahora,                           # M
    ]

# ─────────────────────────────────────────────────────────────────────────────
# SYNC PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def sync(since: datetime):
    """Sincroniza ordenes Amazon con la hoja 'Ordenes Amazon'."""
    ws = get_worksheet(SHEET_NAME)
    existing = load_existing_orders(ws)
    log.info(f"Ordenes ya en Sheet: {len(existing)}")

    orders = get_orders(since)
    if not orders:
        log.info("Sin ordenes nuevas de Amazon.")
        return 0, 0

    nuevas   = []   # filas para append
    updates  = []   # {range, values} para batch_update de estado
    ahora    = datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d %H:%M")

    for order in orders:
        order_id   = order.get("AmazonOrderId", "")
        estado_raw = order.get("OrderStatus", "")
        estado     = ESTADO_MAP.get(estado_raw, estado_raw)
        fecha_envio = _fmt_date(order.get("LastUpdateDate", "") if estado_raw in ("Shipped", "Delivered") else "")
        entrega_est = _fmt_date(
            (order.get("PromisedDeliveryDate") or
             order.get("EarliestDeliveryDate") or
             order.get("LatestDeliveryDate") or "")
        )

        if order_id in existing:
            # Orden ya existe: actualizar estado, fecha envio, entrega y timestamp
            row_n = existing[order_id]
            col_I = f"I{row_n}"
            col_K = f"K{row_n}"
            col_L = f"L{row_n}"
            col_M = f"M{row_n}"
            updates.extend([
                {"range": f"'{SHEET_NAME}'!{col_I}", "values": [[estado]]},
                {"range": f"'{SHEET_NAME}'!{col_K}", "values": [[fecha_envio]]},
                {"range": f"'{SHEET_NAME}'!{col_L}", "values": [[entrega_est]]},
                {"range": f"'{SHEET_NAME}'!{col_M}", "values": [[ahora]]},
            ])
        else:
            # Orden nueva: obtener items y construir fila
            time.sleep(0.3)
            items = get_order_items(order_id)
            row   = build_order_row(order, items)
            nuevas.append(row)
            existing[order_id] = None   # evitar duplicado si aparece dos veces en la respuesta

    # Ejecutar actualizaciones en batch
    if updates:
        ws.spreadsheet.values_batch_update({
            "valueInputOption": "USER_ENTERED",
            "data": updates,
        })
        actualizadas = len(updates) // 4  # 4 celdas por orden
        log.info(f"Ordenes actualizadas (estado): {actualizadas}")
    else:
        actualizadas = 0

    # Agregar ordenes nuevas
    if nuevas:
        col_a  = ws.col_values(1)
        next_r = len(col_a) + 1
        ws.update(
            range_name=f"A{next_r}",
            values=nuevas,
            value_input_option="USER_ENTERED",
        )
        log.info(f"Ordenes nuevas agregadas: {len(nuevas)}")

    return len(nuevas), actualizadas

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MORAES -- Sync Ordenes Amazon")
    parser.add_argument("--setup", action="store_true",
                        help="Primera vez: crea la hoja 'Ordenes Amazon'")
    parser.add_argument("--days",  type=int, default=30,
                        help="Dias hacia atras para sincronizar (default: 30)")
    parser.add_argument("--date",  type=str,
                        help="Fecha inicio YYYY-MM-DD")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("MORAES -- Sync Ordenes Amazon")
    log.info("=" * 60)

    validate_credentials()

    if args.setup:
        log.info("Modo SETUP...")
        setup_sheet()
        return

    since = (
        datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=BOGOTA_TZ)
        if args.date
        else datetime.now(BOGOTA_TZ) - timedelta(days=args.days)
    )
    log.info(f"Sincronizando desde: {since.strftime('%d/%m/%Y')} ({args.days} dias)")

    nuevas, actualizadas = sync(since)

    ahora = datetime.now(BOGOTA_TZ).strftime("%d/%m/%Y %I:%M %p")
    if nuevas or actualizadas:
        msg = (
            f"<b>MORAES -- Sync Ordenes Amazon</b>\n"
            f"<i>{ahora} (Bogota)</i>\n"
            f"---------------------\n"
            f"+ {nuevas} orden(es) nueva(s)\n"
            f"~ {actualizadas} estado(s) actualizado(s)\n"
            f"Ver hoja: <i>{SHEET_NAME}</i>"
        )
    else:
        msg = (
            f"<b>MORAES -- Sync Ordenes Amazon</b>\n"
            f"<i>{ahora} (Bogota)</i>\n"
            f"---------------------\n"
            f"Sin cambios. Todo al dia."
        )
    send_telegram(msg)

    log.info("=" * 60)
    log.info(f"Completado: {nuevas} nuevas | {actualizadas} actualizadas.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
