"""
automations/inventory_alerts.py
================================
Revisa el inventario FBA en Amazon y envia alertas por Email + Telegram
cuando algun producto baja del umbral de stock definido.

Uso:
    python automations/inventory_alerts.py
    python automations/inventory_alerts.py --threshold 15

Automatizacion diaria (Windows Task Scheduler):
    Programa   : C:/Python314/python.exe
    Argumentos : automations/inventory_alerts.py
    Iniciar en : C:/Users/Usuario/Desktop/Dashboard_Moraes
    Frecuencia : Diario 8:00 AM
"""

import os
import sys
import argparse
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from utils.amazon_client import CREDENTIALS, MARKETPLACE, validate_credentials
from utils.sheets_client import get_worksheet

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────

STOCK_THRESHOLD = 10        # Alerta cuando stock < este numero
SHEET_INVENTARIO = "Inventario"  # Nombre de la hoja en Google Sheets

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
            os.path.join(os.path.dirname(__file__), "..", "inventory_alerts_log.txt"),
            encoding="utf-8"
        ),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# AMAZON — INVENTARIO FBA
# ─────────────────────────────────────────────────────────────────────────────

def get_fba_inventory() -> list[dict]:
    """
    Obtiene el inventario FBA desde Amazon SP-API.
    Devuelve lista de dicts con: sku, asin, nombre, cantidad_disponible
    """
    from sp_api.api import Inventories

    log.info("Consultando inventario FBA en Amazon...")
    inventory_api = Inventories(credentials=CREDENTIALS, marketplace=MARKETPLACE)

    items = []

    try:
        resp = inventory_api.get_inventory_summary_marketplace()
        summaries = resp.payload if isinstance(resp.payload, list) else resp.payload.get("inventories", [])

        for item in summaries:
            qty = item.get("fulfillableQuantity", 0) or item.get("totalQuantity", 0) or 0
            items.append({
                "sku": item.get("sellerSku", ""),
                "asin": item.get("asin", ""),
                "nombre": item.get("productName", item.get("sellerSku", "")),
                "disponible": int(qty),
                "en_transito": item.get("inboundReceivingQuantity", 0) or 0,
            })

    except Exception as e:
        log.error(f"Error obteniendo inventario FBA: {e}")

    log.info(f"Total SKUs en FBA: {len(items)}")
    return items


def filter_low_stock(items: list[dict], threshold: int) -> list[dict]:
    """Filtra los productos por debajo del umbral."""
    return [i for i in items if i["disponible"] < threshold]

# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE SHEETS — ACTUALIZAR INVENTARIO
# ─────────────────────────────────────────────────────────────────────────────

def update_inventory_sheet(items: list[dict]):
    """
    Actualiza la hoja Inventario con los datos frescos de FBA.
    Busca cada SKU y actualiza la columna de stock FBA.
    """
    try:
        ws = get_worksheet(SHEET_INVENTARIO)
        headers = ws.row_values(1)

        # Buscar columnas clave
        if "SKU" not in headers or "Stock FBA" not in headers:
            log.warning(
                "Hoja Inventario no tiene columnas 'SKU' y 'Stock FBA'. "
                "Saltando actualizacion de Sheets."
            )
            return

        sku_col = headers.index("SKU") + 1
        stock_col = headers.index("Stock FBA") + 1
        fecha_col = headers.index("Ultima actualizacion") + 1 if "Ultima actualizacion" in headers else None

        all_skus = ws.col_values(sku_col)
        hoy = datetime.now().strftime("%Y-%m-%d %H:%M")

        updates = []
        for item in items:
            if item["sku"] in all_skus:
                row_idx = all_skus.index(item["sku"]) + 1
                updates.append({
                    "range": f"{chr(64 + stock_col)}{row_idx}",
                    "values": [[item["disponible"]]],
                })
                if fecha_col:
                    updates.append({
                        "range": f"{chr(64 + fecha_col)}{row_idx}",
                        "values": [[hoy]],
                    })

        if updates:
            ws.spreadsheet.values_update(
                f"{SHEET_INVENTARIO}",
                params={"valueInputOption": "USER_ENTERED"},
                body={"valueRanges": [
                    {"range": u["range"], "values": u["values"]} for u in updates
                ]},
            )
            log.info(f"Inventario actualizado en Sheets: {len(items)} SKUs")

    except Exception as e:
        log.warning(f"No se pudo actualizar hoja Inventario: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICACIONES
# ─────────────────────────────────────────────────────────────────────────────

def send_telegram(message: str):
    """Envia mensaje via Telegram Bot API."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram no configurado. Agrega TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID al .env")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            log.info("Alerta enviada por Telegram")
        else:
            log.error(f"Error Telegram: {resp.text}")
    except Exception as e:
        log.error(f"Error enviando Telegram: {e}")


def send_email(subject: str, body_html: str):
    """Envia email via Gmail SMTP."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        log.warning("Gmail no configurado. Agrega GMAIL_USER y GMAIL_APP_PASSWORD al .env")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        log.info("Alerta enviada por Email")
    except Exception as e:
        log.error(f"Error enviando email: {e}")


def build_alert_messages(low_stock: list[dict], threshold: int):
    """Construye los mensajes de alerta para Telegram y Email."""
    hoy = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── Telegram (texto plano con HTML basico) ──
    lines = [f"<b>MORAES - Alerta de Stock Bajo</b>", f"<i>{hoy}</i>", ""]
    for item in low_stock:
        emoji = "CRITICO" if item["disponible"] == 0 else "BAJO"
        lines.append(
            f"[{emoji}] <b>{item['sku']}</b>\n"
            f"   Stock: {item['disponible']} uds (umbral: {threshold})\n"
            f"   ASIN: {item['asin']}"
        )
    lines.append(f"\nTotal productos bajo stock: {len(low_stock)}")
    telegram_msg = "\n".join(lines)

    # ── Email (HTML) ──
    rows = ""
    for item in low_stock:
        color = "#ff4444" if item["disponible"] == 0 else "#ff9900"
        rows += f"""
        <tr>
            <td style="padding:8px;border:1px solid #ddd">{item['sku']}</td>
            <td style="padding:8px;border:1px solid #ddd">{item['asin']}</td>
            <td style="padding:8px;border:1px solid #ddd;color:{color};font-weight:bold">
                {item['disponible']}
            </td>
            <td style="padding:8px;border:1px solid #ddd">{item['en_transito']}</td>
        </tr>"""

    email_html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px">
    <h2 style="color:#e47911">MORAES - Alerta de Stock Bajo FBA</h2>
    <p>{hoy} | {len(low_stock)} producto(s) bajo {threshold} unidades</p>
    <table style="border-collapse:collapse;width:100%">
        <tr style="background:#f2f2f2">
            <th style="padding:8px;border:1px solid #ddd;text-align:left">SKU</th>
            <th style="padding:8px;border:1px solid #ddd;text-align:left">ASIN</th>
            <th style="padding:8px;border:1px solid #ddd;text-align:left">Stock Disponible</th>
            <th style="padding:8px;border:1px solid #ddd;text-align:left">En Transito</th>
        </tr>
        {rows}
    </table>
    <p style="color:#666;font-size:12px">
        Envia un envio a Amazon FBA cuando el stock baje del umbral.<br>
        Umbral configurado: {threshold} unidades
    </p>
    </body></html>
    """

    return telegram_msg, email_html

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MORAES - Alertas de inventario FBA")
    parser.add_argument("--threshold", type=int, default=STOCK_THRESHOLD,
                        help=f"Umbral de stock (default: {STOCK_THRESHOLD})")
    parser.add_argument("--test", action="store_true",
                        help="Envia una alerta de prueba sin revisar inventario real")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("MORAES - Revision de inventario FBA")
    log.info("=" * 60)

    validate_credentials()

    # Modo test: enviar alerta de prueba sin consultar Amazon
    if args.test:
        log.info("Modo TEST activado — enviando alerta de prueba...")
        test_items = [
            {"sku": "434-WINE-2B", "asin": "B0TEST1234", "disponible": 3, "en_transito": 0},
            {"sku": "5231-GOLF",   "asin": "B0TEST5678", "disponible": 0, "en_transito": 5},
        ]
        telegram_msg, email_html = build_alert_messages(test_items, args.threshold)
        send_telegram(telegram_msg)
        send_email(
            subject="[TEST] MORAES ALERTA: Prueba de notificaciones",
            body_html=email_html,
        )
        log.info("Alerta de prueba enviada. Revisa Telegram y tu correo.")
        return

    # 1. Obtener inventario de Amazon
    items = get_fba_inventory()
    if not items:
        log.info("No se encontro inventario FBA o error en la consulta.")
        return

    # 2. Actualizar hoja Inventario en Sheets
    update_inventory_sheet(items)

    # 3. Filtrar productos bajo umbral
    low_stock = filter_low_stock(items, args.threshold)

    if not low_stock:
        log.info(f"Todo bien. Ningun producto bajo {args.threshold} unidades.")
        return

    log.warning(f"ALERTA: {len(low_stock)} producto(s) bajo {args.threshold} unidades")
    for item in low_stock:
        log.warning(f"  - {item['sku']}: {item['disponible']} uds disponibles")

    # 4. Enviar alertas
    telegram_msg, email_html = build_alert_messages(low_stock, args.threshold)

    send_telegram(telegram_msg)
    send_email(
        subject=f"MORAES ALERTA: {len(low_stock)} producto(s) con stock bajo",
        body_html=email_html,
    )

    log.info("=" * 60)
    log.info("Revision completada.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
