"""
automations/setup_amazon_sheet.py
==================================
Crea y formatea la hoja "Ventas Amazon" en el spreadsheet de MORAES.
Correr UNA SOLA VEZ para dejar la hoja lista.

Uso:
    python automations/setup_amazon_sheet.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.sheets_client import get_client, SPREADSHEET_ID
import gspread

# ─── Configuracion ────────────────────────────────────────────────────────────

SHEET_NAME = "Ventas Amazon"

HEADERS = [
    "Order ID",
    "Fecha",
    "Producto",
    "ASIN",
    "SKU",
    "Cantidad",
    "Precio Unitario (USD)",
    "Ingreso Total (USD)",
    "Fulfillment",
    "Estado",
    "Marketplace",
]

# Anchos de columna en pixeles (aproximado en Google Sheets = chars * 7)
COL_WIDTHS = {
    0: 200,   # Order ID
    1: 110,   # Fecha
    2: 280,   # Producto
    3: 120,   # ASIN
    4: 140,   # SKU
    5: 90,    # Cantidad
    6: 160,   # Precio Unitario
    7: 155,   # Ingreso Total
    8: 100,   # Fulfillment
    9: 100,   # Estado
    10: 120,  # Marketplace
}

# ─── Funciones ────────────────────────────────────────────────────────────────

def create_or_get_sheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    """Crea la hoja si no existe, si ya existe la devuelve."""
    try:
        ws = spreadsheet.worksheet(SHEET_NAME)
        print(f"La hoja '{SHEET_NAME}' ya existe.")
        return ws
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=len(HEADERS))
        print(f"Hoja '{SHEET_NAME}' creada.")
        return ws


def setup_headers(ws: gspread.Worksheet):
    """Escribe el titulo y los headers con formato."""
    spreadsheet_id = ws.spreadsheet.id

    # Fila 1: Titulo
    ws.update(range_name="A1", values=[["VENTAS AMAZON - Sincronizado via SP-API"]])

    # Fila 2: vacia (separador)
    ws.update(range_name="A2", values=[[""]])

    # Fila 3: Headers
    ws.update(range_name="A3", values=[HEADERS])

    print("Headers escritos.")


def apply_formatting(ws: gspread.Worksheet, spreadsheet: gspread.Spreadsheet):
    """Aplica formato visual a la hoja."""
    sheet_id = ws.id

    requests = []

    # ── 1. Formato titulo (fila 1) ──────────────────────────────────────────
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0, "endRowIndex": 1,
                "startColumnIndex": 0, "endColumnIndex": len(HEADERS)
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.13, "green": 0.13, "blue": 0.13},
                    "textFormat": {
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        "fontSize": 12,
                        "bold": True
                    },
                    "horizontalAlignment": "LEFT"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
        }
    })

    # ── 2. Formato headers (fila 3) ─────────────────────────────────────────
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 2, "endRowIndex": 3,
                "startColumnIndex": 0, "endColumnIndex": len(HEADERS)
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.18, "green": 0.18, "blue": 0.18},
                    "textFormat": {
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        "fontSize": 10,
                        "bold": True
                    },
                    "horizontalAlignment": "CENTER"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
        }
    })

    # ── 3. Congelar fila 3 (headers siempre visibles) ───────────────────────
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 3}
            },
            "fields": "gridProperties.frozenRowCount"
        }
    })

    # ── 4. Anchos de columnas ────────────────────────────────────────────────
    for col_idx, width in COL_WIDTHS.items():
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": col_idx,
                    "endIndex": col_idx + 1
                },
                "properties": {"pixelSize": width},
                "fields": "pixelSize"
            }
        })

    # ── 5. Merge titulo en todas las columnas ────────────────────────────────
    requests.append({
        "mergeCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0, "endRowIndex": 1,
                "startColumnIndex": 0, "endColumnIndex": len(HEADERS)
            },
            "mergeType": "MERGE_ALL"
        }
    })

    spreadsheet.batch_update({"requests": requests})
    print("Formato aplicado.")


def main():
    print("=" * 50)
    print("MORAES - Setup hoja Ventas Amazon")
    print("=" * 50)

    gc = get_client()
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    ws = create_or_get_sheet(spreadsheet)
    setup_headers(ws)
    apply_formatting(ws, spreadsheet)

    print("=" * 50)
    print(f"Listo. Abre tu Sheet y busca la hoja '{SHEET_NAME}'")
    print("=" * 50)


if __name__ == "__main__":
    main()
