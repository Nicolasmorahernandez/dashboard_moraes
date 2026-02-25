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
import pathlib, re
from datetime import datetime

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard MORAES",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
# PALETA DE COLORES PERSONALIZADA
# ══════════════════════════════════════════════════════════════════════════════
COLORS = {
    "primary": "#1e3a8a",
    "primary_light": "#3b82f6",
    "secondary": "#10b981",
    "secondary_light": "#34d399",
    "accent": "#f59e0b",
    "accent_light": "#fbbf24",
    "negative": "#ef4444",
    "negative_light": "#f87171",
    "bg_dark": "#0f172a",
    "bg_card": "#1e293b",
    "bg_card_hover": "#273548",
    "text": "#f1f5f9",
    "text_muted": "#94a3b8",
    "border": "#334155",
    "border_light": "#475569",
    "gradient_start": "#1e3a8a",
    "gradient_end": "#7c3aed",
}

COLOR_SEQ_PRIMARY = [
    COLORS["primary_light"], COLORS["secondary"], COLORS["accent"],
    COLORS["negative"], "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16",
]
COLOR_POS_NEG = [COLORS["secondary"], COLORS["negative"]]

# ══════════════════════════════════════════════════════════════════════════════
# ESTILOS CSS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f"""
<style>
    @keyframes fadeInUp {{
        from {{ opacity: 0; transform: translateY(20px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
    }}

    .stApp {{
        background: linear-gradient(135deg, {COLORS['bg_dark']} 0%, #0c1220 50%, #111827 100%);
    }}

    /* ── Sidebar ──────────────────────────────────────────── */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {COLORS['bg_card']} 0%, {COLORS['bg_dark']} 100%);
        border-right: 1px solid {COLORS['border']};
    }}
    [data-testid="stSidebar"] [data-testid="stMarkdown"] h1,
    [data-testid="stSidebar"] [data-testid="stMarkdown"] h2,
    [data-testid="stSidebar"] [data-testid="stMarkdown"] h3 {{
        color: {COLORS['text']};
    }}
    .sidebar-logo {{
        text-align: center;
        padding: 1rem 0 0.5rem 0;
    }}
    .sidebar-logo h2 {{
        background: linear-gradient(135deg, {COLORS['primary_light']}, {COLORS['gradient_end']});
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 1.5rem;
        font-weight: 800;
        margin: 0;
    }}
    .sidebar-logo .sub {{
        color: {COLORS['text_muted']};
        font-size: 0.75rem;
        margin-top: 2px;
    }}
    .sidebar-section {{
        color: {COLORS['text_muted']};
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-weight: 600;
        padding: 8px 0 4px 0;
        border-top: 1px solid {COLORS['border']};
        margin-top: 12px;
    }}

    /* ── Header ───────────────────────────────────────────── */
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
        color: white; font-size: 1.8rem; font-weight: 700; margin: 0; letter-spacing: -0.02em;
    }}
    .dashboard-header .subtitle {{
        color: rgba(255,255,255,0.75); font-size: 0.85rem; margin-top: 4px;
    }}
    .header-badge {{
        background: rgba(255,255,255,0.15); backdrop-filter: blur(10px);
        padding: 6px 14px; border-radius: 20px; color: white; font-size: 0.75rem; font-weight: 500;
    }}

    /* ── Tarjetas de métricas ─────────────────────────────── */
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
        font-size: 0.82rem; color: {COLORS['text_muted']} !important;
        font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em;
    }}
    [data-testid="stMetric"] [data-testid="stMetricValue"] {{
        font-size: 1.6rem; font-weight: 700; color: {COLORS['text']} !important;
    }}

    /* ── Tabs ─────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px; background: {COLORS['bg_card']}; border-radius: 12px;
        padding: 4px; border: 1px solid {COLORS['border']}; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }}
    .stTabs [data-baseweb="tab"] {{
        padding: 10px 24px; border-radius: 10px; font-weight: 500; font-size: 0.85rem;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); color: {COLORS['text_muted']}; border: none;
    }}
    .stTabs [data-baseweb="tab"]:hover {{
        background: rgba(59, 130, 246, 0.1); color: {COLORS['text']};
    }}
    .stTabs [aria-selected="true"] {{
        background: linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['gradient_end']} 100%) !important;
        color: white !important; box-shadow: 0 2px 10px rgba(30, 58, 138, 0.4);
    }}

    /* ── Selectbox y Multiselect ───────────────────────────── */
    [data-baseweb="select"] {{ border-radius: 10px !important; }}
    [data-baseweb="select"] > div {{
        background: {COLORS['bg_card']} !important; border: 1px solid {COLORS['border']} !important;
        border-radius: 10px !important; transition: all 0.3s ease;
    }}
    [data-baseweb="select"] > div:hover {{
        border-color: {COLORS['primary_light']} !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
    }}

    /* ── DataFrames ────────────────────────────────────────── */
    [data-testid="stDataFrame"] {{
        border-radius: 12px; overflow: hidden;
        border: 1px solid {COLORS['border']}; box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    }}

    /* ── Expander ──────────────────────────────────────────── */
    [data-testid="stExpander"] {{
        background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']};
        border-left: 3px solid {COLORS['accent']}; border-radius: 12px;
        transition: all 0.3s ease; margin-bottom: 8px;
    }}
    [data-testid="stExpander"]:hover {{
        border-left-color: {COLORS['primary_light']}; box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    }}

    /* ── Botones ───────────────────────────────────────────── */
    .stDownloadButton > button {{
        background: linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['primary_light']} 100%) !important;
        color: white !important; border: none !important; border-radius: 10px !important;
        padding: 10px 24px !important; font-weight: 600 !important;
        transition: all 0.3s ease !important; box-shadow: 0 2px 10px rgba(30, 58, 138, 0.3) !important;
    }}
    .stDownloadButton > button:hover {{
        transform: translateY(-2px) !important; box-shadow: 0 6px 20px rgba(30, 58, 138, 0.5) !important;
    }}
    .stButton > button {{
        background: linear-gradient(135deg, {COLORS['bg_card']} 0%, rgba(30,41,59,0.8) 100%) !important;
        border: 1px solid {COLORS['border']} !important; border-radius: 10px !important;
        color: {COLORS['text']} !important; transition: all 0.3s ease !important; padding: 8px 20px !important;
    }}
    .stButton > button:hover {{
        border-color: {COLORS['primary_light']} !important;
        box-shadow: 0 0 15px rgba(59, 130, 246, 0.2) !important; transform: translateY(-1px) !important;
    }}

    /* ── Separadores / Alertas / Inputs ────────────────────── */
    hr {{ border: none; height: 1px; background: linear-gradient(90deg, transparent, {COLORS['border']}, transparent); margin: 1.5rem 0; }}
    [data-testid="stAlert"] {{ border-radius: 12px; border: none; }}
    .section-title {{
        font-size: 1.2rem; font-weight: 700; color: {COLORS['text']};
        padding-bottom: 8px; margin-bottom: 16px;
        border-bottom: 2px solid transparent;
        border-image: linear-gradient(90deg, {COLORS['primary_light']}, {COLORS['gradient_end']}) 1;
        animation: fadeInUp 0.5s ease-out;
    }}
    .section-subtitle {{ font-size: 0.9rem; color: {COLORS['text_muted']}; margin-bottom: 12px; }}
    [data-testid="stTextInput"] input {{
        background: {COLORS['bg_card']} !important; border: 1px solid {COLORS['border']} !important;
        border-radius: 10px !important; color: {COLORS['text']} !important; transition: all 0.3s ease;
    }}
    [data-testid="stTextInput"] input:focus {{
        border-color: {COLORS['primary_light']} !important; box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2) !important;
    }}
    .element-container {{ animation: fadeInUp 0.4s ease-out; }}

    /* ── Ocultar elementos default ─────────────────────────── */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    header {{ visibility: hidden; }}

    /* ── Footer personalizado ──────────────────────────────── */
    .custom-footer {{
        background: linear-gradient(135deg, {COLORS['bg_card']} 0%, rgba(15,23,42,0.9) 100%);
        border-top: 1px solid {COLORS['border']}; border-radius: 16px 16px 0 0;
        padding: 16px 24px; margin-top: 2rem; text-align: center;
        color: {COLORS['text_muted']}; font-size: 0.8rem;
    }}
    .custom-footer a {{ color: {COLORS['primary_light']}; text-decoration: none; }}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE DISEÑO
# ══════════════════════════════════════════════════════════════════════════════
def render_header():
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    st.markdown(f"""
    <div class="dashboard-header">
        <div>
            <h1>📊 Dashboard MORAES</h1>
            <div class="subtitle">Analítica financiera en tiempo real · Google Sheets</div>
        </div>
        <div class="header-badge">🕐 {now}</div>
    </div>
    """, unsafe_allow_html=True)


def section_title(icon: str, title: str, subtitle: str = ""):
    sub_html = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="section-title">{icon} {title}</div>{sub_html}', unsafe_allow_html=True)


def styled_separator():
    st.markdown('<div style="margin:1.5rem 0;height:1px;background:linear-gradient(90deg,transparent,#334155,#3b82f6,#334155,transparent);"></div>', unsafe_allow_html=True)


def render_footer():
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    st.markdown(f"""
    <div class="custom-footer">
        <strong>Dashboard MORAES</strong> · Datos actualizados desde Google Sheets cada 60s<br/>
        Última carga: {now} ·
        <a href="https://github.com/Nicolasmorahernandez/dashboard_moraes" target="_blank">GitHub</a>
    </div>
    """, unsafe_allow_html=True)


def apply_chart_theme(fig, height: int = None):
    layout_args = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, -apple-system, sans-serif", color=COLORS["text"], size=12),
        xaxis=dict(gridcolor="rgba(51,65,85,0.4)", gridwidth=1, zeroline=False, showline=True, linecolor=COLORS["border"], linewidth=1),
        yaxis=dict(gridcolor="rgba(51,65,85,0.4)", gridwidth=1, zeroline=False, showline=True, linecolor=COLORS["border"], linewidth=1),
        margin=dict(t=30, b=40, l=60, r=20),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)", font=dict(color=COLORS["text_muted"], size=11)),
        hoverlabel=dict(bgcolor=COLORS["bg_card"], bordercolor=COLORS["border"], font=dict(color=COLORS["text"], size=13)),
    )
    if height:
        layout_args["height"] = height
    fig.update_layout(**layout_args)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# CONEXIÓN Y CARGA DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
SPREADSHEET_NAME = "Finanzas MORAES"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
SA_FILE = pathlib.Path(__file__).parent / "service_account.json"

EXPECTED_HEADERS = {
    "Vendidos": "Producto",
    "Pedidos": "Producto",
    "Modelo Unitario de Rentabilidad": "Producto",
    "proveedores": "Proveedor",
}


def get_gspread_client():
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    elif SA_FILE.exists():
        creds = Credentials.from_service_account_file(str(SA_FILE), scopes=SCOPES)
    else:
        st.error("No se encontraron credenciales. En local: coloca service_account.json. En Streamlit Cloud: configura secrets.")
        st.stop()
    return gspread.authorize(creds)


def _find_header_row(all_values: list[list[str]], marker: str) -> int:
    for idx, row in enumerate(all_values):
        for cell in row:
            if marker.lower() in str(cell).lower():
                return idx
    return 0


def _clean_currency(val: str) -> float:
    if pd.isna(val) or val is None:
        return 0.0
    s = re.sub(r'[$ ]', '', str(val).strip()).replace(',', '')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _clean_pct(val: str) -> float:
    if pd.isna(val) or val is None:
        return 0.0
    s = str(val).strip().replace('%', '')
    try:
        v = float(s)
        return v / 100 if abs(v) > 5 else v
    except ValueError:
        return 0.0


@st.cache_data(ttl=60)
def load_sheet(sheet_name: str) -> pd.DataFrame:
    try:
        gc = get_gspread_client()
        ws = gc.open(SPREADSHEET_NAME).worksheet(sheet_name)
        all_values = ws.get_all_values()
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
        cols, seen, new_cols = df.columns.tolist(), {}, []
        for c in cols:
            c_clean = c.strip()
            if c_clean in seen:
                seen[c_clean] += 1
                new_cols.append(f"{c_clean}_{seen[c_clean]}")
            else:
                seen[c_clean] = 0
                new_cols.append(c_clean)
        df.columns = new_cols
        df = df.replace("", None).dropna(how="all")
        return df
    except gspread.exceptions.WorksheetNotFound:
        st.warning(f"Hoja **'{sheet_name}'** no encontrada.")
        return pd.DataFrame()
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"No se encontró el spreadsheet **'{SPREADSHEET_NAME}'**.")
        st.stop()
    except Exception as e:
        st.error(f"Error al cargar **'{sheet_name}'**: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_vendidos_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        gc = get_gspread_client()
        ws = gc.open(SPREADSHEET_NAME).worksheet("Vendidos")
        all_values = ws.get_all_values()
        if not all_values:
            return pd.DataFrame(), pd.DataFrame()
        header_idx = _find_header_row(all_values, "Producto")
        headers = all_values[header_idx]
        data = all_values[header_idx + 1:]
        if not data:
            return pd.DataFrame(), pd.DataFrame()

        # VENTAS (cols 1-8)
        v_idx = list(range(1, 9))
        v_h = [headers[i].strip() for i in v_idx if i < len(headers)]
        v_d = [[row[i] if i < len(row) else "" for i in v_idx] for row in data]
        df_v = pd.DataFrame(v_d, columns=v_h).replace("", None)
        fc = df_v.columns[0] if len(df_v.columns) > 0 else None
        if fc:
            df_v = df_v.dropna(subset=[fc])
            df_v = df_v[~df_v[fc].str.strip().str.lower().isin(["total", ""])]

        # GASTOS (cols 13-20)
        g_idx = list(range(13, 21))
        g_h = [headers[i].strip() for i in g_idx if i < len(headers)]
        g_d = [[row[i] if i < len(row) else "" for i in g_idx] for row in data]
        df_g = pd.DataFrame(g_d, columns=g_h).replace("", None)
        fg = df_g.columns[0] if len(df_g.columns) > 0 else None
        if fg:
            df_g = df_g.dropna(subset=[fg])
            df_g = df_g[df_g[fg].str.strip() != ""]

        for df in [df_v, df_g]:
            cols, seen, new_cols = df.columns.tolist(), {}, []
            for c in cols:
                if c in seen:
                    seen[c] += 1
                    new_cols.append(f"{c}_{seen[c]}")
                else:
                    seen[c] = 0
                    new_cols.append(c)
            df.columns = new_cols
        return df_v, df_g
    except Exception as e:
        st.error(f"Error al cargar **'Vendidos'**: {e}")
        return pd.DataFrame(), pd.DataFrame()


def safe_numeric(df, col):
    return df[col].apply(_clean_currency) if col in df.columns else pd.Series(dtype=float)

def safe_pct(df, col):
    return df[col].apply(_clean_pct) if col in df.columns else pd.Series(dtype=float)

def fmt_usd(val): return f"${val:,.2f}"
def fmt_pct(val): return f"{val * 100:.1f}%"
def empty_warning(name): st.info(f"No hay datos disponibles en la hoja **{name}**.")

def col_exists(df, col):
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

# ══════════════════════════════════════════════════════════════════════════════
# PREPROCESAMIENTO
# ══════════════════════════════════════════════════════════════════════════════
# -- VENDIDOS --
COL_V_PRODUCTO = "Producto"
COL_V_CATEGORIA = col_exists(df_vendidos, "Categor") or "Categoría"
COL_V_FECHA = col_exists(df_vendidos, "Fecha de Venta") or "Fecha de Venta"
COL_V_CANTIDAD = col_exists(df_vendidos, "Cantidad Vendida") or "Cantidad Vendida"
COL_V_PRECIO = col_exists(df_vendidos, "Precio Unitario") or "Precio Unitario (USD)"
COL_V_INGRESO = col_exists(df_vendidos, "Ingreso Total") or "Ingreso Total (USD)"
COL_V_METODO_PAGO = col_exists(df_vendidos, "todo de Pago") or "Método de Pago"

if not df_vendidos.empty:
    for c in [COL_V_CANTIDAD, COL_V_PRECIO, COL_V_INGRESO]:
        if c in df_vendidos.columns:
            df_vendidos[c] = safe_numeric(df_vendidos, c)
    if COL_V_FECHA in df_vendidos.columns:
        df_vendidos[COL_V_FECHA] = pd.to_datetime(df_vendidos[COL_V_FECHA], errors="coerce", dayfirst=True)
        df_vendidos["Mes"] = df_vendidos[COL_V_FECHA].dt.to_period("M").astype(str)

# -- GASTOS --
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
        df_gastos_vendidos[COL_G_FECHA] = pd.to_datetime(df_gastos_vendidos[COL_G_FECHA], errors="coerce", dayfirst=True)

# -- RENTABILIDAD --
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

# -- PEDIDOS --
COL_P_REF = col_exists(df_pedidos, "Referencia") or "Referencia del Pedido"
COL_P_PRODUCTO = "Producto"
COL_P_PROVEEDOR = "Proveedor"
COL_P_CANTIDAD = col_exists(df_pedidos, "Cantidad Solicitada") or "Cantidad Solicitada"
COL_P_COSTO_TOTAL = col_exists(df_pedidos, "Costo Total Estimado") or "Costo Total Estimado (USD)"
COL_P_FECHA = col_exists(df_pedidos, "Fecha Estimada") or "Fecha Estimada de Llegada"
COL_P_CONFIRMADO = col_exists(df_pedidos, "Pedido Confirmado") or "¿Pedido Confirmado?"

if not df_pedidos.empty:
    for c in [COL_P_CANTIDAD, COL_P_COSTO_TOTAL]:
        if c in df_pedidos.columns:
            df_pedidos[c] = safe_numeric(df_pedidos, c)
    if COL_P_FECHA in df_pedidos.columns:
        df_pedidos[COL_P_FECHA] = pd.to_datetime(df_pedidos[COL_P_FECHA], errors="coerce", dayfirst=True)
    df_pedidos = df_pedidos.dropna(subset=[COL_P_PRODUCTO])
    df_pedidos = df_pedidos[df_pedidos[COL_P_PRODUCTO].str.strip() != ""]
    if COL_P_CONFIRMADO in df_pedidos.columns:
        df_pedidos["_confirmado"] = (
            df_pedidos[COL_P_CONFIRMADO].astype(str).str.strip().str.upper()
            .isin(["SI", "SÍ", "YES", "TRUE", "VERDADERO", "1"])
        )
    else:
        df_pedidos["_confirmado"] = False


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — SLICER & FILTER
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div class="sidebar-logo">
        <h2>📊 MORAES</h2>
        <div class="sub">Financial Analytics Dashboard</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # ── Filtros de Rentabilidad / Costos ──────────────────────
    st.markdown('<div class="sidebar-section">📊 Productos y Canales</div>', unsafe_allow_html=True)

    productos_list = df_rentabilidad[COL_R_PRODUCTO].dropna().unique().tolist() if not df_rentabilidad.empty else []
    metodos_list = (
        df_rentabilidad[COL_R_METODO].dropna().unique().tolist()
        if not df_rentabilidad.empty and COL_R_METODO in df_rentabilidad.columns else []
    )

    sel_productos = st.multiselect("Productos", productos_list, default=productos_list, key="sb_prod")
    sel_metodos = st.multiselect("Canal de Venta", metodos_list, default=metodos_list, key="sb_met")

    # ── Filtros de Pedidos ────────────────────────────────────
    st.markdown('<div class="sidebar-section">📦 Pedidos</div>', unsafe_allow_html=True)

    estado_filtro = st.selectbox("Estado", ["Todos", "Confirmados", "Pendientes"], key="sb_estado")
    prod_ped_list = df_pedidos[COL_P_PRODUCTO].dropna().unique().tolist() if not df_pedidos.empty else []
    sel_prod_ped = st.multiselect("Producto (Pedidos)", prod_ped_list, default=prod_ped_list, key="sb_ped_prod")

    # ── Filtros de Proveedores ────────────────────────────────
    st.markdown('<div class="sidebar-section">🤝 Proveedores</div>', unsafe_allow_html=True)

    busqueda_prov = st.text_input("🔍 Buscar proveedor", key="sb_prov_search")
    tipos_prov_list = (
        df_proveedores["Tipo de proveedor"].dropna().unique().tolist()
        if not df_proveedores.empty and "Tipo de proveedor" in df_proveedores.columns else []
    )
    sel_tipo_prov = st.multiselect("Tipo", tipos_prov_list, default=tipos_prov_list, key="sb_prov_tipo")

    # ── Info ──────────────────────────────────────────────────
    st.markdown('<div class="sidebar-section">ℹ️ Info</div>', unsafe_allow_html=True)
    st.caption(f"Última carga: {datetime.now().strftime('%H:%M:%S')}")
    st.caption("Datos: Google Sheets (TTL 60s)")


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑAS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📈 Panel General",
    "💰 Rentabilidad",
    "🔀 Canales de Venta",
    "📦 Pedidos e Inventario",
    "🏷️ Costos por Producto",
    "🤝 Proveedores",
])


# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — Panel General
# Wireframe: KPIs (row) → 3-col grid: [Bar Chart][Chart][Scatter] / [Bar][Pie][Chart] → Top 10
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
        n_transacciones = len(df_vendidos)
        n_productos = df_vendidos[COL_V_PRODUCTO].nunique()
        margen_pct = (ganancia_neta / ventas_totales * 100) if ventas_totales > 0 else 0

        # ── KPI ROW (8 cards) ────────────────────────────────────
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("💵 Ventas Totales", fmt_usd(ventas_totales))
        k2.metric("📤 Gastos Totales", fmt_usd(gastos_totales))
        k3.metric("📊 Ganancia Neta", fmt_usd(ganancia_neta), delta=fmt_usd(ganancia_neta), delta_color="normal")
        k4.metric("🎫 Ticket Promedio", fmt_usd(ticket_promedio))
        k5.metric("🛒 Transacciones", n_transacciones)
        k6.metric("📈 Margen %", f"{margen_pct:.1f}%")

        styled_separator()

        # ── ROW 1: 3 columnas [Bar Chart] [Chart] [Scatter] ──
        r1c1, r1c2, r1c3 = st.columns(3)

        with r1c1:
            section_title("📊", "Ventas vs Gastos")
            if "Mes" in df_vendidos.columns and COL_V_INGRESO in df_vendidos.columns:
                ventas_mes = (
                    df_vendidos.groupby("Mes")[COL_V_INGRESO].sum().reset_index()
                    .rename(columns={COL_V_INGRESO: "Ventas"})
                )
                ventas_mes["Gastos"] = gastos_totales / len(ventas_mes) if len(ventas_mes) > 0 else 0
                fig = px.bar(
                    ventas_mes, x="Mes", y=["Ventas", "Gastos"],
                    barmode="group", text_auto="$.2f",
                    color_discrete_sequence=[COLORS["secondary"], COLORS["negative"]],
                    labels={"value": "USD", "variable": ""},
                )
                apply_chart_theme(fig, height=350)
                fig.update_layout(legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center"), bargap=0.3)
                fig.update_traces(marker_line_width=0, marker_cornerradius=6)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay datos de fecha.")

        with r1c2:
            section_title("📦", "Ingresos por Producto")
            if COL_V_INGRESO in df_vendidos.columns:
                ing_prod = (
                    df_vendidos.groupby(COL_V_PRODUCTO)[COL_V_INGRESO]
                    .sum().sort_values(ascending=True).reset_index()
                )
                fig = px.bar(
                    ing_prod, y=COL_V_PRODUCTO, x=COL_V_INGRESO,
                    orientation="h", text_auto="$.2f",
                    color=COL_V_PRODUCTO,
                    color_discrete_sequence=COLOR_SEQ_PRIMARY,
                )
                apply_chart_theme(fig, height=350)
                fig.update_layout(showlegend=False)
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(fig, use_container_width=True)

        with r1c3:
            section_title("🔍", "Precio vs Cantidad")
            if COL_V_PRECIO in df_vendidos.columns and COL_V_CANTIDAD in df_vendidos.columns:
                fig = px.scatter(
                    df_vendidos, x=COL_V_PRECIO, y=COL_V_CANTIDAD,
                    color=COL_V_PRODUCTO,
                    size=COL_V_INGRESO if COL_V_INGRESO in df_vendidos.columns else None,
                    color_discrete_sequence=COLOR_SEQ_PRIMARY,
                    hover_data=[COL_V_PRODUCTO],
                    labels={COL_V_PRECIO: "Precio Unit. (USD)", COL_V_CANTIDAD: "Cantidad"},
                )
                apply_chart_theme(fig, height=350)
                fig.update_traces(marker=dict(line=dict(width=1, color=COLORS["border"])))
                st.plotly_chart(fig, use_container_width=True)

        styled_separator()

        # ── ROW 2: 3 columnas [Bar Chart] [Pie Chart] [Chart] ──
        r2c1, r2c2, r2c3 = st.columns(3)

        with r2c1:
            section_title("💸", "Gastos por Categoría")
            if not df_gastos_vendidos.empty and COL_G_CATEGORIA in df_gastos_vendidos.columns and COL_G_MONTO in df_gastos_vendidos.columns:
                gastos_cat = (
                    df_gastos_vendidos.dropna(subset=[COL_G_CATEGORIA])
                    .groupby(COL_G_CATEGORIA)[COL_G_MONTO].sum()
                    .sort_values(ascending=True).reset_index()
                )
                if not gastos_cat.empty:
                    fig = px.bar(
                        gastos_cat, y=COL_G_CATEGORIA, x=COL_G_MONTO,
                        orientation="h", text_auto="$.2f",
                        color=COL_G_CATEGORIA,
                        color_discrete_sequence=COLOR_SEQ_PRIMARY,
                    )
                    apply_chart_theme(fig, height=350)
                    fig.update_layout(showlegend=False)
                    fig.update_traces(marker_cornerradius=6)
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin datos de gastos.")

        with r2c2:
            section_title("🥧", "Distribución de Gastos")
            if not df_gastos_vendidos.empty and COL_G_CATEGORIA in df_gastos_vendidos.columns and COL_G_MONTO in df_gastos_vendidos.columns:
                gastos_cat2 = (
                    df_gastos_vendidos.dropna(subset=[COL_G_CATEGORIA])
                    .groupby(COL_G_CATEGORIA)[COL_G_MONTO].sum().reset_index()
                )
                if not gastos_cat2.empty:
                    fig = px.pie(
                        gastos_cat2, names=COL_G_CATEGORIA, values=COL_G_MONTO,
                        hole=0.5, color_discrete_sequence=COLOR_SEQ_PRIMARY,
                    )
                    apply_chart_theme(fig, height=350)
                    fig.update_traces(
                        textinfo="percent+label",
                        textfont=dict(size=11, color=COLORS["text"]),
                        marker=dict(line=dict(color=COLORS["bg_dark"], width=2)),
                        pull=[0.03] * len(gastos_cat2),
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin datos de gastos.")

        with r2c3:
            section_title("💳", "Métodos de Pago")
            if COL_V_METODO_PAGO in df_vendidos.columns:
                metodo_data = df_vendidos[COL_V_METODO_PAGO].dropna().value_counts().reset_index()
                metodo_data.columns = ["Método", "Cantidad"]
                if not metodo_data.empty:
                    fig = px.pie(
                        metodo_data, names="Método", values="Cantidad",
                        hole=0.5, color_discrete_sequence=[COLORS["primary_light"], COLORS["accent"], COLORS["secondary"]],
                    )
                    apply_chart_theme(fig, height=350)
                    fig.update_traces(
                        textinfo="percent+label",
                        textfont=dict(size=11, color=COLORS["text"]),
                        marker=dict(line=dict(color=COLORS["bg_dark"], width=2)),
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin datos de método de pago.")

        styled_separator()

        # ── BOTTOM: Top 10 Productos ──────────────────────────
        section_title("🏆", "Top 10 Productos", "Ranking por cantidad vendida")
        if COL_V_CANTIDAD in df_vendidos.columns:
            top10 = (
                df_vendidos.groupby(COL_V_PRODUCTO)[COL_V_CANTIDAD]
                .sum().sort_values(ascending=False).head(10).reset_index()
            )
            cols_top = st.columns(min(len(top10), 5))
            medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
            for i, row in top10.iterrows():
                col_idx = i % 5
                pct = (row[COL_V_CANTIDAD] / cant_ventas * 100) if cant_ventas > 0 else 0
                with cols_top[col_idx]:
                    st.markdown(f"""
                    <div style="background: {COLORS['bg_card']}; border: 1px solid {COLORS['border']};
                         border-radius: 10px; padding: 12px 14px; margin-bottom: 8px; text-align: center;
                         border-top: 3px solid {COLOR_SEQ_PRIMARY[i % len(COLOR_SEQ_PRIMARY)]};">
                        <div style="font-size: 1.5rem;">{medals[i]}</div>
                        <div style="font-weight: 600; color: {COLORS['text']}; font-size: 0.9rem; margin-top: 4px;">
                            {row[COL_V_PRODUCTO]}
                        </div>
                        <div style="color: {COLORS['accent']}; font-weight: 700; font-size: 1.1rem;">
                            {int(row[COL_V_CANTIDAD])} uds
                        </div>
                        <div style="color: {COLORS['text_muted']}; font-size: 0.75rem;">{pct:.1f}%</div>
                    </div>
                    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — Rentabilidad
# Wireframe: KPIs → [ROI bar][MARGIN bar][Scatter] → [Ganancias bar][Pie][Best/Worst] → Table
# ──────────────────────────────────────────────────────────────────────────────
with tab2:
    section_title("💰", "Análisis de Rentabilidad", "ROI, márgenes y ganancias por producto y canal")

    if df_rentabilidad.empty:
        empty_warning("Modelo Unitario de Rentabilidad")
    else:
        df_r = df_rentabilidad.copy()
        if sel_productos:
            df_r = df_r[df_r[COL_R_PRODUCTO].isin(sel_productos)]
        if sel_metodos and COL_R_METODO in df_r.columns:
            df_r = df_r[df_r[COL_R_METODO].isin(sel_metodos)]

        if df_r.empty:
            st.warning("No hay datos con los filtros seleccionados. Ajusta en el panel lateral.")
        else:
            roi_prom = df_r[COL_R_ROI].mean() if COL_R_ROI in df_r.columns else 0
            margin_prom = df_r[COL_R_MARGIN].mean() if COL_R_MARGIN in df_r.columns else 0
            ganancia_prom = df_r[COL_R_GANANCIA].mean() if COL_R_GANANCIA in df_r.columns else 0
            precio_venta_prom = df_r[COL_R_VENTA].mean() if COL_R_VENTA in df_r.columns else 0
            costo_prom = df_r[COL_R_COSTO].mean() if COL_R_COSTO in df_r.columns else 0

            # KPIs
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("📈 ROI Promedio", fmt_pct(roi_prom))
            m2.metric("📊 MARGIN Prom.", fmt_pct(margin_prom))
            m3.metric("💵 Ganancia Unit.", fmt_usd(ganancia_prom))
            m4.metric("🏷️ Precio Venta", fmt_usd(precio_venta_prom))
            m5.metric("💰 Costo Prom.", fmt_usd(costo_prom))

            styled_separator()

            # Row 1: [ROI bar] [MARGIN bar] [Scatter]
            r1c1, r1c2, r1c3 = st.columns(3)

            with r1c1:
                section_title("📈", "ROI por Producto")
                fig = px.bar(
                    df_r, x=COL_R_PRODUCTO, y=COL_R_ROI,
                    color=COL_R_METODO if COL_R_METODO in df_r.columns else None,
                    barmode="group",
                    text=df_r[COL_R_ROI].apply(lambda v: f"{v*100:.1f}%"),
                    color_discrete_sequence=[COLORS["secondary"], COLORS["primary_light"], COLORS["accent"]],
                )
                apply_chart_theme(fig, height=350)
                fig.update_xaxes(tickangle=-45)
                fig.update_traces(marker_cornerradius=5)
                st.plotly_chart(fig, use_container_width=True)

            with r1c2:
                section_title("📊", "MARGIN por Producto")
                fig = px.bar(
                    df_r, x=COL_R_PRODUCTO, y=COL_R_MARGIN,
                    color=COL_R_METODO if COL_R_METODO in df_r.columns else None,
                    barmode="group",
                    text=df_r[COL_R_MARGIN].apply(lambda v: f"{v*100:.1f}%"),
                    color_discrete_sequence=[COLORS["accent"], COLORS["primary_light"], COLORS["secondary"]],
                )
                apply_chart_theme(fig, height=350)
                fig.update_xaxes(tickangle=-45)
                fig.update_traces(marker_cornerradius=5)
                st.plotly_chart(fig, use_container_width=True)

            with r1c3:
                section_title("🔍", "ROI vs MARGIN")
                if COL_R_ROI in df_r.columns and COL_R_MARGIN in df_r.columns:
                    fig = px.scatter(
                        df_r, x=COL_R_ROI, y=COL_R_MARGIN,
                        color=COL_R_PRODUCTO,
                        size=df_r[COL_R_GANANCIA].abs() if COL_R_GANANCIA in df_r.columns else None,
                        symbol=COL_R_METODO if COL_R_METODO in df_r.columns else None,
                        color_discrete_sequence=COLOR_SEQ_PRIMARY,
                        hover_data=[COL_R_PRODUCTO, COL_R_GANANCIA],
                    )
                    apply_chart_theme(fig, height=350)
                    fig.update_traces(marker=dict(line=dict(width=1, color=COLORS["border"])))
                    st.plotly_chart(fig, use_container_width=True)

            styled_separator()

            # Row 2: [Ganancias bar] [Distribución pie] [Best/Worst]
            r2c1, r2c2, r2c3 = st.columns(3)

            with r2c1:
                section_title("💵", "Ganancias por Producto")
                if COL_R_GANANCIA in df_r.columns:
                    gan_prod = df_r.groupby(COL_R_PRODUCTO)[COL_R_GANANCIA].sum().sort_values(ascending=True).reset_index()
                    fig = px.bar(
                        gan_prod, y=COL_R_PRODUCTO, x=COL_R_GANANCIA,
                        orientation="h", text_auto="$.2f",
                        color=COL_R_PRODUCTO,
                        color_discrete_sequence=COLOR_SEQ_PRIMARY,
                    )
                    apply_chart_theme(fig, height=350)
                    fig.update_layout(showlegend=False)
                    fig.update_traces(marker_cornerradius=6)
                    st.plotly_chart(fig, use_container_width=True)

            with r2c2:
                section_title("🥧", "Distribución de Costos")
                if COL_R_METODO in df_r.columns:
                    dist = df_r.groupby(COL_R_METODO)[COL_R_COSTO].sum().reset_index()
                    fig = px.pie(dist, names=COL_R_METODO, values=COL_R_COSTO, hole=0.5)
                    apply_chart_theme(fig, height=350)
                    fig.update_traces(
                        textinfo="percent+label",
                        textfont=dict(size=11, color=COLORS["text"]),
                        marker=dict(
                            colors=[COLORS["primary_light"], COLORS["secondary"], COLORS["accent"]],
                            line=dict(color=COLORS["bg_dark"], width=2),
                        ),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            with r2c3:
                section_title("🏆", "Mejor / Peor ROI")
                if COL_R_ROI in df_r.columns:
                    best = df_r.loc[df_r[COL_R_ROI].idxmax()]
                    worst = df_r.loc[df_r[COL_R_ROI].idxmin()]
                    st.success(f"🏆 **Mejor:** {best[COL_R_PRODUCTO]} ({best.get(COL_R_METODO, 'N/A')}) — {fmt_pct(best[COL_R_ROI])}")
                    st.error(f"⚠️ **Peor:** {worst[COL_R_PRODUCTO]} ({worst.get(COL_R_METODO, 'N/A')}) — {fmt_pct(worst[COL_R_ROI])}")
                    styled_separator()
                    # Mini table
                    df_mini = df_r[[COL_R_PRODUCTO, COL_R_METODO, COL_R_ROI, COL_R_MARGIN, COL_R_GANANCIA]].copy()
                    df_mini[COL_R_ROI] = df_mini[COL_R_ROI].apply(fmt_pct)
                    df_mini[COL_R_MARGIN] = df_mini[COL_R_MARGIN].apply(fmt_pct)
                    df_mini[COL_R_GANANCIA] = df_mini[COL_R_GANANCIA].apply(fmt_usd)
                    st.dataframe(df_mini, use_container_width=True, hide_index=True, height=200)

            styled_separator()

            # Table
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


# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — Comparación de Canales
# Wireframe: KPIs (canal cards) → [ROI bar][MARGIN bar][Ganancia vs Costo] → [Pie][Pie][Recomendación]
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
            # KPI cards per canal
            canal_icons = {"FBA": "📦", "FBM": "🚚", "DIRECTO": "🏪", "Directo": "🏪"}
            canal_colors = [COLORS["primary_light"], COLORS["secondary"], COLORS["accent"]]
            cols_canal = st.columns(len(canales))
            for i, canal in enumerate(canales):
                sub = df_rentabilidad[df_rentabilidad[COL_R_METODO] == canal]
                icon = canal_icons.get(canal, "📊")
                with cols_canal[i]:
                    st.markdown(f"""
                    <div style="text-align:center;background:{COLORS['bg_card']};border:1px solid {COLORS['border']};
                         border-radius:14px;padding:16px;margin-bottom:12px;border-top:3px solid {canal_colors[i % 3]};">
                        <div style="font-size:2rem;margin-bottom:6px;">{icon}</div>
                        <div style="font-size:1.1rem;font-weight:700;color:{COLORS['text']};margin-bottom:8px;">{canal}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.metric("ROI Prom.", fmt_pct(sub[COL_R_ROI].mean()))
                    st.metric("MARGIN", fmt_pct(sub[COL_R_MARGIN].mean()))
                    st.metric("Ganancia", fmt_usd(sub[COL_R_GANANCIA].mean()))
                    st.metric("Productos", len(sub))

            styled_separator()

            agg = (
                df_rentabilidad.groupby(COL_R_METODO)
                .agg({COL_R_ROI: "mean", COL_R_MARGIN: "mean", COL_R_GANANCIA: "sum", COL_R_COSTO: "sum"})
                .reset_index()
            )

            # Row 1: [ROI bar] [MARGIN bar] [Ganancia vs Costo]
            r1c1, r1c2, r1c3 = st.columns(3)

            with r1c1:
                section_title("📈", "ROI por Canal")
                fig = px.bar(
                    agg, x=COL_R_METODO, y=COL_R_ROI,
                    text=agg[COL_R_ROI].apply(lambda v: f"{v*100:.1f}%"),
                    color=COL_R_METODO,
                    color_discrete_sequence=canal_colors,
                )
                apply_chart_theme(fig, height=350)
                fig.update_layout(showlegend=False)
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(fig, use_container_width=True)

            with r1c2:
                section_title("📊", "MARGIN por Canal")
                fig = px.bar(
                    agg, x=COL_R_METODO, y=COL_R_MARGIN,
                    text=agg[COL_R_MARGIN].apply(lambda v: f"{v*100:.1f}%"),
                    color=COL_R_METODO,
                    color_discrete_sequence=canal_colors,
                )
                apply_chart_theme(fig, height=350)
                fig.update_layout(showlegend=False)
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(fig, use_container_width=True)

            with r1c3:
                section_title("💰", "Ganancia vs Costo")
                fig = px.bar(
                    agg, x=COL_R_METODO, y=[COL_R_GANANCIA, COL_R_COSTO],
                    barmode="group", text_auto="$.2f",
                    color_discrete_sequence=[COLORS["secondary"], COLORS["negative"]],
                    labels={"value": "USD", "variable": ""},
                )
                apply_chart_theme(fig, height=350)
                fig.update_layout(legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center"), bargap=0.3)
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(fig, use_container_width=True)

            styled_separator()

            # Row 2: [Pie productos] [Pie ingresos] [Recomendación]
            r2c1, r2c2, r2c3 = st.columns(3)

            canal_counts = df_rentabilidad.groupby(COL_R_METODO).size().reset_index(name="Unidades")
            with r2c1:
                section_title("📦", "Productos por Canal")
                fig = px.pie(canal_counts, names=COL_R_METODO, values="Unidades", hole=0.5)
                apply_chart_theme(fig, height=350)
                fig.update_traces(
                    textinfo="percent+label", textfont=dict(size=11, color=COLORS["text"]),
                    marker=dict(colors=canal_colors, line=dict(color=COLORS["bg_dark"], width=2)),
                )
                st.plotly_chart(fig, use_container_width=True)

            ingresos_canal = (
                df_rentabilidad.groupby(COL_R_METODO)[COL_R_VENTA]
                .sum().reset_index().rename(columns={COL_R_VENTA: "Ingresos"})
            )
            with r2c2:
                section_title("💵", "Ingresos por Canal")
                fig = px.pie(ingresos_canal, names=COL_R_METODO, values="Ingresos", hole=0.5)
                apply_chart_theme(fig, height=350)
                fig.update_traces(
                    textinfo="percent+label", textfont=dict(size=11, color=COLORS["text"]),
                    marker=dict(colors=canal_colors, line=dict(color=COLORS["bg_dark"], width=2)),
                )
                st.plotly_chart(fig, use_container_width=True)

            with r2c3:
                section_title("🎯", "Recomendación")
                mejor_canal = agg.loc[agg[COL_R_ROI].idxmax(), COL_R_METODO]
                mejor_roi = agg.loc[agg[COL_R_ROI].idxmax(), COL_R_ROI]
                mejor_margin = agg.loc[agg[COL_R_MARGIN].idxmax(), COL_R_METODO]
                st.success(f"🏆 **Mejor ROI:** **{mejor_canal}** — {fmt_pct(mejor_roi)}")
                st.info(f"📊 **Mejor MARGIN:** **{mejor_margin}** — {fmt_pct(agg.loc[agg[COL_R_MARGIN].idxmax(), COL_R_MARGIN])}")
                styled_separator()
                # Summary table
                agg_display = agg.copy()
                agg_display[COL_R_ROI] = agg_display[COL_R_ROI].apply(fmt_pct)
                agg_display[COL_R_MARGIN] = agg_display[COL_R_MARGIN].apply(fmt_pct)
                agg_display[COL_R_GANANCIA] = agg_display[COL_R_GANANCIA].apply(fmt_usd)
                agg_display[COL_R_COSTO] = agg_display[COL_R_COSTO].apply(fmt_usd)
                st.dataframe(agg_display, use_container_width=True, hide_index=True, height=180)


# ──────────────────────────────────────────────────────────────────────────────
# TAB 4 — Pedidos e Inventario
# Wireframe: KPIs → [Bar inversión][Scatter timeline][Pie unidades] → Table
# ──────────────────────────────────────────────────────────────────────────────
with tab4:
    section_title("📦", "Pedidos e Inventario", "Seguimiento de pedidos, inversiones y llegadas estimadas")

    if df_pedidos.empty:
        empty_warning("Pedidos")
    else:
        # Apply sidebar filters
        df_p = df_pedidos.copy()
        if estado_filtro == "Confirmados":
            df_p = df_p[df_p["_confirmado"]]
        elif estado_filtro == "Pendientes":
            df_p = df_p[~df_p["_confirmado"]]
        if sel_prod_ped:
            df_p = df_p[df_p[COL_P_PRODUCTO].isin(sel_prod_ped)]

        total_pedidos = len(df_p)
        confirmados = df_p["_confirmado"].sum()
        pendientes = total_pedidos - confirmados
        inversion_total = df_p[COL_P_COSTO_TOTAL].sum() if COL_P_COSTO_TOTAL in df_p.columns else 0
        inversion_conf = df_p.loc[df_p["_confirmado"], COL_P_COSTO_TOTAL].sum() if COL_P_COSTO_TOTAL in df_p.columns else 0
        total_uds = int(df_p[COL_P_CANTIDAD].sum()) if COL_P_CANTIDAD in df_p.columns else 0

        # KPIs
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("📋 Total Pedidos", total_pedidos)
        k2.metric("✅ Confirmados", int(confirmados))
        k3.metric("⏳ Pendientes", int(pendientes))
        k4.metric("💰 Inversión Total", fmt_usd(inversion_total))
        k5.metric("📦 Total Unidades", total_uds)

        styled_separator()

        if df_p.empty:
            st.warning("No hay pedidos con los filtros seleccionados.")
        else:
            # Row 1: [Bar inversión] [Scatter timeline] [Pie unidades]
            r1c1, r1c2, r1c3 = st.columns(3)

            with r1c1:
                section_title("💰", "Inversión por Producto")
                if COL_P_COSTO_TOTAL in df_p.columns:
                    inv_prod = df_p.groupby(COL_P_PRODUCTO)[COL_P_COSTO_TOTAL].sum().sort_values(ascending=True).reset_index()
                    fig = px.bar(
                        inv_prod, y=COL_P_PRODUCTO, x=COL_P_COSTO_TOTAL,
                        orientation="h", text_auto="$.2f",
                        color=COL_P_PRODUCTO, color_discrete_sequence=COLOR_SEQ_PRIMARY,
                    )
                    apply_chart_theme(fig, height=350)
                    fig.update_layout(showlegend=False)
                    fig.update_traces(marker_cornerradius=6)
                    st.plotly_chart(fig, use_container_width=True)

            with r1c2:
                section_title("📅", "Timeline de Llegadas")
                if COL_P_FECHA in df_p.columns:
                    df_tl = df_p.dropna(subset=[COL_P_FECHA])
                    if not df_tl.empty and COL_P_CANTIDAD in df_tl.columns:
                        fig = px.scatter(
                            df_tl, x=COL_P_FECHA, y=COL_P_PRODUCTO,
                            size=COL_P_CANTIDAD, color=COL_P_PRODUCTO,
                            hover_data=[COL_P_PROVEEDOR, COL_P_COSTO_TOTAL] if COL_P_PROVEEDOR in df_tl.columns else None,
                            size_max=40, color_discrete_sequence=COLOR_SEQ_PRIMARY,
                        )
                        apply_chart_theme(fig, height=350)
                        fig.update_layout(showlegend=False, yaxis=dict(categoryorder="total ascending"))
                        fig.update_traces(marker=dict(line=dict(width=1, color=COLORS["border"])))
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("Sin datos de timeline.")
                else:
                    st.info("Sin fechas de llegada.")

            with r1c3:
                section_title("📦", "Unidades por Producto")
                if COL_P_CANTIDAD in df_p.columns:
                    uds = df_p.groupby(COL_P_PRODUCTO)[COL_P_CANTIDAD].sum().reset_index()
                    fig = px.pie(uds, names=COL_P_PRODUCTO, values=COL_P_CANTIDAD, hole=0.5)
                    apply_chart_theme(fig, height=350)
                    fig.update_traces(
                        textinfo="percent+label", textfont=dict(size=11, color=COLORS["text"]),
                        marker=dict(colors=COLOR_SEQ_PRIMARY[:len(uds)], line=dict(color=COLORS["bg_dark"], width=2)),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            styled_separator()

            # Table
            section_title("📋", "Detalle de Pedidos")
            df_tabla = df_p.copy()
            df_tabla["Estado"] = df_tabla["_confirmado"].map({True: "✅ Confirmado", False: "⏳ Pendiente"})
            cols_show = [c for c in df_tabla.columns if not c.startswith("_")]
            st.dataframe(df_tabla[cols_show], use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────────────────────────────────────
# TAB 5 — Costos por Producto
# Wireframe: KPIs → [Bar costos][Pie distribución][Desglose] → Table
# ──────────────────────────────────────────────────────────────────────────────
with tab5:
    section_title("🏷️", "Costos por Producto", "Análisis detallado de la estructura de costos")

    if df_rentabilidad.empty:
        empty_warning("Modelo Unitario de Rentabilidad")
    else:
        # Apply sidebar filters
        df_c = df_rentabilidad.copy()
        if sel_productos:
            df_c = df_c[df_c[COL_R_PRODUCTO].isin(sel_productos)]
        if sel_metodos and COL_R_METODO in df_c.columns:
            df_c = df_c[df_c[COL_R_METODO].isin(sel_metodos)]

        if df_c.empty:
            st.warning("No hay datos con los filtros seleccionados. Ajusta en el panel lateral.")
        else:
            costo_total = df_c[COL_R_COSTO].sum() if COL_R_COSTO in df_c.columns else 0
            productos_unicos = df_c[COL_R_PRODUCTO].nunique()
            items_costo = len(df_c)
            costo_promedio = df_c[COL_R_COSTO].mean() if COL_R_COSTO in df_c.columns else 0
            ganancia_total = df_c[COL_R_GANANCIA].sum() if COL_R_GANANCIA in df_c.columns else 0

            # KPIs
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("💰 Costo Total", fmt_usd(costo_total))
            m2.metric("📦 Productos", productos_unicos)
            m3.metric("📋 Ítems", items_costo)
            m4.metric("📊 Costo Prom.", fmt_usd(costo_promedio))
            m5.metric("💵 Ganancia Tot.", fmt_usd(ganancia_total))

            styled_separator()

            # Row 1: [Bar costos] [Pie distribución] [Desglose/Comparativo]
            r1c1, r1c2, r1c3 = st.columns(3)

            with r1c1:
                section_title("📊", "Costos por Producto")
                cost_prod = df_c.groupby(COL_R_PRODUCTO)[COL_R_COSTO].sum().sort_values(ascending=True).reset_index()
                fig = px.bar(
                    cost_prod, y=COL_R_PRODUCTO, x=COL_R_COSTO,
                    orientation="h", text_auto="$.2f",
                    color=COL_R_PRODUCTO, color_discrete_sequence=COLOR_SEQ_PRIMARY,
                )
                apply_chart_theme(fig, height=350)
                fig.update_layout(showlegend=False)
                fig.update_traces(marker_cornerradius=6)
                st.plotly_chart(fig, use_container_width=True)

            with r1c2:
                section_title("🥧", "Distribución por Canal")
                if COL_R_METODO in df_c.columns:
                    dist_canal = df_c.groupby(COL_R_METODO)[COL_R_COSTO].sum().reset_index()
                    fig = px.pie(dist_canal, names=COL_R_METODO, values=COL_R_COSTO, hole=0.5)
                    apply_chart_theme(fig, height=350)
                    fig.update_traces(
                        textinfo="percent+label", textfont=dict(size=11, color=COLORS["text"]),
                        marker=dict(
                            colors=[COLORS["primary_light"], COLORS["secondary"], COLORS["accent"]],
                            line=dict(color=COLORS["bg_dark"], width=2),
                        ),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            with r1c3:
                section_title("⚖️", "Costo vs Ganancia")
                if COL_R_GANANCIA in df_c.columns:
                    cg = df_c.groupby(COL_R_PRODUCTO).agg({COL_R_COSTO: "sum", COL_R_GANANCIA: "sum"}).reset_index()
                    fig = px.bar(
                        cg, x=COL_R_PRODUCTO, y=[COL_R_COSTO, COL_R_GANANCIA],
                        barmode="group", text_auto="$.2f",
                        color_discrete_sequence=[COLORS["negative"], COLORS["secondary"]],
                        labels={"value": "USD", "variable": ""},
                    )
                    apply_chart_theme(fig, height=350)
                    fig.update_layout(legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"))
                    fig.update_xaxes(tickangle=-45)
                    fig.update_traces(marker_cornerradius=6)
                    st.plotly_chart(fig, use_container_width=True)

            styled_separator()

            # Desglose por canal (solo si un producto seleccionado)
            if len(sel_productos) == 1 and COL_R_METODO in df_c.columns:
                section_title("📊", f"Desglose por Canal — {sel_productos[0]}")
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

            # Table + Download
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
            st.download_button("📥 Descargar CSV", csv, "costos_moraes.csv", "text/csv", key="dl_costos")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 6 — Proveedores
# Wireframe: KPIs → [Pie tipo][Ranking][Detalle] → Table
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

        # KPIs
        m1, m2, m3 = st.columns(3)
        m1.metric("👥 Total Proveedores", total_prov)
        m2.metric("📞 Con Teléfono", int(con_tel))
        m3.metric("🏷️ Tipo Principal", tipo_principal)

        styled_separator()

        # Apply sidebar filters
        df_pv = df_proveedores.copy()
        if busqueda_prov:
            mask = df_pv.apply(lambda row: busqueda_prov.lower() in " ".join(row.astype(str)).lower(), axis=1)
            df_pv = df_pv[mask]
        if sel_tipo_prov and "Tipo de proveedor" in df_pv.columns:
            df_pv = df_pv[df_pv["Tipo de proveedor"].isin(sel_tipo_prov)]

        if df_pv.empty:
            st.warning("No se encontraron proveedores.")
        else:
            # Row 1: [Pie tipo] [Ranking] [Detalle expanders]
            r1c1, r1c2, r1c3 = st.columns(3)

            with r1c1:
                section_title("📊", "Proveedores por Tipo")
                if "Tipo de proveedor" in df_pv.columns:
                    tipo_count = df_pv.groupby("Tipo de proveedor").size().reset_index(name="Cantidad")
                    fig = px.pie(tipo_count, names="Tipo de proveedor", values="Cantidad", hole=0.5, color_discrete_sequence=COLOR_SEQ_PRIMARY)
                    apply_chart_theme(fig, height=380)
                    fig.update_traces(
                        textinfo="percent+label", textfont=dict(size=11, color=COLORS["text"]),
                        marker=dict(line=dict(color=COLORS["bg_dark"], width=2)),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            with r1c2:
                section_title("🏆", "Más Usados en Pedidos")
                if not df_pedidos.empty and COL_P_PROVEEDOR in df_pedidos.columns:
                    top_prov = df_pedidos[COL_P_PROVEEDOR].value_counts().head(5).reset_index()
                    top_prov.columns = ["Proveedor", "Pedidos"]
                    for idx, row in top_prov.iterrows():
                        rank = idx + 1
                        st.markdown(f"""
                        <div style="background:{COLORS['bg_card']};border:1px solid {COLORS['border']};
                             border-left:3px solid {COLORS['secondary']};border-radius:8px;padding:10px 14px;margin-bottom:6px;">
                            <div style="font-weight:600;color:{COLORS['text']};font-size:0.9rem;">#{rank} {row['Proveedor']}</div>
                            <div style="color:{COLORS['text_muted']};font-size:0.8rem;">{row['Pedidos']} pedidos</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("No hay datos de pedidos para cruzar.")

            with r1c3:
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

            # Table + Download
            section_title("📋", "Vista de Tabla")
            st.dataframe(
                df_pv, use_container_width=True, hide_index=True,
                column_config={
                    "Sitio web": st.column_config.LinkColumn("Sitio Web"),
                    "Confiabilidad": st.column_config.TextColumn("Confiabilidad"),
                },
            )
            csv = df_pv.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Descargar CSV", csv, "proveedores_moraes.csv", "text/csv", key="dl_prov")


# ── Footer ───────────────────────────────────────────────────────────────────
styled_separator()
render_footer()
