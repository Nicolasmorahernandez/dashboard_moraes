"""
automations/sync_amazon_sheets.py
==================================
Sincroniza ventas de Amazon SP-API a la hoja "Ventas Amazon" en Google Sheets.

Uso:
    python automations/sync_amazon_sheets.py              # ultimos 7 dias
    python automations/sync_amazon_sheets.py --days 30    # ultimos 30 dias
    python automations/sync_amazon_sheets.py --date 2026-03-01

PRIMER USO: correr primero el script de setup:
    python automations/setup_amazon_sheet.py

Automatizacion diaria (Windows Task Scheduler):
    Programa   : python
    Argumentos : C:/Users/Usuario/Desktop/Dashboard_Moraes/automations/sync_amazon_sheets.py
    Frecuencia : Diario 7:00 AM
"""

import sys
import time
import argparse
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.amazon_client import CREDENTIALS, MARKETPLACE, validate_credentials
from utils.sheets_client import get_worksheet, append_rows
from utils.notifier import send_telegram
from sp_api.api import Orders, FinancesV0
from sp_api.base import SellingApiException

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────

BOGOTA_TZ = ZoneInfo("America/Bogota")
SHEET_NAME = "Ventas Amazon"      # Hoja dedicada creada con setup_amazon_sheet.py
HEADER_ROW = 3                    # Los headers estan en la fila 3
ORDER_ID_COL = "A"                # Order ID esta en columna A (facil deduplicacion)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "..", "sync_log.txt"),
            encoding="utf-8"
        ),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES AMAZON
# ─────────────────────────────────────────────────────────────────────────────

def get_orders(since_date: datetime) -> list[dict]:
    """Obtiene todas las ordenes desde una fecha con paginacion."""
    orders_api = Orders(credentials=CREDENTIALS, marketplace=MARKETPLACE)
    all_orders = []
    next_token = None
    page = 1
    since_iso = since_date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info(f"Obteniendo ordenes desde {since_iso}...")

    while True:
        try:
            if next_token:
                response = orders_api.get_orders(NextToken=next_token)
            else:
                response = orders_api.get_orders(
                    CreatedAfter=since_iso,
                    OrderStatuses=["Shipped", "Unshipped", "PartiallyShipped", "Canceled"],
                    MarketplaceIds=[MARKETPLACE.marketplace_id],
                )
            orders = response.payload.get("Orders", [])
            all_orders.extend(orders)
            log.info(f"  Pagina {page}: {len(orders)} ordenes")
            next_token = response.payload.get("NextToken")
            if not next_token:
                break
            page += 1
            time.sleep(0.5)
        except SellingApiException as e:
            log.error(f"Error SP-API obteniendo ordenes: {e}")
            break

    log.info(f"Total ordenes encontradas: {len(all_orders)}")
    return all_orders


def get_order_items(order_id: str) -> list[dict]:
    """Obtiene los items de una orden especifica."""
    orders_api = Orders(credentials=CREDENTIALS, marketplace=MARKETPLACE)
    try:
        response = orders_api.get_order_items(order_id=order_id)
        return response.payload.get("OrderItems", [])
    except SellingApiException as e:
        log.warning(f"Error obteniendo items de {order_id}: {e}")
        return []


def get_refunds(since_date: datetime) -> list[dict]:
    """Obtiene devoluciones (RefundEventList) desde la Finances API."""
    finances = FinancesV0(credentials=CREDENTIALS, marketplace=MARKETPLACE)
    since_iso = since_date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    until_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_refunds = []
    next_token = None

    log.info("Obteniendo devoluciones desde Finances API...")
    while True:
        try:
            if next_token:
                resp = finances.list_financial_events(NextToken=next_token)
            else:
                resp = finances.list_financial_events(
                    PostedAfter=since_iso,
                    PostedBefore=until_iso,
                    MaxResultsPerPage=100,
                )
            events = resp.payload.get("FinancialEvents", {}).get("RefundEventList", []) or []
            all_refunds.extend(events)
            next_token = resp.payload.get("NextToken")
            if not next_token:
                break
            time.sleep(0.5)
        except SellingApiException as e:
            log.error(f"Error obteniendo devoluciones: {e}")
            break

    log.info(f"Total devoluciones encontradas: {len(all_refunds)}")
    return all_refunds

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES SHEETS
# ─────────────────────────────────────────────────────────────────────────────

def get_existing_order_ids() -> set:
    """
    Lee la columna A (Order ID) para saber que ordenes ya estan guardadas.
    Evita duplicados en cada ejecucion.
    """
    try:
        worksheet = get_worksheet(SHEET_NAME)
        # Columna A desde fila 4 en adelante (fila 1=titulo, 2=vacia, 3=headers)
        values = worksheet.col_values(1)
        existing = set(v.strip() for v in values[HEADER_ROW:] if v.strip())
        return existing
    except Exception as e:
        log.warning(f"No se pudo obtener IDs existentes: {e}")
        return set()


def append_to_amazon_sheet(rows: list[list]) -> int:
    """Agrega filas nuevas debajo de los datos existentes."""
    if not rows:
        return 0
    worksheet = get_worksheet(SHEET_NAME)
    col_a = worksheet.col_values(1)
    next_row = len(col_a) + 1
    worksheet.update(
        range_name=f"A{next_row}",
        values=rows,
        value_input_option="USER_ENTERED",
    )
    return len(rows)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTRUCCION DE FILAS
# ─────────────────────────────────────────────────────────────────────────────

def build_rows(orders: list[dict], existing_ids: set) -> list[list]:
    """
    Convierte ordenes Amazon al formato de la hoja 'Ventas Amazon'.

    Columnas (en orden):
    Order ID | Fecha | Producto | ASIN | SKU | Cantidad |
    Precio Unitario | Ingreso Total | Fulfillment | Estado | Marketplace
    """
    rows = []
    skipped = 0

    for order in orders:
        order_id = order.get("AmazonOrderId", "")

        # Saltar si ya existe en la hoja
        if order_id in existing_ids:
            skipped += 1
            continue

        # Fecha en hora de Bogota
        try:
            dt = datetime.fromisoformat(
                order.get("PurchaseDate", "").replace("Z", "+00:00")
            ).astimezone(BOGOTA_TZ)
            fecha = dt.strftime("%Y-%m-%d")
        except Exception:
            fecha = order.get("PurchaseDate", "")[:10]

        fulfillment = order.get("FulfillmentChannel", "")
        fulfillment_label = "FBA" if fulfillment == "AFN" else "FBM"
        estado = order.get("OrderStatus", "")
        marketplace_id = order.get("MarketplaceId", "")

        # Mapear marketplace ID a nombre legible
        marketplace_names = {
            "ATVPDKIKX0DER": "Amazon.com",
            "A2EUQ1WTGCTBG2": "Amazon.ca",
            "A1AM78C64UM0Y8": "Amazon.com.mx",
        }
        marketplace = marketplace_names.get(marketplace_id, marketplace_id)

        # Obtener items de la orden
        time.sleep(0.3)
        items = get_order_items(order_id)

        for item in items:
            titulo = item.get("Title", "Producto desconocido")
            producto = titulo[:60] if len(titulo) > 60 else titulo
            asin = item.get("ASIN", "")
            sku = item.get("SellerSKU", "")
            cantidad = int(item.get("QuantityOrdered", 1))

            # Precio: ItemPrice viene como total, dividir por cantidad para unit
            price_info = item.get("ItemPrice", {})
            try:
                precio_total = float(price_info.get("Amount", 0))
                precio_unit = round(precio_total / cantidad, 2) if cantidad > 0 else precio_total
            except (ValueError, ZeroDivisionError):
                precio_unit = 0.0

            ingreso_total = round(precio_unit * cantidad, 2)

            rows.append([
                order_id,           # A - Order ID
                fecha,              # B - Fecha
                producto,           # C - Producto
                asin,               # D - ASIN
                sku,                # E - SKU
                cantidad,           # F - Cantidad
                precio_unit,        # G - Precio Unitario (USD)
                ingreso_total,      # H - Ingreso Total (USD)
                fulfillment_label,  # I - Fulfillment (FBA/FBM)
                estado,             # J - Estado
                marketplace,        # K - Marketplace
            ])

    log.info(f"Filas nuevas: {len(rows)} | Ya existian: {skipped}")
    return rows


def build_refund_rows(refunds: list[dict], existing_ids: set) -> list[list]:
    """
    Convierte devoluciones al formato de la hoja 'Ventas Amazon'.
    Las filas de devolución tienen montos NEGATIVOS y Order ID con prefijo 'REF-'.
    """
    rows = []
    skipped = 0

    for event in refunds:
        order_id = event.get("AmazonOrderId", "")
        refund_id = f"REF-{order_id}"

        if refund_id in existing_ids:
            skipped += 1
            continue

        try:
            dt = datetime.fromisoformat(
                event.get("PostedDate", "").replace("Z", "+00:00")
            ).astimezone(BOGOTA_TZ)
            fecha = dt.strftime("%Y-%m-%d")
        except Exception:
            fecha = event.get("PostedDate", "")[:10]

        for item in event.get("ShipmentItemAdjustmentList", []):
            sku  = item.get("SellerSKU", "")
            asin = item.get("ASIN", "")
            cantidad = int(item.get("QuantityShipped", 1))

            # Buscar el monto "Principal" (precio del producto devuelto)
            monto_refund = 0.0
            for charge in item.get("ItemChargeAdjustmentList", []):
                if charge.get("ChargeType") == "Principal":
                    amt = charge.get("ChargeAmount", {})
                    monto_refund = float(amt.get("CurrencyAmount", amt.get("Amount", 0)))
                    break

            if monto_refund == 0:
                continue

            # Precio unitario (negativo)
            precio_unit = round(monto_refund / cantidad, 2) if cantidad > 0 else monto_refund

            rows.append([
                refund_id,              # A - Order ID (con prefijo REF-)
                fecha,                  # B - Fecha de devolución
                f"[DEVOLUCION] {sku}",  # C - Producto
                asin,                   # D - ASIN
                sku,                    # E - SKU
                -cantidad,              # F - Cantidad (negativa)
                precio_unit,            # G - Precio Unitario
                round(monto_refund, 2), # H - Ingreso Total (negativo)
                "FBM",                  # I - Fulfillment
                "Refunded",             # J - Estado
                "Amazon.com",           # K - Marketplace
            ])

    log.info(f"Devoluciones nuevas: {len(rows)} | Ya existian: {skipped}")
    return rows

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync Amazon -> Google Sheets")
    parser.add_argument("--days", type=int, default=7, help="Dias hacia atras (default: 7)")
    parser.add_argument("--date", type=str, help="Fecha inicio YYYY-MM-DD")
    args = parser.parse_args()

    log.info("=" * 55)
    log.info("MORAES - Sync Amazon -> Ventas Amazon (Sheet)")
    log.info("=" * 55)

    # 1. Validar credenciales
    validate_credentials()

    # 2. Rango de fechas
    since = (
        datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=BOGOTA_TZ)
        if args.date
        else datetime.now(BOGOTA_TZ) - timedelta(days=args.days)
    )
    log.info(f"Desde: {since.strftime('%Y-%m-%d')} ({args.days} dias)")

    # 3. IDs ya guardados
    log.info("Conectando a Google Sheets...")
    existing_ids = get_existing_order_ids()
    log.info(f"Ordenes ya en Sheet: {len(existing_ids)}")

    # 4. Obtener ordenes de Amazon
    orders = get_orders(since)
    rows = build_rows(orders, existing_ids) if orders else []

    # 5. Obtener devoluciones
    refunds = get_refunds(since)
    refund_rows = build_refund_rows(refunds, existing_ids) if refunds else []

    # 6. Guardar todo en el Sheet
    all_rows = rows + refund_rows
    if all_rows:
        count = append_to_amazon_sheet(all_rows)
        log.info(f"OK: {len(rows)} ventas + {len(refund_rows)} devoluciones en '{SHEET_NAME}'")
    else:
        log.info("Sin datos nuevos para agregar.")

    log.info("=" * 55)
    log.info("Sincronizacion completa.")
    log.info("=" * 55)

    # 7. Notificacion Telegram
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI
    ahora = _dt.now(ZoneInfo("America/Bogota"))
    fecha_str = ahora.strftime("%d/%m/%Y %I:%M %p")
    total_en_sheet = len(existing_ids) + len(all_rows)

    if all_rows:
        total_ventas_usd = sum(r[7] for r in rows)          # col H: Ingreso Total
        lineas = [
            f"<b>📦 MORAES — Sync Ventas Amazon</b>",
            f"<i>{fecha_str} (Bogotá)</i>",
            "─────────────────────",
        ]
        if rows:
            lineas.append(f"✅ {len(rows)} orden(es) nueva(s)  →  <b>${total_ventas_usd:,.2f} USD</b>")
        if refund_rows:
            lineas.append(f"↩️ {len(refund_rows)} devolución(es) nueva(s)")
        lineas.append(f"📊 Total en sheet: {total_en_sheet} registros")
    else:
        lineas = [
            f"<b>📦 MORAES — Sync Ventas Amazon</b>",
            f"<i>{fecha_str} (Bogotá)</i>",
            "─────────────────────",
            f"✓ Sin datos nuevos",
            f"📊 Total en sheet: {total_en_sheet} registros",
        ]

    send_telegram("\n".join(lineas))


if __name__ == "__main__":
    main()
