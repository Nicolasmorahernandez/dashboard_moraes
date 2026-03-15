"""
Dashboard MORAES — Streamlit + Google Sheets + Plotly
Conecta con el Google Sheet "Finanzas MORAES" y presenta 6 pestañas de análisis.

ESTRUCTURA REAL DEL SHEET:
- Vendidos: headers en fila 3, datos desde fila 4 (cols B-I)
- Modelo Unitario de Rentabilidad: headers en fila 1, datos normales
- Pedidos: headers en fila 3, datos desde fila 4
- proveedores: headers en fila 1, datos normales

Los valores monetarios vienen con formato "$1,234.56" y los porcentajes como "22.42%".
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import pathlib, re, base64
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_BOGOTA = ZoneInfo("America/Bogota")

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard MORAES",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════════════════
# PALETA DE COLORES PERSONALIZADA
# ══════════════════════════════════════════════════════════════════════════════
COLORS = {
    "primary": "#1e3a8a",       # Azul oscuro
    "primary_light": "#3b82f6", # Azul medio
    "secondary": "#10b981",     # Verde esmeralda
    "secondary_light": "#34d399",# Verde claro
    "accent": "#f59e0b",        # Naranja/ámbar
    "accent_light": "#fbbf24",  # Ámbar claro
    "negative": "#ef4444",      # Rojo
    "negative_light": "#f87171",# Rojo claro
    "bg_dark": "#0f172a",       # Slate muy oscuro
    "bg_card": "#1e293b",       # Slate oscuro
    "bg_card_hover": "#273548", # Slate medio para hover
    "text": "#f1f5f9",          # Gris muy claro
    "text_muted": "#94a3b8",    # Gris medio
    "border": "#334155",        # Slate medio
    "border_light": "#475569",  # Slate algo más claro
    "gradient_start": "#1e3a8a",# Inicio gradiente
    "gradient_end": "#7c3aed",  # Fin gradiente (violeta)
}

# Secuencias de colores para gráficos
COLOR_SEQ_PRIMARY = [
    COLORS["primary_light"], COLORS["secondary"], COLORS["accent"],
    COLORS["negative"], "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16",
]
COLOR_SEQ_PASTEL = [
    "#93c5fd", "#6ee7b7", "#fcd34d", "#fca5a5",
    "#c4b5fd", "#67e8f9", "#f9a8d4", "#bef264",
]
COLOR_POS_NEG = [COLORS["secondary"], COLORS["negative"]]


# ══════════════════════════════════════════════════════════════════════════════
# ESTILOS CSS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f"""
<style>
    /* ── Animaciones ──────────────────────────────────────── */
    @keyframes fadeInUp {{
        from {{ opacity: 0; transform: translateY(20px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes shimmer {{
        0%   {{ background-position: -200% 0; }}
        100% {{ background-position: 200% 0; }}
    }}
    @keyframes pulse {{
        0%, 100% {{ opacity: 1; }}
        50%      {{ opacity: 0.7; }}
    }}

    /* ── Body / Fondo principal ───────────────────────────── */
    .stApp {{
        background: linear-gradient(135deg, {COLORS['bg_dark']} 0%, #0c1220 50%, #111827 100%);
    }}

    /* ── Header fijo superior ─────────────────────────────── */
    .dashboard-header {{
        background: linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['gradient_end']} 100%);
        padding: 1.2rem 2rem;
        border-radius: 0 0 16px 16px;
        margin: -1rem -1rem 1.5rem -1rem;
        box-shadow: 0 4px 20px rgba(30, 58, 138, 0.4);
        animation: fadeInUp 0.6s ease-out;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}
    .dashboard-header h1 {{
        color: white;
        font-size: 1.8rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.02em;
    }}
    .dashboard-header .subtitle {{
        color: rgba(255,255,255,0.75);
        font-size: 0.85rem;
        margin-top: 4px;
    }}
    .header-badge {{
        background: rgba(255,255,255,0.15);
        backdrop-filter: blur(10px);
        padding: 6px 14px;
        border-radius: 20px;
        color: white;
        font-size: 0.75rem;
        font-weight: 500;
    }}

    /* ── Tarjetas de métricas con gradientes ───────────────── */
    [data-testid="stMetric"] {{
        background: linear-gradient(145deg, {COLORS['bg_card']} 0%, rgba(30,41,59,0.7) 100%);
        border: 1px solid {COLORS['border']};
        border-radius: 14px;
        padding: 18px 22px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.05);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        animation: fadeInUp 0.5s ease-out;
    }}
    [data-testid="stMetric"]:hover {{
        transform: translateY(-3px);
        box-shadow: 0 8px 30px rgba(30, 58, 138, 0.3), inset 0 1px 0 rgba(255,255,255,0.08);
        border-color: {COLORS['primary_light']};
    }}
    [data-testid="stMetric"] label {{
        font-size: 0.82rem;
        color: {COLORS['text_muted']} !important;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    [data-testid="stMetric"] [data-testid="stMetricValue"] {{
        font-size: 1.6rem;
        font-weight: 700;
        color: {COLORS['text']} !important;
    }}

    /* ── Tabs con transiciones suaves ─────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px;
        background: {COLORS['bg_card']};
        border-radius: 12px;
        padding: 4px;
        border: 1px solid {COLORS['border']};
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }}
    .stTabs [data-baseweb="tab"] {{
        padding: 10px 24px;
        border-radius: 10px;
        font-weight: 500;
        font-size: 0.85rem;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        color: {COLORS['text_muted']};
        border: none;
    }}
    .stTabs [data-baseweb="tab"]:hover {{
        background: rgba(59, 130, 246, 0.1);
        color: {COLORS['text']};
    }}
    .stTabs [aria-selected="true"] {{
        background: linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['gradient_end']} 100%) !important;
        color: white !important;
        box-shadow: 0 2px 10px rgba(30, 58, 138, 0.4);
    }}

    /* ── Selectbox y Multiselect ───────────────────────────── */
    [data-baseweb="select"] {{
        border-radius: 10px !important;
    }}
    [data-baseweb="select"] > div {{
        background: {COLORS['bg_card']} !important;
        border: 1px solid {COLORS['border']} !important;
        border-radius: 10px !important;
        transition: all 0.3s ease;
    }}
    [data-baseweb="select"] > div:hover {{
        border-color: {COLORS['primary_light']} !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
    }}

    /* ── DataFrames ────────────────────────────────────────── */
    [data-testid="stDataFrame"] {{
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid {COLORS['border']};
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    }}

    /* ── Expander ──────────────────────────────────────────── */
    [data-testid="stExpander"] {{
        background: {COLORS['bg_card']};
        border: 1px solid {COLORS['border']};
        border-left: 3px solid {COLORS['accent']};
        border-radius: 12px;
        transition: all 0.3s ease;
        margin-bottom: 8px;
    }}
    [data-testid="stExpander"]:hover {{
        border-left-color: {COLORS['primary_light']};
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    }}

    /* ── Botones de descarga ───────────────────────────────── */
    .stDownloadButton > button {{
        background: linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['primary_light']} 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 2px 10px rgba(30, 58, 138, 0.3) !important;
    }}
    .stDownloadButton > button:hover {{
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(30, 58, 138, 0.5) !important;
    }}

    /* ── Botón de actualizar ───────────────────────────────── */
    .stButton > button {{
        background: linear-gradient(135deg, {COLORS['bg_card']} 0%, rgba(30,41,59,0.8) 100%) !important;
        border: 1px solid {COLORS['border']} !important;
        border-radius: 10px !important;
        color: {COLORS['text']} !important;
        transition: all 0.3s ease !important;
        padding: 8px 20px !important;
    }}
    .stButton > button:hover {{
        border-color: {COLORS['primary_light']} !important;
        box-shadow: 0 0 15px rgba(59, 130, 246, 0.2) !important;
        transform: translateY(-1px) !important;
    }}

    /* ── Separadores elegantes ─────────────────────────────── */
    hr {{
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, {COLORS['border']}, transparent);
        margin: 1.5rem 0;
    }}

    /* ── Alertas personalizadas ────────────────────────────── */
    [data-testid="stAlert"] {{
        border-radius: 12px;
        border: none;
    }}

    /* ── Headers / Títulos ─────────────────────────────────── */
    .section-title {{
        font-size: 1.2rem;
        font-weight: 700;
        color: {COLORS['text']};
        padding-bottom: 8px;
        margin-bottom: 16px;
        border-bottom: 2px solid transparent;
        border-image: linear-gradient(90deg, {COLORS['primary_light']}, {COLORS['gradient_end']}) 1;
        animation: fadeInUp 0.5s ease-out;
    }}
    .section-subtitle {{
        font-size: 0.9rem;
        color: {COLORS['text_muted']};
        margin-bottom: 12px;
    }}

    /* ── Text input (buscador) ─────────────────────────────── */
    [data-testid="stTextInput"] input {{
        background: {COLORS['bg_card']} !important;
        border: 1px solid {COLORS['border']} !important;
        border-radius: 10px !important;
        color: {COLORS['text']} !important;
        transition: all 0.3s ease;
    }}
    [data-testid="stTextInput"] input:focus {{
        border-color: {COLORS['primary_light']} !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2) !important;
    }}

    /* ── Contenedor de contenido con fade-in ───────────────── */
    .element-container {{
        animation: fadeInUp 0.4s ease-out;
    }}

    /* ── Success / Error boxes ─────────────────────────────── */
    .stSuccess {{
        background: rgba(16, 185, 129, 0.1) !important;
        border-left: 4px solid {COLORS['secondary']} !important;
        border-radius: 10px !important;
    }}
    .stError {{
        background: rgba(239, 68, 68, 0.1) !important;
        border-left: 4px solid {COLORS['negative']} !important;
        border-radius: 10px !important;
    }}

    /* ── Ocultar elementos por defecto de Streamlit ────────── */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    header {{ visibility: hidden; }}

    /* ── Footer personalizado ──────────────────────────────── */
    .custom-footer {{
        background: linear-gradient(135deg, {COLORS['bg_card']} 0%, rgba(15,23,42,0.9) 100%);
        border-top: 1px solid {COLORS['border']};
        border-radius: 16px 16px 0 0;
        padding: 16px 24px;
        margin-top: 2rem;
        text-align: center;
        color: {COLORS['text_muted']};
        font-size: 0.8rem;
    }}
    .custom-footer a {{
        color: {COLORS['primary_light']};
        text-decoration: none;
    }}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE DISEÑO (helpers visuales)
# ══════════════════════════════════════════════════════════════════════════════
def _get_logo_b64() -> str:
    """Lee logo_moraes.png y lo devuelve como base64 para embeber en HTML."""
    logo_path = pathlib.Path(__file__).parent / "logo_moraes.png"
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""


def render_header():
    """Renderiza el header principal del dashboard."""
    now = datetime.now(tz=TZ_BOGOTA).strftime("%d/%m/%Y %H:%M")
    _logo_b64 = _get_logo_b64()
    if _logo_b64:
        _logo_html = (
            f'<img src="data:image/png;base64,{_logo_b64}" '
            f'style="width:52px; height:52px; border-radius:10px; '
            f'object-fit:cover; margin-right:14px; flex-shrink:0;">'
        )
    else:
        _logo_html = '<span style="font-size:2rem; margin-right:10px;">📊</span>'
    st.markdown(f"""
    <div class="dashboard-header">
        <div style="display:flex; align-items:center;">
            {_logo_html}
            <div>
                <h1 style="margin:0;">Dashboard MORAES</h1>
                <div class="subtitle">Analítica financiera en tiempo real · Google Sheets</div>
            </div>
        </div>
        <div class="header-badge">🕐 {now}</div>
    </div>
    """, unsafe_allow_html=True)


def section_title(icon: str, title: str, subtitle: str = ""):
    """Renderiza un título de sección estilizado."""
    sub_html = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(f"""
    <div class="section-title">{icon} {title}</div>
    {sub_html}
    """, unsafe_allow_html=True)


def styled_separator():
    """Separador visual elegante."""
    st.markdown("""
    <div style="margin: 1.5rem 0; height: 1px;
         background: linear-gradient(90deg, transparent, #334155, #3b82f6, #334155, transparent);">
    </div>
    """, unsafe_allow_html=True)


def render_footer():
    """Renderiza el footer personalizado."""
    now = datetime.now(tz=TZ_BOGOTA).strftime("%d/%m/%Y %H:%M:%S")
    st.markdown(f"""
    <div class="custom-footer">
        <strong>Dashboard MORAES</strong> · Datos actualizados desde Google Sheets cada 60s<br/>
        Última carga: {now} ·
        <a href="https://github.com/Nicolasmorahernandez/dashboard_moraes" target="_blank">GitHub</a>
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE GRÁFICOS (layout y tema consistente)
# ══════════════════════════════════════════════════════════════════════════════
def apply_chart_theme(fig, height: int = None):
    """Aplica el tema visual consistente a cualquier gráfico Plotly."""
    layout_args = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Inter, -apple-system, sans-serif",
            color=COLORS["text"],
            size=12,
        ),
        xaxis=dict(
            gridcolor="rgba(51,65,85,0.4)",
            gridwidth=1,
            zeroline=False,
            showline=True,
            linecolor=COLORS["border"],
            linewidth=1,
        ),
        yaxis=dict(
            gridcolor="rgba(51,65,85,0.4)",
            gridwidth=1,
            zeroline=False,
            showline=True,
            linecolor=COLORS["border"],
            linewidth=1,
        ),
        margin=dict(t=30, b=40, l=60, r=20),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(0,0,0,0)",
            font=dict(color=COLORS["text_muted"], size=11),
        ),
        hoverlabel=dict(
            bgcolor=COLORS["bg_card"],
            bordercolor=COLORS["border"],
            font=dict(color=COLORS["text"], size=13),
        ),
    )
    if height:
        layout_args["height"] = height
    fig.update_layout(**layout_args)
    return fig


# ── Constantes ───────────────────────────────────────────────────────────────
SPREADSHEET_NAME = "Finanzas MORAES"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
SA_FILE = pathlib.Path(__file__).parent / "service_account.json"

# Columnas esperadas por hoja (para detectar la fila de headers automáticamente)
EXPECTED_HEADERS = {
    "Vendidos": "Producto",
    "Pedidos": "Producto",
    "Modelo Unitario de Rentabilidad": "Producto",
    "proveedores": "Proveedor",
    "Ordenes Amazon": "Order ID",
}


# ── Conexión a Google Sheets ─────────────────────────────────────────────────
def get_gspread_client():
    """Autenticación con Service Account."""
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES
        )
    elif SA_FILE.exists():
        creds = Credentials.from_service_account_file(str(SA_FILE), scopes=SCOPES)
    else:
        st.error(
            "No se encontraron credenciales. "
            "En local: coloca service_account.json. "
            "En Streamlit Cloud: configura secrets."
        )
        st.stop()

    return gspread.authorize(creds)


def _find_header_row(all_values: list[list[str]], marker: str) -> int:
    """Busca la fila que contiene el marcador en cualquier celda (header real)."""
    for idx, row in enumerate(all_values):
        for cell in row:
            if marker.lower() in str(cell).lower():
                return idx
    return 0


def _clean_currency(val: str) -> float:
    """Limpia valores monetarios: '$40,000.00' -> 40000.0."""
    if pd.isna(val) or val is None:
        return 0.0
    s = str(val).strip()
    s = re.sub(r'[$ ]', '', s)
    s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _clean_pct(val: str) -> float:
    """Limpia porcentajes: '22.42%' -> 0.2242."""
    if pd.isna(val) or val is None:
        return 0.0
    s = str(val).strip().replace('%', '')
    try:
        v = float(s)
        if abs(v) > 5:
            return v / 100
        return v
    except ValueError:
        return 0.0


@st.cache_data(ttl=60)
def load_sheet(sheet_name: str) -> pd.DataFrame:
    """Carga una hoja del spreadsheet y devuelve un DataFrame limpio."""
    try:
        gc = get_gspread_client()
        spreadsheet = gc.open(SPREADSHEET_NAME)
        worksheet = spreadsheet.worksheet(sheet_name)

        all_values = worksheet.get_all_values()
        if not all_values:
            return pd.DataFrame()

        marker = EXPECTED_HEADERS.get(sheet_name, "Producto")
        header_idx = _find_header_row(all_values, marker)

        headers = all_values[header_idx]
        data = all_values[header_idx + 1:]

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=headers)
        df = df.loc[:, df.columns.str.strip() != ""]

        cols = df.columns.tolist()
        seen = {}
        new_cols = []
        for c in cols:
            c_clean = c.strip()
            if c_clean in seen:
                seen[c_clean] += 1
                new_cols.append(f"{c_clean}_{seen[c_clean]}")
            else:
                seen[c_clean] = 0
                new_cols.append(c_clean)
        df.columns = new_cols

        df = df.replace("", None)
        df = df.dropna(how="all")

        return df

    except gspread.exceptions.WorksheetNotFound:
        st.warning(f"Hoja **'{sheet_name}'** no encontrada en el spreadsheet.")
        return pd.DataFrame()
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"No se encontró el spreadsheet **'{SPREADSHEET_NAME}'**.")
        st.stop()
    except Exception as e:
        st.error(f"Error al cargar la hoja **'{sheet_name}'**: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_vendidos_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carga la hoja 'Vendidos' y la separa en dos DataFrames independientes.

    La hoja 'Vendidos' contiene DOS tablas lado a lado:
    - Izquierda (cols 1-8): Tabla de VENTAS
    - Derecha (cols 13-20): Tabla de GASTOS/COSTOS
    """
    try:
        gc = get_gspread_client()
        spreadsheet = gc.open(SPREADSHEET_NAME)
        worksheet = spreadsheet.worksheet("Vendidos")
        all_values = worksheet.get_all_values()

        if not all_values:
            return pd.DataFrame(), pd.DataFrame()

        header_idx = _find_header_row(all_values, "Producto")
        headers = all_values[header_idx]
        data = all_values[header_idx + 1:]

        if not data:
            return pd.DataFrame(), pd.DataFrame()

        # ── TABLA DE VENTAS (columnas 1-8) ────────
        ventas_cols_idx = list(range(1, 9))
        ventas_headers = [headers[i].strip() for i in ventas_cols_idx if i < len(headers)]
        ventas_data = []
        for row in data:
            vals = [row[i] if i < len(row) else "" for i in ventas_cols_idx]
            ventas_data.append(vals)

        df_ventas = pd.DataFrame(ventas_data, columns=ventas_headers)
        df_ventas = df_ventas.replace("", None)

        first_col = df_ventas.columns[0] if len(df_ventas.columns) > 0 else None
        if first_col:
            df_ventas = df_ventas.dropna(subset=[first_col])
            df_ventas = df_ventas[~df_ventas[first_col].str.strip().str.lower().isin(["total", ""])]

        # ── TABLA DE GASTOS (columnas 13-20) ────
        gastos_cols_idx = list(range(13, 21))
        gastos_headers = [headers[i].strip() for i in gastos_cols_idx if i < len(headers)]
        gastos_data = []
        for row in data:
            vals = [row[i] if i < len(row) else "" for i in gastos_cols_idx]
            gastos_data.append(vals)

        df_gastos = pd.DataFrame(gastos_data, columns=gastos_headers)
        df_gastos = df_gastos.replace("", None)

        first_gasto_col = df_gastos.columns[0] if len(df_gastos.columns) > 0 else None
        if first_gasto_col:
            df_gastos = df_gastos.dropna(subset=[first_gasto_col])
            df_gastos = df_gastos[df_gastos[first_gasto_col].str.strip() != ""]

        for df in [df_ventas, df_gastos]:
            cols = df.columns.tolist()
            seen = {}
            new_cols = []
            for c in cols:
                if c in seen:
                    seen[c] += 1
                    new_cols.append(f"{c}_{seen[c]}")
                else:
                    seen[c] = 0
                    new_cols.append(c)
            df.columns = new_cols

        return df_ventas, df_gastos

    except Exception as e:
        st.error(f"Error al cargar la hoja **'Vendidos'**: {e}")
        return pd.DataFrame(), pd.DataFrame()


# ── Meses en español → número ────────────────────────────────────────────────
MESES_ES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
    "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}


def _parse_fecha_gasto(val) -> pd.Timestamp:
    """Parsea 'ENERO 2026' o fechas estándar a Timestamp."""
    if pd.isna(val) or val is None:
        return pd.NaT
    s = str(val).strip().upper()
    parts = s.split()
    if len(parts) == 2 and parts[0] in MESES_ES:
        try:
            return pd.Timestamp(year=int(parts[1]), month=MESES_ES[parts[0]], day=1)
        except Exception:
            return pd.NaT
    return pd.to_datetime(val, dayfirst=True, errors="coerce")


# ── Funciones auxiliares ─────────────────────────────────────────────────────
def safe_numeric(df: pd.DataFrame, col: str) -> pd.Series:
    """Convierte columna a numérico, limpiando $ y comas primero."""
    if col not in df.columns:
        return pd.Series(dtype=float)
    return df[col].apply(_clean_currency)


def safe_pct(df: pd.DataFrame, col: str) -> pd.Series:
    """Convierte columna de porcentaje a decimal."""
    if col not in df.columns:
        return pd.Series(dtype=float)
    return df[col].apply(_clean_pct)


def fmt_usd(val: float) -> str:
    return f"${val:,.2f}"


def fmt_pct(val: float) -> str:
    return f"{val * 100:.1f}%"


def empty_warning(name: str):
    st.info(f"No hay datos disponibles en la hoja **{name}**.")


def col_exists(df: pd.DataFrame, col: str) -> str | None:
    """Busca columna con coincidencia parcial (case-insensitive)."""
    col_lower = col.lower()
    for c in df.columns:
        if col_lower in c.lower():
            return c
    return None


# ══════════════════════════════════════════════════════════════════════════════
# CARGA DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
render_header()

with st.spinner("⏳ Conectando con Google Sheets..."):
    df_vendidos, df_gastos_vendidos = load_vendidos_tables()
    df_rentabilidad = load_sheet("Modelo Unitario de Rentabilidad")
    df_pedidos = load_sheet("Pedidos")
    df_proveedores = load_sheet("proveedores")
    df_ordenes = load_sheet("Ordenes Amazon")

col_btn, col_space = st.columns([1, 5])
with col_btn:
    if st.button("🔄 Actualizar datos"):
        st.cache_data.clear()
        st.rerun()

styled_separator()

# ── Preprocesamiento — VENDIDOS ──────────────────────────────────────────────
COL_V_PRODUCTO = "Producto"
COL_V_CATEGORIA = col_exists(df_vendidos, "Categor") or "Categoría"
COL_V_FECHA = col_exists(df_vendidos, "Fecha de Venta") or "Fecha de Venta"
COL_V_CANTIDAD = col_exists(df_vendidos, "Cantidad Vendida") or "Cantidad Vendida"
COL_V_PRECIO = col_exists(df_vendidos, "Precio Unitario") or "Precio Unitario (USD)"
COL_V_INGRESO = col_exists(df_vendidos, "Ingreso Total") or "Ingreso Total (USD)"
COL_V_METODO_PAGO = col_exists(df_vendidos, "todo de Pago") or "Método de Pago"

if not df_vendidos.empty:
    if COL_V_CANTIDAD in df_vendidos.columns:
        df_vendidos[COL_V_CANTIDAD] = safe_numeric(df_vendidos, COL_V_CANTIDAD)
    if COL_V_PRECIO in df_vendidos.columns:
        df_vendidos[COL_V_PRECIO] = safe_numeric(df_vendidos, COL_V_PRECIO)
    if COL_V_INGRESO in df_vendidos.columns:
        df_vendidos[COL_V_INGRESO] = safe_numeric(df_vendidos, COL_V_INGRESO)
    if COL_V_FECHA in df_vendidos.columns:
        df_vendidos[COL_V_FECHA] = pd.to_datetime(
            df_vendidos[COL_V_FECHA], errors="coerce", dayfirst=True
        )
        df_vendidos["Mes"] = df_vendidos[COL_V_FECHA].dt.to_period("M").astype(str)

# ── Preprocesamiento — GASTOS ────────────────────────────────────────────────
COL_G_DESCRIPCION = col_exists(df_gastos_vendidos, "Descripci") or "Descripción del Costo"
COL_G_CATEGORIA = col_exists(df_gastos_vendidos, "Categor") or "Categoría del Gasto"
COL_G_FECHA = col_exists(df_gastos_vendidos, "Fecha de Pago") or "Fecha de Pago"
COL_G_MONTO = col_exists(df_gastos_vendidos, "Monto") or "Monto (USD)"
COL_G_PAGADO = col_exists(df_gastos_vendidos, "Pagado") or "¿Pagado?"
COL_G_PROVEEDOR = col_exists(df_gastos_vendidos, "Proveedor") or "Proveedor"

if not df_gastos_vendidos.empty:
    if COL_G_MONTO in df_gastos_vendidos.columns:
        df_gastos_vendidos[COL_G_MONTO] = safe_numeric(df_gastos_vendidos, COL_G_MONTO)
    if COL_G_FECHA in df_gastos_vendidos.columns:
        df_gastos_vendidos[COL_G_FECHA] = df_gastos_vendidos[COL_G_FECHA].apply(_parse_fecha_gasto)

# ── Preprocesamiento — RENTABILIDAD ──────────────────────────────────────────
COL_R_PRODUCTO = "Producto"
COL_R_METODO = col_exists(df_rentabilidad, "todo de venta") or "Método de venta"
COL_R_COMPRA_USD = col_exists(df_rentabilidad, "compra del producto (USD)") or "Precio de compra del producto (USD)"
COL_R_COSTO = col_exists(df_rentabilidad, "Costo Total") or "Costo Total"
COL_R_VENTA = col_exists(df_rentabilidad, "Precio de venta") or "Precio de venta (USD)"
COL_R_GANANCIA = col_exists(df_rentabilidad, "Ganancias") or "Ganancias (USD)"
COL_R_MARGIN = "MARGIN"
COL_R_ROI = "ROI"

if not df_rentabilidad.empty:
    for c in [COL_R_COMPRA_USD, COL_R_COSTO, COL_R_VENTA, COL_R_GANANCIA]:
        if c in df_rentabilidad.columns:
            df_rentabilidad[c] = safe_numeric(df_rentabilidad, c)
    for c in [COL_R_MARGIN, COL_R_ROI]:
        if c in df_rentabilidad.columns:
            df_rentabilidad[c] = safe_pct(df_rentabilidad, c)
    df_rentabilidad = df_rentabilidad.dropna(subset=[COL_R_PRODUCTO])
    df_rentabilidad = df_rentabilidad[df_rentabilidad[COL_R_PRODUCTO].str.strip() != ""]

# ── Preprocesamiento — PEDIDOS ───────────────────────────────────────────────
COL_P_REF = col_exists(df_pedidos, "Referencia") or "Referencia del Pedido"
COL_P_PRODUCTO = "Producto"
COL_P_PROVEEDOR = "Proveedor"
COL_P_CANTIDAD = col_exists(df_pedidos, "Cantidad Solicitada") or "Cantidad Solicitada"
COL_P_COSTO_TOTAL = col_exists(df_pedidos, "Costo Total Estimado") or "Costo Total Estimado (USD)"
COL_P_FECHA = col_exists(df_pedidos, "Fecha Estimada") or "Fecha Estimada de Llegada"
COL_P_CONFIRMADO = col_exists(df_pedidos, "Pedido Confirmado") or "¿Pedido Confirmado?"

if not df_pedidos.empty:
    if COL_P_CANTIDAD in df_pedidos.columns:
        df_pedidos[COL_P_CANTIDAD] = safe_numeric(df_pedidos, COL_P_CANTIDAD)
    if COL_P_COSTO_TOTAL in df_pedidos.columns:
        df_pedidos[COL_P_COSTO_TOTAL] = safe_numeric(df_pedidos, COL_P_COSTO_TOTAL)
    if COL_P_FECHA in df_pedidos.columns:
        df_pedidos[COL_P_FECHA] = pd.to_datetime(
            df_pedidos[COL_P_FECHA], errors="coerce", dayfirst=True
        )
    df_pedidos = df_pedidos.dropna(subset=[COL_P_PRODUCTO])
    df_pedidos = df_pedidos[df_pedidos[COL_P_PRODUCTO].str.strip() != ""]


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑAS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📈 Panel General",
    "💰 Rentabilidad",
    "🔀 Canales de Venta",
    "📦 Pedidos e Inventario",
    "🏷️ Costos por Producto",
    "🤝 Proveedores",
    "📦 Órdenes Amazon",
])


# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — Panel General
# ──────────────────────────────────────────────────────────────────────────────
with tab1:
    section_title("📈", "Panel General", "Resumen ejecutivo de ventas, gastos y rentabilidad")

    if df_vendidos.empty:
        empty_warning("Vendidos")
    else:
        ventas_totales = df_vendidos[COL_V_INGRESO].sum() if COL_V_INGRESO in df_vendidos.columns else 0
        gastos_totales = df_gastos_vendidos[COL_G_MONTO].sum() if not df_gastos_vendidos.empty and COL_G_MONTO in df_gastos_vendidos.columns else 0
        ganancia_neta = ventas_totales - gastos_totales
        cant_ventas = df_vendidos[COL_V_CANTIDAD].sum() if COL_V_CANTIDAD in df_vendidos.columns else 0
        ticket_promedio = ventas_totales / cant_ventas if cant_ventas > 0 else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("💵 Ventas Totales", fmt_usd(ventas_totales))
        k2.metric("📤 Gastos Totales", fmt_usd(gastos_totales))
        k3.metric(
            "📊 Ganancia Neta",
            fmt_usd(ganancia_neta),
            delta=fmt_usd(ganancia_neta),
            delta_color="normal",
        )
        k4.metric("🎫 Ticket Promedio", fmt_usd(ticket_promedio))

        styled_separator()

        # ── Preparación de datos Ventas vs Gastos (outer join para no perder meses) ──
        _vg_ventas_all = pd.DataFrame()
        _vg_gastos_raw = pd.DataFrame()
        _vg_has_gastos = False

        if "Mes" in df_vendidos.columns and COL_V_INGRESO in df_vendidos.columns:
            _vg_ventas_all = (
                df_vendidos.groupby("Mes")[COL_V_INGRESO]
                .sum().reset_index()
                .rename(columns={COL_V_INGRESO: "Ventas"})
            )
            if (
                not df_gastos_vendidos.empty
                and COL_G_FECHA in df_gastos_vendidos.columns
                and COL_G_MONTO in df_gastos_vendidos.columns
            ):
                _vg_gastos_raw = df_gastos_vendidos.dropna(subset=[COL_G_FECHA]).copy()
                _vg_gastos_raw["Mes"] = _vg_gastos_raw[COL_G_FECHA].dt.to_period("M").astype(str)
                _vg_has_gastos = True
                _vg_gastos_agg = (
                    _vg_gastos_raw.groupby("Mes")[COL_G_MONTO]
                    .sum().reset_index()
                    .rename(columns={COL_G_MONTO: "Gastos"})
                )
                # outer join: incluye meses con solo gastos (ej. nov 2025 sin ventas)
                _vg_ventas_all = _vg_ventas_all.merge(_vg_gastos_agg, on="Mes", how="outer")
                _vg_ventas_all["Ventas"] = _vg_ventas_all["Ventas"].fillna(0)
                _vg_ventas_all["Gastos"] = _vg_ventas_all["Gastos"].fillna(0)
            else:
                _vg_ventas_all["Gastos"] = 0
            _vg_ventas_all = _vg_ventas_all.sort_values("Mes").reset_index(drop=True)

        _vg_all_months = _vg_ventas_all["Mes"].tolist() if not _vg_ventas_all.empty else []
        _vg_sel = st.multiselect(
            "🗓️ Filtrar por mes",
            options=_vg_all_months,
            default=_vg_all_months,
            key="vg_meses",
        )
        _vg_data = (
            _vg_ventas_all[_vg_ventas_all["Mes"].isin(_vg_sel)]
            if _vg_sel else _vg_ventas_all
        )

        col_chart, col_top = st.columns([2, 1])

        with col_chart:
            section_title("📊", "Ventas vs Gastos", "Comparativa mensual de ingresos y egresos")
            if not _vg_ventas_all.empty:
                fig_vg = px.bar(
                    _vg_data, x="Mes", y=["Ventas", "Gastos"],
                    barmode="group", text_auto="$.2f",
                    color_discrete_sequence=[COLORS["secondary"], COLORS["negative"]],
                    labels={"value": "USD", "variable": ""},
                )
                apply_chart_theme(fig_vg)
                fig_vg.update_layout(
                    legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center"),
                    bargap=0.3,
                )
                fig_vg.update_traces(marker_line_width=0, marker_cornerradius=6)
                st.plotly_chart(fig_vg, use_container_width=True)
            else:
                st.info("No hay datos de fecha para graficar por mes.")

        with col_top:
            # ── Top 3: usa datos filtrados si hay filtro activo ───────────────
            _vg_filtered = bool(_vg_sel) and set(_vg_sel) != set(_vg_all_months)
            _df_top_base = (
                df_vendidos[df_vendidos["Mes"].isin(_vg_sel)]
                if _vg_filtered and "Mes" in df_vendidos.columns
                else df_vendidos
            )
            _top_subtitle = (
                f"Período: {', '.join(_vg_sel)}" if _vg_filtered else "Por cantidad vendida"
            )
            section_title("🏆", "Top 3 Productos", _top_subtitle)
            if COL_V_CANTIDAD in _df_top_base.columns and not _df_top_base.empty:
                _top_total = _df_top_base[COL_V_CANTIDAD].sum()
                top3 = (
                    _df_top_base.groupby(COL_V_PRODUCTO)[COL_V_CANTIDAD]
                    .sum()
                    .sort_values(ascending=False)
                    .head(3)
                    .reset_index()
                )
                medals = ["🥇", "🥈", "🥉"]
                for i, row in top3.iterrows():
                    medal = medals[i] if i < 3 else ""
                    pct = (row[COL_V_CANTIDAD] / _top_total * 100) if _top_total > 0 else 0
                    st.markdown(f"""
                    <div style="background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']};
                         border-radius: 10px; padding: 12px 16px; margin-bottom: 8px;
                         transition: all 0.3s ease;">
                        <div style="font-size: 1.1rem; font-weight: 600; color: {COLORS['text']};">
                            {medal} {row[COL_V_PRODUCTO]}
                        </div>
                        <div style="color: {COLORS['text_muted']}; font-size: 0.85rem; margin-top: 4px;">
                            {int(row[COL_V_CANTIDAD])} unidades · {pct:.1f}% del total
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            elif _vg_filtered:
                st.info("Sin ventas en el período seleccionado.")

        # ── Tortas por período cuando hay filtro activo ───────────────────────
        _vg_filtered = bool(_vg_sel) and set(_vg_sel) != set(_vg_all_months)
        if _vg_filtered and not _vg_data.empty:
            styled_separator()
            meses_label = ", ".join(_vg_sel)
            section_title("🥧", "Desglose del período seleccionado", meses_label)
            pie_v, pie_g = st.columns(2)

            with pie_v:
                section_title("💚", "Ventas por Producto")
                df_v_filt = df_vendidos[df_vendidos["Mes"].isin(_vg_sel)]
                if not df_v_filt.empty and COL_V_INGRESO in df_v_filt.columns:
                    vp = df_v_filt.groupby(COL_V_PRODUCTO)[COL_V_INGRESO].sum().reset_index()
                    fig_pv = px.pie(
                        vp, names=COL_V_PRODUCTO, values=COL_V_INGRESO,
                        hole=0.5, color_discrete_sequence=COLOR_SEQ_PRIMARY,
                    )
                    apply_chart_theme(fig_pv, height=380)
                    fig_pv.update_traces(
                        textinfo="percent+label",
                        textfont=dict(size=11, color=COLORS["text"]),
                        marker=dict(line=dict(color=COLORS["bg_dark"], width=2)),
                        pull=[0.03] * len(vp),
                    )
                    st.plotly_chart(fig_pv, use_container_width=True)

            with pie_g:
                section_title("🔴", "Gastos por Categoría")
                if (
                    _vg_has_gastos
                    and not _vg_gastos_raw.empty
                    and COL_G_CATEGORIA in _vg_gastos_raw.columns
                ):
                    df_g_filt = _vg_gastos_raw[_vg_gastos_raw["Mes"].isin(_vg_sel)]
                    if not df_g_filt.empty:
                        gp = df_g_filt.groupby(COL_G_CATEGORIA)[COL_G_MONTO].sum().reset_index()
                        fig_pg = px.pie(
                            gp, names=COL_G_CATEGORIA, values=COL_G_MONTO,
                            hole=0.5,
                            color_discrete_sequence=[
                                COLORS["negative"], COLORS["accent"],
                                COLORS["primary_light"], "#8b5cf6",
                                "#06b6d4", "#ec4899",
                            ],
                        )
                        apply_chart_theme(fig_pg, height=380)
                        fig_pg.update_traces(
                            textinfo="percent+label",
                            textfont=dict(size=11, color=COLORS["text"]),
                            marker=dict(line=dict(color=COLORS["bg_dark"], width=2)),
                            pull=[0.03] * len(gp),
                        )
                        st.plotly_chart(fig_pg, use_container_width=True)

        styled_separator()

        # Gráfico de pastel: distribución de gastos por categoría
        section_title("🥧", "Distribución de Gastos", "Desglose por categoría de gasto")
        if not df_gastos_vendidos.empty and COL_G_CATEGORIA in df_gastos_vendidos.columns and COL_G_MONTO in df_gastos_vendidos.columns:
            gastos_cat = (
                df_gastos_vendidos.dropna(subset=[COL_G_CATEGORIA])
                .groupby(COL_G_CATEGORIA)[COL_G_MONTO]
                .sum()
                .reset_index()
            )
            if not gastos_cat.empty:
                col_pie, col_detail = st.columns([2, 1])
                with col_pie:
                    fig_pie = px.pie(
                        gastos_cat, names=COL_G_CATEGORIA, values=COL_G_MONTO,
                        hole=0.5, color_discrete_sequence=COLOR_SEQ_PRIMARY,
                    )
                    apply_chart_theme(fig_pie, height=400)
                    fig_pie.update_traces(
                        textinfo="percent+label",
                        textfont=dict(size=12, color=COLORS["text"]),
                        marker=dict(line=dict(color=COLORS["bg_dark"], width=2)),
                        pull=[0.03] * len(gastos_cat),
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)

                with col_detail:
                    st.markdown(f"<br>", unsafe_allow_html=True)
                    for _, row in gastos_cat.sort_values(COL_G_MONTO, ascending=False).iterrows():
                        pct = (row[COL_G_MONTO] / gastos_totales * 100) if gastos_totales > 0 else 0
                        st.markdown(f"""
                        <div style="background: {COLORS['bg_card']}; border-left: 3px solid {COLORS['primary_light']};
                             border-radius: 8px; padding: 10px 14px; margin-bottom: 6px;">
                            <div style="font-weight: 600; color: {COLORS['text']}; font-size: 0.9rem;">
                                {row[COL_G_CATEGORIA]}
                            </div>
                            <div style="color: {COLORS['accent']}; font-weight: 700; font-size: 1rem;">
                                {fmt_usd(row[COL_G_MONTO])} <span style="color: {COLORS['text_muted']}; font-size: 0.8rem;">({pct:.1f}%)</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
        else:
            st.info("No hay datos de gastos disponibles para el gráfico.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — Rentabilidad
# ──────────────────────────────────────────────────────────────────────────────
with tab2:
    section_title("💰", "Análisis de Rentabilidad", "ROI, márgenes y ganancias por producto y canal")

    if df_rentabilidad.empty:
        empty_warning("Modelo Unitario de Rentabilidad")
    else:
        f1, f2 = st.columns(2)
        productos_list = df_rentabilidad[COL_R_PRODUCTO].dropna().unique().tolist()
        metodos_list = (
            df_rentabilidad[COL_R_METODO].dropna().unique().tolist()
            if COL_R_METODO in df_rentabilidad.columns else []
        )

        with f1:
            sel_prod = st.multiselect(
                "Filtrar por Producto", options=productos_list,
                default=productos_list, key="rent_prod",
            )
        with f2:
            sel_met = st.multiselect(
                "Filtrar por Método de Venta", options=metodos_list,
                default=metodos_list, key="rent_met",
            )

        df_r = df_rentabilidad.copy()
        if sel_prod:
            df_r = df_r[df_r[COL_R_PRODUCTO].isin(sel_prod)]
        if sel_met and COL_R_METODO in df_r.columns:
            df_r = df_r[df_r[COL_R_METODO].isin(sel_met)]

        if df_r.empty:
            st.warning("No hay datos con los filtros seleccionados.")
        else:
            roi_prom = df_r[COL_R_ROI].mean() if COL_R_ROI in df_r.columns else 0
            margin_prom = df_r[COL_R_MARGIN].mean() if COL_R_MARGIN in df_r.columns else 0
            ganancia_prom = df_r[COL_R_GANANCIA].mean() if COL_R_GANANCIA in df_r.columns else 0
            precio_venta_prom = df_r[COL_R_VENTA].mean() if COL_R_VENTA in df_r.columns else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📈 ROI Promedio", fmt_pct(roi_prom))
            m2.metric("📊 MARGIN Promedio", fmt_pct(margin_prom))
            m3.metric("💵 Ganancia Unit. Prom.", fmt_usd(ganancia_prom))
            m4.metric("🏷️ Precio Venta Prom.", fmt_usd(precio_venta_prom))

            styled_separator()

            gc1, gc2 = st.columns(2)

            with gc1:
                section_title("📈", "ROI por Producto y Método")
                fig_roi = px.bar(
                    df_r, x=COL_R_PRODUCTO, y=COL_R_ROI,
                    color=COL_R_METODO if COL_R_METODO in df_r.columns else None,
                    barmode="group",
                    text=df_r[COL_R_ROI].apply(lambda v: f"{v*100:.1f}%"),
                    color_discrete_sequence=[COLORS["secondary"], COLORS["primary_light"], COLORS["accent"]],
                    hover_data=[COL_R_GANANCIA, COL_R_VENTA] if COL_R_GANANCIA in df_r.columns else None,
                )
                apply_chart_theme(fig_roi)
                fig_roi.update_xaxes(tickangle=-45)
                fig_roi.update_traces(marker_cornerradius=5)
                st.plotly_chart(fig_roi, use_container_width=True)

            with gc2:
                section_title("📊", "MARGIN por Producto y Método")
                fig_mar = px.bar(
                    df_r, x=COL_R_PRODUCTO, y=COL_R_MARGIN,
                    color=COL_R_METODO if COL_R_METODO in df_r.columns else None,
                    barmode="group",
                    text=df_r[COL_R_MARGIN].apply(lambda v: f"{v*100:.1f}%"),
                    color_discrete_sequence=[COLORS["accent"], COLORS["primary_light"], COLORS["secondary"]],
                    hover_data=[COL_R_GANANCIA, COL_R_COSTO] if COL_R_GANANCIA in df_r.columns else None,
                )
                apply_chart_theme(fig_mar)
                fig_mar.update_xaxes(tickangle=-45)
                fig_mar.update_traces(marker_cornerradius=5)
                st.plotly_chart(fig_mar, use_container_width=True)

            styled_separator()

            # Scatter plot: ROI vs MARGIN
            if COL_R_ROI in df_r.columns and COL_R_MARGIN in df_r.columns:
                section_title("🔍", "ROI vs MARGIN", "Análisis bidimensional de rentabilidad")
                fig_scatter = px.scatter(
                    df_r, x=COL_R_ROI, y=COL_R_MARGIN,
                    color=COL_R_PRODUCTO,
                    size=df_r[COL_R_GANANCIA].abs() if COL_R_GANANCIA in df_r.columns else None,
                    symbol=COL_R_METODO if COL_R_METODO in df_r.columns else None,
                    color_discrete_sequence=COLOR_SEQ_PRIMARY,
                    hover_data=[COL_R_PRODUCTO, COL_R_GANANCIA, COL_R_VENTA],
                    labels={COL_R_ROI: "ROI", COL_R_MARGIN: "MARGIN"},
                )
                apply_chart_theme(fig_scatter, height=400)
                fig_scatter.update_traces(marker=dict(line=dict(width=1, color=COLORS["border"])))
                st.plotly_chart(fig_scatter, use_container_width=True)

            styled_separator()

            # Tabla detallada
            section_title("📋", "Tabla Detallada")
            df_display = df_r.copy()
            if COL_R_ROI in df_display.columns:
                df_display[COL_R_ROI] = df_display[COL_R_ROI].apply(fmt_pct)
            if COL_R_MARGIN in df_display.columns:
                df_display[COL_R_MARGIN] = df_display[COL_R_MARGIN].apply(fmt_pct)
            for c in [COL_R_COMPRA_USD, COL_R_VENTA, COL_R_COSTO, COL_R_GANANCIA]:
                if c in df_display.columns:
                    df_display[c] = df_display[c].apply(fmt_usd)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            styled_separator()

            # Mejor y peor ROI
            if COL_R_ROI in df_r.columns:
                best = df_r.loc[df_r[COL_R_ROI].idxmax()]
                worst = df_r.loc[df_r[COL_R_ROI].idxmin()]
                b1, b2 = st.columns(2)
                with b1:
                    st.success(
                        f"🏆 **Mejor ROI:** {best[COL_R_PRODUCTO]} "
                        f"({best.get(COL_R_METODO, 'N/A')}) — {fmt_pct(best[COL_R_ROI])}"
                    )
                with b2:
                    st.error(
                        f"⚠️ **Peor ROI:** {worst[COL_R_PRODUCTO]} "
                        f"({worst.get(COL_R_METODO, 'N/A')}) — {fmt_pct(worst[COL_R_ROI])}"
                    )


# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — Comparación de Canales
# ──────────────────────────────────────────────────────────────────────────────
with tab3:
    section_title("🔀", "Comparación de Canales de Venta", "FBA vs FBM vs Directo: rentabilidad por canal")

    if df_rentabilidad.empty or COL_R_METODO not in df_rentabilidad.columns:
        empty_warning("Modelo Unitario de Rentabilidad")
    else:
        canales = df_rentabilidad[COL_R_METODO].dropna().unique().tolist()

        if not canales:
            st.info("No se encontraron canales de venta.")
        else:
            # Canal cards con íconos
            canal_icons = {"FBA": "📦", "FBM": "🚚", "DIRECTO": "🏪", "Directo": "🏪"}
            cols = st.columns(len(canales))
            for i, canal in enumerate(canales):
                sub = df_rentabilidad[df_rentabilidad[COL_R_METODO] == canal]
                icon = canal_icons.get(canal, "📊")
                with cols[i]:
                    st.markdown(f"""
                    <div style="text-align: center; background: {COLORS['bg_card']};
                         border: 1px solid {COLORS['border']}; border-radius: 14px;
                         padding: 20px 16px; margin-bottom: 16px;
                         border-top: 3px solid {[COLORS['primary_light'], COLORS['secondary'], COLORS['accent']][i % 3]};">
                        <div style="font-size: 2rem; margin-bottom: 8px;">{icon}</div>
                        <div style="font-size: 1.1rem; font-weight: 700; color: {COLORS['text']}; margin-bottom: 12px;">
                            {canal}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.metric("ROI Prom.", fmt_pct(sub[COL_R_ROI].mean()))
                    st.metric("MARGIN Prom.", fmt_pct(sub[COL_R_MARGIN].mean()))
                    st.metric("Ganancia Prom.", fmt_usd(sub[COL_R_GANANCIA].mean()))
                    st.metric("Productos", len(sub))

            styled_separator()

            agg = (
                df_rentabilidad.groupby(COL_R_METODO)
                .agg({COL_R_ROI: "mean", COL_R_MARGIN: "mean",
                      COL_R_GANANCIA: "sum", COL_R_COSTO: "sum"})
                .reset_index()
            )

            c1, c2 = st.columns(2)
            with c1:
                section_title("📈", "ROI Promedio por Canal")
                fig = px.bar(
                    agg, x=COL_R_METODO, y=COL_R_ROI,
                    text=agg[COL_R_ROI].apply(lambda v: f"{v*100:.1f}%"),
                    color=COL_R_METODO,
                    color_discrete_sequence=[COLORS["primary_light"], COLORS["secondary"], COLORS["accent"]],
                )
                apply_chart_theme(fig)
                fig.update_layout(showlegend=False)
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(fig, use_container_width=True)

            with c2:
                section_title("📊", "MARGIN Promedio por Canal")
                fig = px.bar(
                    agg, x=COL_R_METODO, y=COL_R_MARGIN,
                    text=agg[COL_R_MARGIN].apply(lambda v: f"{v*100:.1f}%"),
                    color=COL_R_METODO,
                    color_discrete_sequence=[COLORS["primary_light"], COLORS["secondary"], COLORS["accent"]],
                )
                apply_chart_theme(fig)
                fig.update_layout(showlegend=False)
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(fig, use_container_width=True)

            styled_separator()

            section_title("💰", "Ganancia vs Costo por Canal", "Comparativa de rentabilidad absoluta")
            fig_gc = px.bar(
                agg, x=COL_R_METODO,
                y=[COL_R_GANANCIA, COL_R_COSTO],
                barmode="group", text_auto="$.2f",
                color_discrete_sequence=[COLORS["secondary"], COLORS["negative"]],
                labels={"value": "USD", "variable": ""},
            )
            apply_chart_theme(fig_gc)
            fig_gc.update_layout(
                legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center"),
                bargap=0.3,
            )
            fig_gc.update_traces(marker_cornerradius=6)
            st.plotly_chart(fig_gc, use_container_width=True)

            styled_separator()

            p1, p2 = st.columns(2)
            canal_counts = df_rentabilidad.groupby(COL_R_METODO).size().reset_index(name="Unidades")
            with p1:
                section_title("📦", "Productos por Canal")
                fig = px.pie(canal_counts, names=COL_R_METODO, values="Unidades", hole=0.5)
                apply_chart_theme(fig, height=380)
                fig.update_traces(
                    textinfo="percent+label",
                    textfont=dict(size=12, color=COLORS["text"]),
                    marker=dict(
                        colors=[COLORS["primary_light"], COLORS["secondary"], COLORS["accent"]],
                        line=dict(color=COLORS["bg_dark"], width=2),
                    ),
                )
                st.plotly_chart(fig, use_container_width=True)

            ingresos_canal = (
                df_rentabilidad.groupby(COL_R_METODO)[COL_R_VENTA]
                .sum().reset_index().rename(columns={COL_R_VENTA: "Ingresos"})
            )
            with p2:
                section_title("💵", "Ingresos por Canal")
                fig = px.pie(ingresos_canal, names=COL_R_METODO, values="Ingresos", hole=0.5)
                apply_chart_theme(fig, height=380)
                fig.update_traces(
                    textinfo="percent+label",
                    textfont=dict(size=12, color=COLORS["text"]),
                    marker=dict(
                        colors=[COLORS["primary_light"], COLORS["secondary"], COLORS["accent"]],
                        line=dict(color=COLORS["bg_dark"], width=2),
                    ),
                )
                st.plotly_chart(fig, use_container_width=True)

            styled_separator()

            mejor_canal = agg.loc[agg[COL_R_ROI].idxmax(), COL_R_METODO]
            mejor_roi = agg.loc[agg[COL_R_ROI].idxmax(), COL_R_ROI]
            st.success(
                f"🎯 **Canal recomendado:** **{mejor_canal}** con el mejor ROI promedio de "
                f"**{fmt_pct(mejor_roi)}**"
            )


# ──────────────────────────────────────────────────────────────────────────────
# TAB 4 — Pedidos e Inventario
# ──────────────────────────────────────────────────────────────────────────────
with tab4:
    section_title("📦", "Pedidos e Inventario", "Seguimiento de pedidos, inversiones y llegadas estimadas")

    if df_pedidos.empty:
        empty_warning("Pedidos")
    else:
        # Estado de confirmación
        if COL_P_CONFIRMADO in df_pedidos.columns:
            df_pedidos["_confirmado"] = (
                df_pedidos[COL_P_CONFIRMADO]
                .astype(str).str.strip().str.upper()
                .isin(["SI", "SÍ", "YES", "TRUE", "VERDADERO", "1"])
            )
        else:
            df_pedidos["_confirmado"] = False

        total_pedidos = len(df_pedidos)
        confirmados = df_pedidos["_confirmado"].sum()
        pendientes = total_pedidos - confirmados
        inversion_total = df_pedidos[COL_P_COSTO_TOTAL].sum() if COL_P_COSTO_TOTAL in df_pedidos.columns else 0
        inversion_conf = (
            df_pedidos.loc[df_pedidos["_confirmado"], COL_P_COSTO_TOTAL].sum()
            if COL_P_COSTO_TOTAL in df_pedidos.columns else 0
        )

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("📋 Total Pedidos", total_pedidos)
        k2.metric("⏳ Pendientes", int(pendientes))
        k3.metric("💰 Inversión Total", fmt_usd(inversion_total))
        k4.metric("✅ Inversión Confirmada", fmt_usd(inversion_conf))

        styled_separator()

        f1, f2 = st.columns(2)
        with f1:
            estado_filtro = st.selectbox(
                "Estado", ["Todos", "Confirmados", "Pendientes"], key="ped_estado"
            )
        with f2:
            prod_ped = df_pedidos[COL_P_PRODUCTO].dropna().unique().tolist()
            sel_prod_ped = st.multiselect(
                "Producto", prod_ped, default=prod_ped, key="ped_prod"
            )

        df_p = df_pedidos.copy()
        if estado_filtro == "Confirmados":
            df_p = df_p[df_p["_confirmado"]]
        elif estado_filtro == "Pendientes":
            df_p = df_p[~df_p["_confirmado"]]
        if sel_prod_ped:
            df_p = df_p[df_p[COL_P_PRODUCTO].isin(sel_prod_ped)]

        if df_p.empty:
            st.warning("No hay pedidos con los filtros seleccionados.")
        else:
            # Inversión por producto
            if COL_P_COSTO_TOTAL in df_p.columns:
                section_title("💰", "Inversión por Producto")
                inv_prod = (
                    df_p.groupby(COL_P_PRODUCTO)[COL_P_COSTO_TOTAL]
                    .sum().sort_values(ascending=False).reset_index()
                )
                fig = px.bar(
                    inv_prod, x=COL_P_PRODUCTO, y=COL_P_COSTO_TOTAL,
                    text_auto="$.2f",
                    color=COL_P_PRODUCTO,
                    color_discrete_sequence=COLOR_SEQ_PRIMARY,
                )
                apply_chart_theme(fig)
                fig.update_layout(showlegend=False)
                fig.update_xaxes(tickangle=-45)
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(fig, use_container_width=True)

            styled_separator()

            # Tabla
            section_title("📋", "Detalle de Pedidos")
            df_tabla = df_p.copy()
            df_tabla["Estado"] = df_tabla["_confirmado"].map(
                {True: "✅ Confirmado", False: "⏳ Pendiente"}
            )
            cols_show = [c for c in df_tabla.columns if not c.startswith("_")]
            st.dataframe(df_tabla[cols_show], use_container_width=True, hide_index=True)

            styled_separator()

            # Timeline
            if COL_P_FECHA in df_p.columns:
                df_timeline = df_p.dropna(subset=[COL_P_FECHA])
                if not df_timeline.empty and COL_P_CANTIDAD in df_timeline.columns:
                    section_title("📅", "Timeline de Llegadas Estimadas")
                    fig_tl = px.scatter(
                        df_timeline,
                        x=COL_P_FECHA, y=COL_P_PRODUCTO,
                        size=COL_P_CANTIDAD, color=COL_P_PRODUCTO,
                        hover_data=[COL_P_PROVEEDOR, COL_P_COSTO_TOTAL] if COL_P_PROVEEDOR in df_timeline.columns else None,
                        size_max=40,
                        color_discrete_sequence=COLOR_SEQ_PRIMARY,
                    )
                    apply_chart_theme(fig_tl)
                    fig_tl.update_layout(
                        showlegend=False,
                        yaxis=dict(categoryorder="total ascending"),
                    )
                    fig_tl.update_traces(marker=dict(line=dict(width=1, color=COLORS["border"])))
                    st.plotly_chart(fig_tl, use_container_width=True)

            styled_separator()

            c1, c2 = st.columns([2, 1])
            with c1:
                if COL_P_CANTIDAD in df_p.columns:
                    section_title("📦", "Unidades por Producto")
                    uds = df_p.groupby(COL_P_PRODUCTO)[COL_P_CANTIDAD].sum().reset_index()
                    fig = px.pie(uds, names=COL_P_PRODUCTO, values=COL_P_CANTIDAD, hole=0.5)
                    apply_chart_theme(fig, height=380)
                    fig.update_traces(
                        textinfo="percent+label",
                        textfont=dict(size=12, color=COLORS["text"]),
                        marker=dict(
                            colors=COLOR_SEQ_PRIMARY[:len(uds)],
                            line=dict(color=COLORS["bg_dark"], width=2),
                        ),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            with c2:
                section_title("📊", "Resumen de Pedidos")
                st.markdown(f"<br>", unsafe_allow_html=True)
                if COL_P_CANTIDAD in df_p.columns:
                    st.metric("Total Unidades", int(df_p[COL_P_CANTIDAD].sum()))
                if COL_P_COSTO_TOTAL in df_p.columns:
                    st.metric("Costo Promedio/Pedido", fmt_usd(df_p[COL_P_COSTO_TOTAL].mean()))
                if COL_P_PROVEEDOR in df_p.columns:
                    st.metric("Proveedores", df_p[COL_P_PROVEEDOR].nunique())


# ──────────────────────────────────────────────────────────────────────────────
# TAB 5 — Costos por Producto
# ──────────────────────────────────────────────────────────────────────────────
with tab5:
    section_title("🏷️", "Costos por Producto", "Análisis detallado de la estructura de costos")

    if df_rentabilidad.empty:
        empty_warning("Modelo Unitario de Rentabilidad")
    else:
        f1, f2 = st.columns(2)
        prods_r = df_rentabilidad[COL_R_PRODUCTO].dropna().unique().tolist()
        canales_r = (
            df_rentabilidad[COL_R_METODO].dropna().unique().tolist()
            if COL_R_METODO in df_rentabilidad.columns else []
        )

        with f1:
            sel_prod_c = st.multiselect(
                "Producto", prods_r, default=prods_r, key="cost_prod"
            )
        with f2:
            sel_canal_c = st.multiselect(
                "Canal / Método", canales_r, default=canales_r, key="cost_canal"
            )

        df_c = df_rentabilidad.copy()
        if sel_prod_c:
            df_c = df_c[df_c[COL_R_PRODUCTO].isin(sel_prod_c)]
        if sel_canal_c and COL_R_METODO in df_c.columns:
            df_c = df_c[df_c[COL_R_METODO].isin(sel_canal_c)]

        if df_c.empty:
            st.warning("No hay datos con los filtros seleccionados.")
        else:
            costo_total = df_c[COL_R_COSTO].sum() if COL_R_COSTO in df_c.columns else 0
            productos_unicos = df_c[COL_R_PRODUCTO].nunique()
            items_costo = len(df_c)
            costo_promedio = df_c[COL_R_COSTO].mean() if COL_R_COSTO in df_c.columns else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("💰 Costo Total", fmt_usd(costo_total))
            m2.metric("📦 Productos Únicos", productos_unicos)
            m3.metric("📋 Ítems de Costo", items_costo)
            m4.metric("📊 Costo Promedio", fmt_usd(costo_promedio))

            styled_separator()

            c1, c2 = st.columns(2)
            with c1:
                if COL_R_METODO in df_c.columns:
                    section_title("🥧", "Distribución por Canal")
                    dist_canal = df_c.groupby(COL_R_METODO)[COL_R_COSTO].sum().reset_index()
                    fig = px.pie(dist_canal, names=COL_R_METODO, values=COL_R_COSTO, hole=0.5)
                    apply_chart_theme(fig, height=380)
                    fig.update_traces(
                        textinfo="percent+label",
                        textfont=dict(size=12, color=COLORS["text"]),
                        marker=dict(
                            colors=[COLORS["primary_light"], COLORS["secondary"], COLORS["accent"]],
                            line=dict(color=COLORS["bg_dark"], width=2),
                        ),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            with c2:
                section_title("📊", "Costos por Producto")
                cost_prod = (
                    df_c.groupby(COL_R_PRODUCTO)[COL_R_COSTO]
                    .sum().sort_values(ascending=False).reset_index()
                )
                fig = px.bar(
                    cost_prod, x=COL_R_PRODUCTO, y=COL_R_COSTO,
                    text_auto="$.2f",
                    color=COL_R_PRODUCTO,
                    color_discrete_sequence=COLOR_SEQ_PRIMARY,
                )
                apply_chart_theme(fig)
                fig.update_layout(showlegend=False)
                fig.update_xaxes(tickangle=-45)
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(fig, use_container_width=True)

            styled_separator()

            # Desglose por canal (solo si un producto seleccionado)
            if len(sel_prod_c) == 1 and COL_R_METODO in df_c.columns:
                section_title("📊", f"Desglose por Canal — {sel_prod_c[0]}")
                canales_prod = df_c[COL_R_METODO].dropna().unique().tolist()
                if canales_prod:
                    tabs_canal = st.tabs(canales_prod)
                    for tab_c, canal in zip(tabs_canal, canales_prod):
                        with tab_c:
                            sub = df_c[df_c[COL_R_METODO] == canal]
                            sc1, sc2, sc3, sc4 = st.columns(4)
                            sc1.metric("Costo Total", fmt_usd(sub[COL_R_COSTO].sum()))
                            sc2.metric("Ganancia", fmt_usd(sub[COL_R_GANANCIA].sum()))
                            sc3.metric("ROI", fmt_pct(sub[COL_R_ROI].mean()))
                            sc4.metric("MARGIN", fmt_pct(sub[COL_R_MARGIN].mean()))
                styled_separator()

            # Tabla completa
            section_title("📋", "Tabla Completa")
            df_cost_display = df_c.copy()
            for c in [COL_R_COMPRA_USD, COL_R_VENTA, COL_R_COSTO, COL_R_GANANCIA]:
                if c in df_cost_display.columns:
                    df_cost_display[c] = df_cost_display[c].apply(fmt_usd)
            for c in [COL_R_ROI, COL_R_MARGIN]:
                if c in df_cost_display.columns:
                    df_cost_display[c] = df_c[c].apply(fmt_pct)
            st.dataframe(df_cost_display, use_container_width=True, hide_index=True)

            csv = df_c.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Descargar CSV", csv, "costos_moraes.csv", "text/csv", key="dl_costos",
            )


# ──────────────────────────────────────────────────────────────────────────────
# TAB 6 — Proveedores
# ──────────────────────────────────────────────────────────────────────────────
with tab6:
    section_title("🤝", "Directorio de Proveedores", "Gestión de proveedores, contactos y confiabilidad")

    if df_proveedores.empty:
        empty_warning("proveedores")
    else:
        total_prov = len(df_proveedores)
        con_tel = (
            df_proveedores["Telefono"].dropna().astype(str).str.strip().ne("").sum()
            if "Telefono" in df_proveedores.columns else 0
        )
        tipo_principal = (
            df_proveedores["Tipo de proveedor"].mode().iloc[0]
            if "Tipo de proveedor" in df_proveedores.columns
            and not df_proveedores["Tipo de proveedor"].dropna().empty
            else "N/A"
        )

        m1, m2, m3 = st.columns(3)
        m1.metric("👥 Total Proveedores", total_prov)
        m2.metric("📞 Con Teléfono", int(con_tel))
        m3.metric("🏷️ Tipo Principal", tipo_principal)

        styled_separator()

        f1, f2 = st.columns(2)
        with f1:
            busqueda = st.text_input("🔍 Buscar proveedor", key="prov_search")
        with f2:
            tipos = (
                df_proveedores["Tipo de proveedor"].dropna().unique().tolist()
                if "Tipo de proveedor" in df_proveedores.columns else []
            )
            sel_tipo = st.multiselect("Filtrar por Tipo", tipos, default=tipos, key="prov_tipo")

        df_pv = df_proveedores.copy()
        if busqueda:
            mask = df_pv.apply(
                lambda row: busqueda.lower() in " ".join(row.astype(str)).lower(), axis=1
            )
            df_pv = df_pv[mask]
        if sel_tipo and "Tipo de proveedor" in df_pv.columns:
            df_pv = df_pv[df_pv["Tipo de proveedor"].isin(sel_tipo)]

        if df_pv.empty:
            st.warning("No se encontraron proveedores.")
        else:
            c1, c2 = st.columns([2, 1])
            with c1:
                if "Tipo de proveedor" in df_pv.columns:
                    section_title("📊", "Proveedores por Tipo")
                    tipo_count = df_pv.groupby("Tipo de proveedor").size().reset_index(name="Cantidad")
                    fig = px.pie(
                        tipo_count, names="Tipo de proveedor", values="Cantidad", hole=0.5,
                        color_discrete_sequence=COLOR_SEQ_PRIMARY,
                    )
                    apply_chart_theme(fig, height=380)
                    fig.update_traces(
                        textinfo="percent+label",
                        textfont=dict(size=12, color=COLORS["text"]),
                        marker=dict(line=dict(color=COLORS["bg_dark"], width=2)),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            with c2:
                section_title("🏆", "Más Usados en Pedidos")
                if not df_pedidos.empty and COL_P_PROVEEDOR in df_pedidos.columns:
                    top_prov = (
                        df_pedidos[COL_P_PROVEEDOR].value_counts().head(5).reset_index()
                    )
                    top_prov.columns = ["Proveedor", "Pedidos"]
                    for idx, row in top_prov.iterrows():
                        rank = idx + 1
                        st.markdown(f"""
                        <div style="background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']};
                             border-left: 3px solid {COLORS['secondary']};
                             border-radius: 8px; padding: 10px 14px; margin-bottom: 6px;">
                            <div style="font-weight: 600; color: {COLORS['text']}; font-size: 0.9rem;">
                                #{rank} {row['Proveedor']}
                            </div>
                            <div style="color: {COLORS['text_muted']}; font-size: 0.8rem;">
                                {row['Pedidos']} pedidos
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("No hay datos de pedidos para cruzar.")

            styled_separator()

            section_title("📇", "Detalle por Proveedor")
            for _, prov in df_pv.iterrows():
                nombre = prov.get("Proveedor", "Sin nombre")
                with st.expander(f"🏢 {nombre}"):
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        st.markdown(f"**Tipo:** {prov.get('Tipo de proveedor', 'N/A')}")
                        st.markdown(f"**Contacto:** {prov.get('Contacto', 'N/A')}")
                        st.markdown(f"**Teléfono:** {prov.get('Telefono', 'N/A')}")
                    with ec2:
                        st.markdown(f"**Sitio Web:** {prov.get('Sitio web', 'N/A')}")
                        st.markdown(f"**Confiabilidad:** {prov.get('Confiabilidad', 'N/A')}")
                        st.markdown(f"**Notas:** {prov.get('Notas', 'N/A')}")

            styled_separator()

            section_title("📋", "Vista de Tabla")
            st.dataframe(
                df_pv, use_container_width=True, hide_index=True,
                column_config={
                    "Sitio web": st.column_config.LinkColumn("Sitio Web"),
                    "Confiabilidad": st.column_config.TextColumn("Confiabilidad"),
                },
            )

            csv = df_pv.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Descargar CSV", csv, "proveedores_moraes.csv", "text/csv", key="dl_prov",
            )


# ──────────────────────────────────────────────────────────────────────────────
# TAB 7 — Órdenes Amazon
# ──────────────────────────────────────────────────────────────────────────────
with tab7:
    section_title("📦", "Órdenes Amazon", "Estado en tiempo real de tus órdenes Amazon")

    if df_ordenes.empty:
        empty_warning("Ordenes Amazon")
        st.info("Corre `python automations/sync_pedidos.py --setup` para crear la hoja y luego el sync diario.")
    else:
        # ── Preprocesamiento ─────────────────────────────────────────────────
        df_ord = df_ordenes.copy()

        # Normalizar columnas numéricas
        for col_n in ["Unidades", "Total (USD)"]:
            if col_n in df_ord.columns:
                df_ord[col_n] = pd.to_numeric(
                    df_ord[col_n].astype(str).str.replace("$", "").str.replace(",", ""),
                    errors="coerce"
                ).fillna(0)

        # Parsear fechas
        for col_d in ["Fecha Compra", "Fecha Envio", "Entrega Estimada"]:
            if col_d in df_ord.columns:
                df_ord[col_d] = pd.to_datetime(df_ord[col_d], errors="coerce")

        # Limpiar filas sin Order ID
        if "Order ID" in df_ord.columns:
            df_ord = df_ord[df_ord["Order ID"].notna() & (df_ord["Order ID"].str.strip() != "")]

        # ── Filtros ──────────────────────────────────────────────────────────
        f1, f2, f3 = st.columns(3)

        estados_disp = ["Todos"] + sorted(df_ord["Estado"].dropna().unique().tolist()) if "Estado" in df_ord.columns else ["Todos"]
        fulfil_disp  = ["Todos"] + sorted(df_ord["Fulfillment"].dropna().unique().tolist()) if "Fulfillment" in df_ord.columns else ["Todos"]

        with f1:
            sel_estado = st.selectbox("Estado", estados_disp, key="ord_estado")
        with f2:
            sel_fulfil = st.selectbox("Fulfillment", fulfil_disp, key="ord_fulfil")
        with f3:
            fecha_min = df_ord["Fecha Compra"].min() if "Fecha Compra" in df_ord.columns and df_ord["Fecha Compra"].notna().any() else None
            fecha_max = df_ord["Fecha Compra"].max() if "Fecha Compra" in df_ord.columns and df_ord["Fecha Compra"].notna().any() else None
            if fecha_min and fecha_max:
                rango = st.date_input(
                    "Rango de fechas",
                    value=(fecha_min.date(), fecha_max.date()),
                    key="ord_fechas",
                )
            else:
                rango = None

        df_f = df_ord.copy()
        if sel_estado != "Todos" and "Estado" in df_f.columns:
            df_f = df_f[df_f["Estado"] == sel_estado]
        if sel_fulfil != "Todos" and "Fulfillment" in df_f.columns:
            df_f = df_f[df_f["Fulfillment"] == sel_fulfil]
        if rango and len(rango) == 2 and "Fecha Compra" in df_f.columns:
            start_d = pd.Timestamp(rango[0])
            end_d   = pd.Timestamp(rango[1])
            df_f = df_f[(df_f["Fecha Compra"] >= start_d) & (df_f["Fecha Compra"] <= end_d)]

        styled_separator()

        # ── KPIs ─────────────────────────────────────────────────────────────
        total_ords    = len(df_f)
        total_uds     = int(df_f["Unidades"].sum())    if "Unidades"    in df_f.columns else 0
        total_usd     = df_f["Total (USD)"].sum()       if "Total (USD)" in df_f.columns else 0

        estado_counts = df_f["Estado"].value_counts().to_dict() if "Estado" in df_f.columns else {}
        n_pendiente   = estado_counts.get("Pendiente", 0)
        n_enviado     = estado_counts.get("Enviado", 0) + estado_counts.get("Enviado parcial", 0)
        n_entregado   = estado_counts.get("Entregado", 0)
        n_cancelado   = estado_counts.get("Cancelado", 0)

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total Órdenes",  total_ords)
        k2.metric("Pendiente",      n_pendiente)
        k3.metric("Enviado",        n_enviado)
        k4.metric("Entregado",      n_entregado)
        k5.metric("Cancelado",      n_cancelado)

        styled_separator()

        # ── Gráficos ─────────────────────────────────────────────────────────
        g1, g2 = st.columns(2)

        with g1:
            section_title("🍩", "Órdenes por Estado")
            if not df_f.empty and "Estado" in df_f.columns:
                estado_df = df_f["Estado"].value_counts().reset_index()
                estado_df.columns = ["Estado", "Cantidad"]
                color_map = {
                    "Pendiente":       COLORS["accent"],
                    "Enviado":         COLORS["primary_light"],
                    "Enviado parcial": COLORS["secondary_light"],
                    "Entregado":       COLORS["secondary"],
                    "Cancelado":       COLORS["negative"],
                    "No disponible":   COLORS["text_muted"],
                }
                fig_donut = px.pie(
                    estado_df, names="Estado", values="Cantidad",
                    hole=0.55,
                    color="Estado",
                    color_discrete_map=color_map,
                )
                fig_donut.update_traces(textposition="outside", textinfo="label+percent")
                fig_donut.update_layout(
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color=COLORS["text"],
                    margin=dict(t=20, b=20, l=20, r=20),
                )
                st.plotly_chart(fig_donut, use_container_width=True)
            else:
                st.info("Sin datos para mostrar.")

        with g2:
            section_title("📅", "Órdenes por Semana")
            if not df_f.empty and "Fecha Compra" in df_f.columns and df_f["Fecha Compra"].notna().any():
                df_time = df_f.dropna(subset=["Fecha Compra"]).copy()
                df_time["Semana"] = df_time["Fecha Compra"].dt.to_period("W").dt.start_time
                weekly = df_time.groupby("Semana").size().reset_index(name="Ordenes")
                fig_line = px.bar(
                    weekly, x="Semana", y="Ordenes",
                    color_discrete_sequence=[COLORS["primary_light"]],
                )
                fig_line.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color=COLORS["text"],
                    xaxis=dict(gridcolor=COLORS["border"]),
                    yaxis=dict(gridcolor=COLORS["border"]),
                    margin=dict(t=20, b=20, l=20, r=20),
                )
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("Sin datos de fechas para mostrar.")

        styled_separator()

        # ── Tabla detallada ──────────────────────────────────────────────────
        section_title("📋", "Detalle de Órdenes")

        cols_show = [c for c in [
            "Order ID", "Fecha Compra", "Producto", "SKU(s)",
            "Unidades", "Total (USD)", "Fulfillment", "Estado",
            "Marketplace", "Fecha Envio", "Entrega Estimada",
        ] if c in df_f.columns]

        df_tabla = df_f[cols_show].copy()

        # Formatear fechas para display
        for col_d in ["Fecha Compra", "Fecha Envio", "Entrega Estimada"]:
            if col_d in df_tabla.columns:
                df_tabla[col_d] = df_tabla[col_d].dt.strftime("%Y-%m-%d").where(df_tabla[col_d].notna(), "")

        st.dataframe(
            df_tabla,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Total (USD)": st.column_config.NumberColumn("Total (USD)", format="$%.2f"),
                "Unidades":    st.column_config.NumberColumn("Uds", format="%d"),
                "Estado":      st.column_config.TextColumn("Estado"),
            },
        )

        styled_separator()

        csv_ord = df_tabla.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Descargar CSV", csv_ord, "ordenes_amazon.csv", "text/csv", key="dl_ordenes"
        )


# ── Footer ───────────────────────────────────────────────────────────────────
styled_separator()
render_footer()
