"""
utils/sheets_client.py
======================
Cliente reutilizable de Google Sheets para todos los scripts de MORAES.
Importar desde cualquier script con:
    from utils.sheets_client import get_worksheet, append_rows
"""

import os
import gspread
from google.oauth2.service_account import Credentials

# ─── Configuración ────────────────────────────────────────────────────────────

SPREADSHEET_ID = "1TX0azfGSqKNRhMqKg_VS3iRHx0RMNPWnKGbq3Pwf8cQ"
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "..", "service_account.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ─── Funciones ────────────────────────────────────────────────────────────────

def get_client() -> gspread.Client:
    """Devuelve un cliente autenticado de gspread."""
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_worksheet(sheet_name: str) -> gspread.Worksheet:
    """Devuelve una hoja específica del spreadsheet de MORAES."""
    gc = get_client()
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    return spreadsheet.worksheet(sheet_name)


def append_rows(sheet_name: str, rows: list[list], value_input_option: str = "USER_ENTERED"):
    """
    Agrega filas al final de una hoja.
    Detecta automáticamente la última fila con datos.
    """
    if not rows:
        return 0

    worksheet = get_worksheet(sheet_name)
    col_a = worksheet.col_values(1)
    next_row = len(col_a) + 1

    worksheet.update(
        range_name=f"A{next_row}",
        values=rows,
        value_input_option=value_input_option,
    )
    return len(rows)


def get_all_values(sheet_name: str) -> list[list]:
    """Devuelve todos los valores de una hoja como lista de listas."""
    worksheet = get_worksheet(sheet_name)
    return worksheet.get_all_values()


def get_column_values(sheet_name: str, col_index: int) -> list:
    """Devuelve todos los valores de una columna (1-indexado)."""
    worksheet = get_worksheet(sheet_name)
    return worksheet.col_values(col_index)
