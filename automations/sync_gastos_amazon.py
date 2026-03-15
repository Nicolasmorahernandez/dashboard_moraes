"""
sync_gastos_amazon.py
=====================
Sincroniza fees y gastos de Amazon SP-API -> hoja "Gastos Amazon" en Google Sheets

Fees que captura:
  - Commission         : Fee de referido (~15% por venta)
  - FBAPerUnitFulfillment: Fee de fulfillment FBA por unidad
  - FBAWeightBasedFee  : Fee FBA basado en peso
  - ShippingChargeback : Cobro de envio
  - RefundCommission   : Reembolso de comision en devoluciones

Uso:
    python automations/sync_gastos_amazon.py            # ultimos 7 dias
    python automations/sync_gastos_amazon.py --days 30  # ultimos 30 dias

Estructura hoja "Gastos Amazon":
    A: Transaction ID | B: Fecha | C: Order ID | D: Tipo de Fee
    E: SKU | F: Monto (USD) | G: Descripcion
"""

import os
import sys
import argparse
import time
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials
from sp_api.api import FinancesV0
from sp_api.base import Marketplaces, SellingApiException
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv()

# Agregar directorio raiz al path para importar utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.notifier import send_telegram  # noqa: E402

BOGOTA_TZ = ZoneInfo("America/Bogota")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "..", "sync_gastos_log.txt"),
            encoding="utf-8"
        ),
    ],
)
log = logging.getLogger(__name__)

AMAZON_CREDENTIALS = {
    "refresh_token": os.getenv("AMAZON_REFRESH_TOKEN"),
    "lwa_app_id": os.getenv("AMAZON_CLIENT_ID"),
    "lwa_client_secret": os.getenv("AMAZON_CLIENT_SECRET"),
}

SPREADSHEET_ID = "1TX0azfGSqKNRhMqKg_VS3iRHx0RMNPWnKGbq3Pwf8cQ"
SHEET_GASTOS = "Gastos Amazon"
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "..", "service_account.json")
MARKETPLACE = Marketplaces.US

# Colores para el header de la hoja
COLOR_HEADER = {"red": 0.13, "green": 0.13, "blue": 0.13}
COLOR_HEADER_TEXT = {"red": 1.0, "green": 1.0, "blue": 1.0}

# Tipos de fees a capturar y su descripcion amigable
FEE_LABELS = {
    "Commission":                   "Fee de referido",
    "FBAPerUnitFulfillmentFee":     "Fee FBA por unidad",
    "FBAWeightBasedFee":            "Fee FBA por peso",
    "FBAPerOrderFulfillmentFee":    "Fee FBA por orden",
    "ShippingChargeback":           "Cobro de envio",
    "RefundCommission":             "Reembolso comision",
    "ReturnShipping":               "Envio de devolucion",
    "VariableClosingFee":           "Fee de cierre variable",
    "FixedClosingFee":              "Fee de cierre fijo",
    "GiftwrapChargeback":           "Cargo regalo",
    "Goodwill":                     "Ajuste goodwill",
    "SAFE-T Claim":                 "Reclamo SAFE-T",
    "StorageRenewalBilling":        "Almacenamiento mensual",
    "LongTermStorageFee":           "Almacenamiento largo plazo",
    "AdvertisingFee":               "Publicidad PPC (Sponsored Products)",
}

# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE SHEETS
# ─────────────────────────────────────────────────────────────────────────────

def get_sheets_client():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)


def setup_sheet(gc):
    """Crea la hoja 'Gastos Amazon' si no existe, con headers y formato."""
    sheet = gc.open_by_key(SPREADSHEET_ID)

    # Verificar si ya existe
    existing = [ws.title for ws in sheet.worksheets()]
    if SHEET_GASTOS in existing:
        log.info(f"Hoja '{SHEET_GASTOS}' ya existe.")
        return sheet.worksheet(SHEET_GASTOS)

    log.info(f"Creando hoja '{SHEET_GASTOS}'...")
    worksheet = sheet.add_worksheet(title=SHEET_GASTOS, rows=1000, cols=8)

    # Titulo y headers
    headers = [
        ["GASTOS AMAZON", "", "", "", "", "", ""],
        ["Transaction ID", "Fecha", "Order ID", "Tipo de Fee", "SKU", "Monto (USD)", "Descripcion"],
    ]
    worksheet.update("A1:G2", headers, value_input_option="USER_ENTERED")

    # Formato del titulo
    worksheet.format("A1:G1", {
        "backgroundColor": COLOR_HEADER,
        "textFormat": {"foregroundColor": COLOR_HEADER_TEXT, "bold": True, "fontSize": 13},
        "horizontalAlignment": "CENTER",
    })
    worksheet.merge_cells("A1:G1")

    # Formato del header de columnas
    worksheet.format("A2:G2", {
        "backgroundColor": {"red": 0.85, "green": 0.10, "blue": 0.10},
        "textFormat": {"foregroundColor": COLOR_HEADER_TEXT, "bold": True},
        "horizontalAlignment": "CENTER",
    })

    # Congelar filas de header
    worksheet.freeze(rows=2)

    log.info(f"Hoja '{SHEET_GASTOS}' creada con formato.")
    return worksheet


def get_existing_transaction_ids(worksheet) -> set:
    """Devuelve Transaction IDs ya guardados para evitar duplicados."""
    try:
        col_a = worksheet.col_values(1)
        return set(v.strip() for v in col_a[2:] if v.strip())
    except Exception as e:
        log.warning(f"No se pudo obtener IDs existentes: {e}")
        return set()


def append_rows(worksheet, rows: list):
    if not rows:
        log.info("No hay filas nuevas de gastos.")
        return
    col_a = worksheet.col_values(1)
    next_row = max(len(col_a) + 1, 3)
    worksheet.update(
        f"A{next_row}",
        rows,
        value_input_option="USER_ENTERED",
    )

    # Formato: montos en rojo para que se vean como gastos
    monto_range = f"F{next_row}:F{next_row + len(rows) - 1}"
    worksheet.format(monto_range, {
        "textFormat": {"foregroundColor": {"red": 0.8, "green": 0.0, "blue": 0.0}},
        "numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"},
    })

    log.info(f"Agregadas {len(rows)} filas de gastos desde fila {next_row}")


# ─────────────────────────────────────────────────────────────────────────────
# AMAZON SP-API — FINANCES
# ─────────────────────────────────────────────────────────────────────────────

def get_service_fees_by_group(finances, since: datetime) -> list:
    """
    Obtiene ServiceFeeEvents con fechas correctas usando financial event groups.
    Cada grupo tiene una fecha de inicio → la usamos como fecha del fee.
    """
    since_iso = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    enriched_events = []

    try:
        # Obtener todos los grupos financieros desde la fecha
        resp = finances.list_financial_event_groups(
            FinancialEventGroupStartedAfter=since_iso,
            MaxResultsPerPage=100,
        )
        groups = resp.payload.get("FinancialEventGroupList", []) or []
        log.info(f"  Grupos financieros encontrados: {len(groups)}")

        for group in groups:
            group_id   = group.get("FinancialEventGroupId", "")
            group_date = _parse_fecha(group.get("FinancialEventGroupStart", ""))
            currency   = group.get("OriginalTotal", {}).get("CurrencyCode", "USD")

            # Solo procesar grupos en USD (ignorar CAD, MXN vacíos)
            if currency != "USD":
                continue

            time.sleep(0.3)
            try:
                events_resp = finances.list_financial_events_by_group_id(
                    event_group_id=group_id,
                    MaxResultsPerPage=100,
                )
                svc_events = (
                    events_resp.payload
                    .get("FinancialEvents", {})
                    .get("ServiceFeeEventList", []) or []
                )
                for ev in svc_events:
                    # Inyectar fecha del grupo y group_id para deduplicación
                    ev["_group_date"] = group_date
                    ev["_group_id"]   = group_id
                    enriched_events.append(ev)

            except SellingApiException as e:
                log.warning(f"  Error obteniendo eventos del grupo {group_id}: {e}")

    except SellingApiException as e:
        log.error(f"Error obteniendo grupos financieros: {e}")

    log.info(f"  Total ServiceFeeEvents con fecha: {len(enriched_events)}")
    return enriched_events


def get_all_financial_events(since: datetime) -> dict:
    """Obtiene TODOS los tipos de eventos financieros desde una fecha."""
    finances = FinancesV0(credentials=AMAZON_CREDENTIALS, marketplace=MARKETPLACE)

    since_iso = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    until_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    log.info(f"Obteniendo eventos financieros desde {since_iso}...")

    all_data = {
        "ShipmentEventList":               [],  # Fees por venta (Commission, FBA)
        "ServiceFeeEventList":             [],  # Tarifas — se llenan vía grupos (con fecha)
        "RefundEventList":                 [],  # Devoluciones
        "AdjustmentEventList":             [],  # Ajustes y reembolsos de Amazon
        "AdvertisingTransactionEventList": [],  # Publicidad PPC (nuevo)
        "ProductAdsPaymentEventList":      [],  # Publicidad PPC (legacy)
        "SellerDealPaymentEventList":      [],  # Deals y promociones
        "CouponPaymentEventList":          [],  # Cupones
    }

    # ── Eventos por rango de fechas (todos excepto ServiceFee) ──
    next_token = None
    page = 1
    while True:
        try:
            if next_token:
                response = finances.list_financial_events(NextToken=next_token)
            else:
                response = finances.list_financial_events(
                    PostedAfter=since_iso,
                    PostedBefore=until_iso,
                    MaxResultsPerPage=100,
                )
            payload = response.payload.get("FinancialEvents", {})

            for key in all_data:
                if key == "ServiceFeeEventList":
                    continue  # ServiceFee se obtiene via grupos
                events = payload.get(key, []) or []
                all_data[key].extend(events)

            totals = {k: len(v) for k, v in all_data.items() if v}
            log.info(f"  Pagina {page}: {totals}")

            next_token = response.payload.get("NextToken")
            if not next_token:
                break
            page += 1
            time.sleep(0.5)

        except SellingApiException as e:
            log.error(f"Error SP-API Finances: {e}")
            break

    # ── ServiceFeeEvents con fechas correctas via grupos ──
    log.info("Obteniendo ServiceFeeEvents con fechas por grupo...")
    all_data["ServiceFeeEventList"] = get_service_fees_by_group(finances, since)

    for k, v in all_data.items():
        log.info(f"  Total {k}: {len(v)}")
    return all_data


def _parse_fecha(date_str: str) -> str:
    """Convierte fecha ISO a string YYYY-MM-DD en zona Bogota."""
    try:
        return datetime.fromisoformat(
            date_str.replace("Z", "+00:00")
        ).astimezone(BOGOTA_TZ).strftime("%Y-%m-%d")
    except Exception:
        return date_str[:10] if date_str else "N/A"


def _get_monto(amount_info: dict) -> float:
    if not amount_info:
        return 0.0
    return float(amount_info.get("CurrencyAmount", amount_info.get("Amount", 0)))


def parse_events_to_rows(all_data: dict, existing_ids: set) -> list:
    """Convierte todos los eventos financieros al formato de la hoja."""
    rows = []
    new_count = 0
    skip_count = 0

    # ── 1. ShipmentEventList: fees por venta (Commission, FBA fulfillment) ──
    for event in all_data.get("ShipmentEventList", []):
        order_id = event.get("AmazonOrderId", "N/A")
        fecha = _parse_fecha(event.get("PostedDate", ""))

        for item in event.get("ShipmentItemList", []):
            sku = item.get("SellerSKU", "N/A")
            for fee in item.get("ItemFeeList", []):
                fee_type = fee.get("FeeType", "Unknown")
                monto = _get_monto(fee.get("FeeAmount", {}))
                if monto == 0:
                    continue
                txn_id = f"{order_id}-{sku}-{fee_type}"
                if txn_id in existing_ids:
                    skip_count += 1
                    continue
                rows.append([txn_id, fecha, order_id, fee_type, sku,
                              round(monto, 2), FEE_LABELS.get(fee_type, fee_type)])
                new_count += 1

    # ── 2. ServiceFeeEventList: Tarifas Logistica FBA, envio a warehouse ──
    for event in all_data.get("ServiceFeeEventList", []):
        sku         = event.get("SellerSKU", "") or event.get("ASIN", "") or "N/A"
        order_id    = event.get("AmazonOrderId", "")
        description = event.get("FeeDescription", event.get("FeeReason", "Tarifa de servicio"))
        # Fecha: viene inyectada del grupo financiero
        fecha       = event.get("_group_date", "N/A")
        group_id    = event.get("_group_id", "")

        for fee in event.get("FeeList", []):
            fee_type = fee.get("FeeType", "ServiceFee")
            monto    = _get_monto(fee.get("FeeAmount", {}))
            if monto == 0:
                continue

            # Clave única: si tiene OrderId propio lo usamos, si no usamos group_id
            if order_id:
                txn_id = f"SVC-{order_id}-{fee_type}"
            else:
                txn_id = f"SVC-GRP-{group_id[:16]}-{fee_type}"

            if txn_id in existing_ids:
                skip_count += 1
                continue

            label = FEE_LABELS.get(fee_type, description[:40])
            rows.append([txn_id, fecha, order_id or "N/A", fee_type, sku,
                         round(monto, 2), label])
            new_count += 1

    # ── 3. RefundEventList: devoluciones ──
    for event in all_data.get("RefundEventList", []):
        order_id = event.get("AmazonOrderId", "N/A")
        fecha = _parse_fecha(event.get("PostedDate", ""))

        for item in event.get("ShipmentItemAdjustmentList", []):
            sku = item.get("SellerSKU", "N/A")
            for fee in item.get("ItemFeeAdjustmentList", []):
                fee_type = fee.get("FeeType", "Refund")
                monto = _get_monto(fee.get("FeeAmount", {}))
                if monto == 0:
                    continue
                txn_id = f"REF-{order_id}-{sku}-{fee_type}"
                if txn_id in existing_ids:
                    skip_count += 1
                    continue
                rows.append([txn_id, fecha, order_id, f"Devolucion-{fee_type}", sku,
                             round(monto, 2), f"Devolucion: {FEE_LABELS.get(fee_type, fee_type)}"])
                new_count += 1

    # ── 4. AdjustmentEventList: ajustes y reembolsos de Amazon ──
    for event in all_data.get("AdjustmentEventList", []):
        adj_type = event.get("AdjustmentType", "Adjustment")
        fecha = _parse_fecha(event.get("PostedDate", ""))
        monto = _get_monto(event.get("AdjustmentAmount", {}))
        if monto == 0:
            continue
        txn_id = f"ADJ-{adj_type}-{fecha}-{monto}"
        if txn_id in existing_ids:
            skip_count += 1
            continue
        rows.append([txn_id, fecha, "N/A", adj_type, "N/A",
                     round(monto, 2), f"Ajuste: {adj_type}"])
        new_count += 1

    # ── 5. AdvertisingTransactionEventList: gastos de publicidad PPC ──
    for event in all_data.get("AdvertisingTransactionEventList", []):
        fecha = _parse_fecha(event.get("PostedDate", ""))
        invoice_id = event.get("InvoiceId", "N/A")
        txn_type = event.get("TransactionType", "charge")

        # El monto puede estar en BaseValue o en la suma de BaseValue + TaxValue
        base = _get_monto(event.get("BaseValue", {}))
        tax  = _get_monto(event.get("TaxValue", {}))
        monto = round(base + tax, 2)

        if monto == 0:
            continue

        txn_id = f"ADS-{invoice_id}-{fecha}-{txn_type}"
        if txn_id in existing_ids:
            skip_count += 1
            continue

        rows.append([txn_id, fecha, "N/A", "AdvertisingFee", "N/A",
                     round(monto, 2), f"Publicidad PPC: {invoice_id}"])
        new_count += 1

    # ── 6. ProductAdsPaymentEventList: publicidad PPC (legacy) ──
    for event in all_data.get("ProductAdsPaymentEventList", []):
        fecha = _parse_fecha(event.get("PostedDate", ""))
        # Si Amazon no devuelve fecha, usar la fecha del sync (hoy)
        if fecha == "N/A":
            fecha = datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d")
        invoice_id = event.get("invoiceId", event.get("InvoiceId", "N/A"))
        txn_type = event.get("transactionType", event.get("TransactionType", "charge"))
        base = _get_monto(event.get("baseValue", event.get("BaseValue", {})))
        tax  = _get_monto(event.get("taxValue", event.get("TaxValue", {})))
        monto = round(base + tax, 2)
        if monto == 0:
            continue
        # Usar N/A en el txn_id para mantener compatibilidad con filas ya guardadas
        txn_id = f"PADS-{invoice_id}-N/A-{txn_type}"
        if txn_id in existing_ids:
            skip_count += 1
            continue
        rows.append([txn_id, fecha, "N/A", "AdvertisingFee", "N/A",
                     round(monto, 2), f"Publicidad PPC: {invoice_id}"])
        new_count += 1

    # ── 7. SellerDealPaymentEventList: deals y promociones ──
    for event in all_data.get("SellerDealPaymentEventList", []):
        fecha = _parse_fecha(event.get("PostedDate", ""))
        deal_id = event.get("dealId", "N/A")
        fee_type = event.get("eventType", "DealFee")
        monto = _get_monto(event.get("feeAmount", {}))
        if monto == 0:
            continue
        txn_id = f"DEAL-{deal_id}-{fecha}-{fee_type}"
        if txn_id in existing_ids:
            skip_count += 1
            continue
        rows.append([txn_id, fecha, "N/A", fee_type, "N/A",
                     round(monto, 2), f"Deal/Promocion: {deal_id}"])
        new_count += 1

    # ── 8. CouponPaymentEventList: cargos por cupones ──
    for event in all_data.get("CouponPaymentEventList", []):
        fecha = _parse_fecha(event.get("PostedDate", ""))
        coupon_id = event.get("couponId", "N/A")
        fee_type = event.get("charge", {}).get("ChargeType", "CouponFee")
        monto = _get_monto(event.get("charge", {}).get("ChargeAmount", {}))
        if monto == 0:
            continue
        txn_id = f"CPN-{coupon_id}-{fecha}"
        if txn_id in existing_ids:
            skip_count += 1
            continue
        rows.append([txn_id, fecha, "N/A", fee_type, "N/A",
                     round(monto, 2), f"Cupon: {coupon_id}"])
        new_count += 1

    log.info(f"Fees procesados: {new_count} nuevos, {skip_count} ya existian")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync gastos/fees Amazon -> Google Sheets")
    parser.add_argument("--days", type=int, default=7, help="Dias hacia atras (default: 7)")
    parser.add_argument("--date", type=str, help="Fecha inicio YYYY-MM-DD")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("MORAES - Sync Gastos/Fees Amazon -> Google Sheets")
    log.info("=" * 60)

    # Rango de fechas
    if args.date:
        since = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=BOGOTA_TZ)
    else:
        since = datetime.now(BOGOTA_TZ) - timedelta(days=args.days)
    log.info(f"Sincronizando desde: {since.strftime('%Y-%m-%d')}")

    # Conectar a Sheets
    log.info("Conectando a Google Sheets...")
    gc = get_sheets_client()
    worksheet = setup_sheet(gc)

    # Obtener IDs existentes
    existing_ids = get_existing_transaction_ids(worksheet)
    log.info(f"Fees ya en Sheets: {len(existing_ids)}")

    # Obtener TODOS los eventos de Amazon
    all_data = get_all_financial_events(since)

    total_events = sum(len(v) for v in all_data.values())
    if total_events == 0:
        log.info("No hay eventos financieros en el periodo seleccionado.")
        ahora = datetime.now(BOGOTA_TZ)
        fecha_str = ahora.strftime("%d/%m/%Y %I:%M %p")
        total_en_sheet = len(existing_ids)
        send_telegram(
            f"<b>💸 MORAES — Sync Gastos Amazon</b>\n"
            f"<i>{fecha_str} (Bogotá)</i>\n"
            f"─────────────────────\n"
            f"✓ Sin gastos nuevos\n"
            f"📊 Total en sheet: {total_en_sheet} transacciones"
        )
        return

    # Convertir a filas
    rows = parse_events_to_rows(all_data, existing_ids)

    # Escribir en Sheets
    append_rows(worksheet, rows)

    # Resumen
    total_monto = sum(r[5] for r in rows)
    log.info("=" * 60)
    log.info(f"Sync completo: {len(rows)} fees nuevos agregados")
    log.info(f"Total fees del periodo: ${abs(total_monto):.2f} USD")
    log.info("=" * 60)

    # 7. Notificacion Telegram
    ahora = datetime.now(BOGOTA_TZ)
    fecha_str = ahora.strftime("%d/%m/%Y %I:%M %p")
    total_en_sheet = len(existing_ids) + len(rows)

    if rows:
        lineas = [
            f"<b>💸 MORAES — Sync Gastos Amazon</b>",
            f"<i>{fecha_str} (Bogotá)</i>",
            "─────────────────────",
            f"✅ {len(rows)} fee(s) nuevo(s)  →  <b>-${abs(total_monto):,.2f} USD</b>",
            f"📊 Total en sheet: {total_en_sheet} transacciones",
        ]
    else:
        lineas = [
            f"<b>💸 MORAES — Sync Gastos Amazon</b>",
            f"<i>{fecha_str} (Bogotá)</i>",
            "─────────────────────",
            f"✓ Sin gastos nuevos",
            f"📊 Total en sheet: {total_en_sheet} transacciones",
        ]

    send_telegram("\n".join(lineas))


if __name__ == "__main__":
    main()
