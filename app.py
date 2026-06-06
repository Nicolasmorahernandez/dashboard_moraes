import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle
from datetime import datetime

st.set_page_config(
    page_title="MORAES Dashboard",
    page_icon="🦎",
    layout="wide",
    initial_sidebar_state="collapsed"
)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

SHEET_FINANZAS_ID = '1ODzs4-V__I5uN5mcbwJrUwIKrDrK6nn-wlii-eKNEhg'
SHEET_AMAZON_ID   = '1TX0azfGSqKNRhMqKg_VS3iRHx0RMNPWnKGbq3Pwf8cQ'

# Los SKU de Amazon son distintos a los internos pero referencian el mismo producto.
# Se normalizan al SKU interno para que las ventas se consoliden por producto.
SKU_MAP = {
    'BT-CX89-PS3K': '5231',   # Golf Glove Case Holder
    '96-XO2W-I9FY': '432',    # Single Bottle Wine Carrier
}

BROWN       = '#271310'
AMBER       = '#944925'
AMBER_DARK  = '#6B371B'
SURFACE     = '#1a1210'
CARD_BG     = '#211815'
CARD_BORDER = '#3a2820'
TEXT_MAIN   = '#f5ede8'
TEXT_MUTED  = '#a08070'
GREEN       = '#4ade80'
GREEN_DIM   = '#166534'
RED         = '#f87171'
RED_DIM     = '#7f1d1d'
BLUE        = '#60a5fa'
BLUE_DIM    = '#1e3a5f'
# Identidad de canales y paleta de gráficos — tonos cuero (marca)
GOLD        = '#D9A441'   # oro cálido
CH_AMAZON   = '#B5651D'   # ámbar quemado → canal Amazon
CH_DIRECTO  = '#D9A441'   # oro → canal Directo
# secuencia categórica graduada (marrón profundo → oro claro)
CHART_SEQ   = ['#3E1F12', '#6B371B', '#944925', '#B5651D', '#C8893A', '#D9A441', '#E8C170']

# ── Autenticación ─────────────────────────────────────────────────
def autenticar():
    # Streamlit Cloud: service account desde secrets
    if 'gcp_service_account' in st.secrets:
        return gspread.service_account_from_dict(dict(st.secrets['gcp_service_account']))

    # Streamlit Cloud fallback: token OAuth base64
    if 'token_pickle_b64' in st.secrets:
        import base64
        creds = pickle.loads(base64.b64decode(st.secrets['token_pickle_b64']))
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return gspread.authorize(creds)

    # Local: token OAuth desde archivo
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # guardar token renovado localmente si es posible
            if not os.path.exists('/mount/src'):
                with open('token.pickle', 'wb') as f:
                    pickle.dump(creds, f)
        else:
            # Solo funciona en local (requiere browser)
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            with open('token.pickle', 'wb') as f:
                pickle.dump(creds, f)

    return gspread.authorize(creds)

# ── Carga de datos ────────────────────────────────────────────────
@st.cache_data(ttl=300)
def cargar_gastos_operativos():
    try:
        gc = autenticar()
        sh = gc.open_by_key(SHEET_FINANZAS_ID)
        ws = next(s for s in sh.worksheets() if 'gastos' in s.title.lower() and 'amazon' not in s.title.lower())
        df = pd.DataFrame(ws.get_all_records(head=4))
        df.columns = [c.strip() for c in df.columns]
        df['Monto Total (USD)'] = pd.to_numeric(
            df['Monto Total (USD)'].astype(str).str.replace('[$,]', '', regex=True), errors='coerce'
        ).fillna(0)
        df = df[df['Fecha'].astype(str).str.strip() != '']
        # excluir filas de totales / leyenda que no son gastos reales
        df = df[~df['Fecha'].astype(str).str.strip().str.upper().str.startswith('TOTAL')]
        df = df[~df['Fecha'].astype(str).str.contains('🔴|Fondo rojo|Categorías', na=False)]
        df['Pagado'] = df['¿Pagado?'].astype(str).str.contains('✅|TRUE|true|si|sí', case=False)
        if 'Canal' not in df.columns:
            df['Canal'] = 'Ambos'
        df['Canal'] = df['Canal'].astype(str).str.strip()
        if 'Tipo' not in df.columns:
            df['Tipo'] = 'Directo'
        df['Tipo'] = df['Tipo'].astype(str).str.strip()
        if '¿En inventario?' not in df.columns:
            df['¿En inventario?'] = 'No'
        df['En inventario'] = df['¿En inventario?'].astype(str).str.strip().str.lower().isin(['sí','si','yes','true'])
        return df
    except Exception as e:
        st.error(f"Error Gastos Operativos: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_ventas():
    try:
        gc = autenticar()
        frames = []
        sh1 = gc.open_by_key(SHEET_FINANZAS_ID)
        ws1 = next((s for s in sh1.worksheets() if 'ventas' in s.title.lower()), None)
        if ws1:
            h = ['Fecha','Producto','SKU','Canal','Unidades','Precio Unit (USD)','Total (USD)','Cuenta','Notas']
            df1 = pd.DataFrame(ws1.get_all_records(head=3, expected_headers=h))
            df1.columns = [c.strip() for c in df1.columns]
            df1 = df1[df1['Fecha'].astype(str).str.strip() != '']
            frames.append(df1)
        sh2 = gc.open_by_key(SHEET_AMAZON_ID)
        ws2 = next((s for s in sh2.worksheets() if s.title.strip() == 'Ventas Amazon'), None)
        if ws2:
            df2 = pd.DataFrame(ws2.get_all_records(head=3))
            df2.columns = [c.strip() for c in df2.columns]
            df2 = df2[df2['Fecha'].astype(str).str.strip() != '']
            df2 = df2.rename(columns={
                'Cantidad': 'Unidades',
                'Precio Unitario (USD)': 'Precio Unit (USD)',
                'Ingreso Total (USD)': 'Total (USD)',
                'Fulfillment': 'Cuenta',
            })
            if 'Canal' not in df2.columns:
                df2['Canal'] = 'Amazon'
            if 'Notas' not in df2.columns:
                df2['Notas'] = ''
            frames.append(df2[['Fecha','Producto','SKU','Canal','Unidades','Precio Unit (USD)','Total (USD)','Cuenta','Notas']])
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if df.empty:
            return df
        # normalizar SKU de Amazon → SKU interno (mismo producto)
        df['SKU'] = df['SKU'].astype(str).str.strip().replace(SKU_MAP)
        for col in ['Total (USD)', 'Precio Unit (USD)']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace('[$,]', '', regex=True), errors='coerce').fillna(0)
        df['Unidades'] = pd.to_numeric(df['Unidades'], errors='coerce').fillna(0)
        cuenta = df['Cuenta'].astype(str).str.strip().str.upper()
        df['Cobrado'] = ~(cuenta.str.contains('NO HAN PAGADO|NO PAGADO', na=False) | (cuenta == ''))
        return df
    except Exception as e:
        st.error(f"Error Ventas: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_margenes():
    try:
        gc = autenticar()
        sh = gc.open_by_key(SHEET_FINANZAS_ID)
        ws = next(s for s in sh.worksheets() if 'rgen' in s.title.lower() or 'argen' in s.title.lower())
        h = ['SKU','Canal','Costo COP','Costo USD','Envío','Empaque','Publicidad','Comisión','Costo Total','Precio Venta','Ganancia','Margen %','ROI %']
        df = pd.DataFrame(ws.get_all_records(head=3, expected_headers=h))
        df.columns = [c.strip() for c in df.columns]
        for col in ['Costo Total', 'Precio Venta', 'Ganancia']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace('[$,%]', '', regex=True), errors='coerce').fillna(0)
        df = df[df['SKU'].astype(str).str.strip() != '']
        df = df[~df['SKU'].astype(str).str.startswith('*')]
        return df
    except Exception as e:
        st.error(f"Error Márgenes: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_gastos_amazon():
    try:
        gc = autenticar()
        sh = gc.open_by_key(SHEET_AMAZON_ID)
        ws = next(s for s in sh.worksheets() if 'gastos amazon' in s.title.lower() or ('amazon' in s.title.lower() and 'gasto' in s.title.lower()))
        h = ['Transaction ID','Fecha','Order ID','Tipo de Fee','SKU','Monto (USD)','Descripcion']
        df = pd.DataFrame(ws.get_all_records(head=2, expected_headers=h))
        df.columns = [c.strip() for c in df.columns]
        df['Monto (USD)'] = pd.to_numeric(df['Monto (USD)'].astype(str).str.replace('[$,]', '', regex=True), errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Error Gastos Amazon: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_inventario():
    try:
        gc = autenticar()
        sh = gc.open_by_key(SHEET_FINANZAS_ID)
        ws = next(s for s in sh.worksheets() if 'inventario' in s.title.lower())
        df = pd.DataFrame(ws.get_all_records(head=4))
        df.columns = [c.strip() for c in df.columns]
        for col in ['Stock (ajustable)', 'Costo Unit. (USD)', 'Valor en Stock (USD)', 'Precio Mercado (USD)', 'Valor a Mercado (USD)']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace('[$,]', '', regex=True), errors='coerce').fillna(0)
        # solo filas de producto real: SKU no vacío, sin TOTAL ni ⚠️, costo > 0
        df = df[df['SKU'].astype(str).str.strip() != '']
        df = df[~df['SKU'].astype(str).str.strip().str.upper().str.startswith('TOTAL')]
        df = df[df['Costo Unit. (USD)'] > 0]
        if 'Canal' not in df.columns:
            df['Canal'] = 'Directo'
        df['Canal'] = df['Canal'].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Error Inventario: {e}")
        return pd.DataFrame()

# ── Estilos ───────────────────────────────────────────────────────
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

  html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
    background-color: {SURFACE};
    color: {TEXT_MAIN};
  }}
  .stApp {{ background-color: {SURFACE}; }}

  /* Header */
  .dash-header {{
    background: linear-gradient(135deg, #2d1a14 0%, #1a0e0a 100%);
    border: 1px solid {CARD_BORDER};
    border-radius: 16px;
    padding: 24px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
  }}
  .dash-header-left {{ display: flex; align-items: center; gap: 16px; }}
  .dash-logo {{ font-size: 2.2rem; }}
  .dash-title {{ font-size: 1.6rem; font-weight: 700; color: {TEXT_MAIN}; margin: 0; }}
  .dash-subtitle {{ font-size: 0.8rem; color: {TEXT_MUTED}; margin: 0; letter-spacing: 0.06em; text-transform: uppercase; }}
  .dash-date {{ font-size: 0.85rem; color: {TEXT_MUTED}; background: rgba(255,255,255,0.05); padding: 6px 14px; border-radius: 20px; border: 1px solid {CARD_BORDER}; }}

  /* Sección label */
  .section-label {{
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase;
    color: {TEXT_MUTED}; margin-bottom: 10px; margin-top: 4px;
  }}

  /* KPI card */
  .kpi-card {{
    background: {CARD_BG};
    border: 1px solid {CARD_BORDER};
    border-radius: 12px;
    padding: 20px 22px;
    height: 100%;
  }}
  .kpi-card-top {{ border-top: 3px solid; }}
  .kpi-icon {{ font-size: 1.4rem; margin-bottom: 8px; }}
  .kpi-label {{ font-size: 0.7rem; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: {TEXT_MUTED}; margin-bottom: 4px; }}
  .kpi-value {{ font-size: 1.7rem; font-weight: 700; line-height: 1.1; }}
  .kpi-sub {{ font-size: 0.75rem; color: {TEXT_MUTED}; margin-top: 6px; }}
  .kpi-badge {{
    display: inline-block; font-size: 0.68rem; font-weight: 600; padding: 2px 8px;
    border-radius: 20px; margin-top: 8px; letter-spacing: 0.04em;
  }}
  .badge-green {{ background: {GREEN_DIM}; color: {GREEN}; }}
  .badge-red   {{ background: {RED_DIM};   color: {RED}; }}
  .badge-blue  {{ background: {BLUE_DIM};  color: {BLUE}; }}
  .badge-amber {{ background: #3d1f0a;     color: #fb923c; }}

  /* Canal card */
  .canal-card {{
    background: {CARD_BG}; border: 1px solid {CARD_BORDER};
    border-radius: 12px; padding: 20px 22px;
  }}
  .canal-name {{ font-size: 0.75rem; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: {TEXT_MUTED}; }}
  .canal-value {{ font-size: 1.4rem; font-weight: 700; margin: 4px 0; }}
  .canal-row {{ display: flex; justify-content: space-between; align-items: baseline; margin-top: 10px; }}
  .canal-stat {{ text-align: right; }}
  .canal-stat-label {{ font-size: 0.65rem; color: {TEXT_MUTED}; text-transform: uppercase; letter-spacing: 0.08em; }}
  .canal-stat-value {{ font-size: 0.95rem; font-weight: 600; }}

  /* Chart card */
  .chart-card {{
    background: {CARD_BG}; border: 1px solid {CARD_BORDER};
    border-radius: 12px; padding: 20px 22px; margin-bottom: 16px;
  }}
  .chart-title {{ font-size: 0.8rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: {TEXT_MUTED}; margin-bottom: 12px; }}

  /* Divider */
  .divider {{ border: none; border-top: 1px solid {CARD_BORDER}; margin: 20px 0; }}

  /* Override Streamlit metrics */
  div[data-testid="metric-container"] {{ display: none !important; }}

  /* Sidebar */
  section[data-testid="stSidebar"] {{ background: #160e0b; border-right: 1px solid {CARD_BORDER}; }}

  /* Plotly charts transparent bg */
  .js-plotly-plot .plotly {{ background: transparent !important; }}

  /* Dash table */
  .dash-table {{ width:100%; border-collapse:collapse; font-family:'Inter',sans-serif; font-size:0.8rem; }}
  .dash-table thead tr {{ background:{CARD_BORDER}; }}
  .dash-table thead th {{
    padding:10px 14px; text-align:left; font-size:0.68rem; font-weight:600;
    letter-spacing:0.1em; text-transform:uppercase; color:{TEXT_MUTED};
    border-bottom:2px solid {AMBER_DARK};
  }}
  .dash-table tbody tr {{ border-bottom:1px solid {CARD_BORDER}; transition:background 150ms; }}
  .dash-table tbody tr:hover {{ background:rgba(148,73,37,0.08); }}
  .dash-table tbody td {{ padding:10px 14px; color:{TEXT_MAIN}; vertical-align:middle; }}
  .dash-table tbody tr:last-child {{ border-bottom:none; }}

  /* ── Mobile responsive (≤ 768px) ───────────────────────────── */
  @media (max-width: 768px) {{

    /* Header compacto */
    .dash-header {{
      flex-direction: column;
      align-items: flex-start;
      padding: 16px;
      gap: 10px;
    }}
    .dash-title {{ font-size: 1.2rem; }}
    .dash-subtitle {{ font-size: 0.68rem; }}
    .dash-date {{ font-size: 0.75rem; padding: 4px 10px; }}
    .dash-header > div:last-child {{ flex-wrap: wrap; gap: 6px; }}

    /* Cards: padding reducido */
    .kpi-card {{ padding: 14px 16px; }}
    .kpi-value {{ font-size: 1.4rem; }}
    .canal-card {{ padding: 14px 16px; }}
    .canal-row {{ flex-direction: column; gap: 8px; align-items: flex-start; }}
    .canal-stat {{ text-align: left; }}

    /* P&L: scroll horizontal (tiene inline flex:0 0 260px que no se puede pisar) */
    .chart-card {{ overflow-x: auto; }}

    /* Streamlit column overrides — usa data-testid internos de Streamlit (no API pública).
       Si Streamlit cambia su DOM en futuras versiones, revisar estos selectores.
       !important necesario para pisar los estilos inline que Streamlit inyecta en columnas. */

    /* KPIs 5-col → grid 2×2+1 */
    .mobile-kpi-grid [data-testid="stHorizontalBlock"] {{
      flex-wrap: wrap !important;
    }}
    .mobile-kpi-grid [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
      flex: 0 0 50% !important;
      max-width: 50% !important;
      min-width: 50% !important;
    }}

    /* Canales 3-col → 1 columna apilada */
    .mobile-canal-grid [data-testid="stHorizontalBlock"] {{
      flex-direction: column !important;
    }}
    .mobile-canal-grid [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
      flex: 0 0 100% !important;
      max-width: 100% !important;
      min-width: 100% !important;
    }}

    /* Inventario KPIs 3-col → 2+1 */
    .mobile-inv-grid [data-testid="stHorizontalBlock"] {{
      flex-wrap: wrap !important;
    }}
    .mobile-inv-grid [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
      flex: 0 0 50% !important;
      max-width: 50% !important;
      min-width: 50% !important;
    }}

    /* Gráficos Plotly y donut: ocultos en mobile */
    .mobile-hidden {{ display: none !important; }}

    /* Espaciado general */
    .section-label {{ font-size: 0.65rem; }}
    [data-testid="stAppViewContainer"] {{ padding: 0 8px !important; }}
  }}
</style>
""", unsafe_allow_html=True)

# ── Cargar datos ──────────────────────────────────────────────────
with st.spinner("Sincronizando con Google Sheets..."):
    df_gastos   = cargar_gastos_operativos()
    df_ventas   = cargar_ventas()
    df_margenes = cargar_margenes()
    df_amazon   = cargar_gastos_amazon()
    df_inv      = cargar_inventario()

# ── Filtro de mes (sidebar colapsado) ────────────────────────────
with st.sidebar:
    st.markdown(f"<p style='color:{AMBER};font-weight:700;font-size:1rem;'>MORAES</p>", unsafe_allow_html=True)
    st.markdown("---")
    meses_orden = ['Oct 2025','Nov 2025','Dic 2025','Ene 2026','Feb 2026','Mar 2026','Abr 2026','May 2026']
    mes_sel = st.selectbox("Período", ["Todos"] + meses_orden)
    st.markdown("---")
    if st.button("🔄 Actualizar"):
        st.cache_data.clear()
        st.rerun()
    st.markdown(f"<small style='color:{TEXT_MUTED}'>MORAES Leather © 2026</small>", unsafe_allow_html=True)

def filtrar(df, col='Fecha'):
    if mes_sel == "Todos" or df.empty or col not in df.columns:
        return df
    return df[df[col].astype(str).str.contains(mes_sel.split()[0], case=False, na=False)]

df_g = filtrar(df_gastos)
df_v = filtrar(df_ventas)

# ── Cálculos ──────────────────────────────────────────────────────
# Escenario: caja real (default) vs proyectado (todo cobrado + gastos pagados).
# El widget toggle se renderiza debajo del header; aquí leemos su estado.
proyectado = st.session_state.get('proy_toggle', False)

# Ventas cobradas (caja real) vs por cobrar (comprometido)
df_v_cob = df_v[df_v['Cobrado']] if not df_v.empty and 'Cobrado' in df_v.columns else df_v
# Fuentes según escenario: en proyectado se asume todo cobrado / todo pagado
df_v_ing = df_v if proyectado else df_v_cob
_df_g_base = df_g if proyectado else (df_g[df_g['Pagado']] if not df_g.empty else df_g)
# Siempre excluir costos de inventario no vendido del P&L y canales
# (independiente del Proyectado — esos costos se activan manualmente cuando se vende)
df_g_pag = (
    _df_g_base[~_df_g_base['En inventario']]
    if not _df_g_base.empty and 'En inventario' in _df_g_base.columns
    else _df_g_base
)

total_ingresos      = df_v_ing['Total (USD)'].sum() if not df_v_ing.empty else 0
ingresos_por_cobrar = 0 if proyectado else (df_v[~df_v['Cobrado']]['Total (USD)'].sum() if (not df_v.empty and 'Cobrado' in df_v.columns) else 0)
total_gastos_pag    = df_g_pag['Monto Total (USD)'].sum() if not df_g_pag.empty else 0
pendientes          = 0 if proyectado else (df_g[~df_g['Pagado']]['Monto Total (USD)'].sum() if not df_g.empty else 0)
utilidad_total      = total_ingresos - total_gastos_pag
rentabilidad_total  = (utilidad_total / total_ingresos * 100) if total_ingresos else 0

amazon_ing          = df_v_ing[df_v_ing['Canal']=='Amazon']['Total (USD)'].sum() if not df_v_ing.empty else 0
directo_ing         = df_v_ing[df_v_ing['Canal']=='Directo']['Total (USD)'].sum() if not df_v_ing.empty else 0
gastos_amazon_total = df_amazon['Monto (USD)'].sum() if not df_amazon.empty else 0

# Gastos por canal: solo Tipo='Directo' (COGS, envíos, empaques producto)
# Estructura queda a nivel empresa en el P&L — no se carga a canales
_pct_amz = (amazon_ing / (amazon_ing + directo_ing)) if (amazon_ing + directo_ing) else 0.5
if not df_g_pag.empty and 'Canal' in df_g_pag.columns and 'Tipo' in df_g_pag.columns:
    _dg_canal = df_g_pag[df_g_pag['Tipo']=='Directo']  # solo costos directos
    _g_amazon  = _dg_canal[_dg_canal['Canal']=='Amazon']['Monto Total (USD)'].sum()
    _g_directo = _dg_canal[_dg_canal['Canal']=='Directo']['Monto Total (USD)'].sum()
    _g_ambos   = _dg_canal[_dg_canal['Canal']=='Ambos']['Monto Total (USD)'].sum()
    gastos_canal_amazon  = _g_amazon  + _g_ambos * _pct_amz
    gastos_no_amazon     = _g_directo + _g_ambos * (1 - _pct_amz)
else:
    gastos_canal_amazon  = 0
    gastos_no_amazon     = total_gastos_pag - abs(gastos_amazon_total)

neto_amazon          = amazon_ing + gastos_amazon_total - gastos_canal_amazon
rentabilidad_amazon  = (neto_amazon / amazon_ing * 100) if amazon_ing else 0
neto_directo         = directo_ing - gastos_no_amazon
rentabilidad_directo = (neto_directo / directo_ing * 100) if directo_ing else 0

# ── P&L en dos niveles: Margen de Contribución y Utilidad Operativa ──
# Costos directos = gastos Tipo='Directo' (COGS, envíos, empaques producto)
# Gastos estructura = gastos Tipo='Estructura' (equipos, logos, dominios, marketing)
if not df_g_pag.empty and 'Tipo' in df_g_pag.columns:
    costos_directos   = df_g_pag[df_g_pag['Tipo']=='Directo']['Monto Total (USD)'].sum()
    gastos_estructura = df_g_pag[df_g_pag['Tipo']=='Estructura']['Monto Total (USD)'].sum()
else:
    costos_directos   = total_gastos_pag
    gastos_estructura = 0
margen_contribucion     = total_ingresos - costos_directos
margen_contribucion_pct = (margen_contribucion / total_ingresos * 100) if total_ingresos else 0
utilidad_operativa      = margen_contribucion - gastos_estructura
utilidad_operativa_pct  = (utilidad_operativa / total_ingresos * 100) if total_ingresos else 0

# Ganancia potencial del inventario — siempre con rentabilidad limpia
# (accrual: pagado + sin inventario pendiente + sin proyectado)
# independiente de los toggles, para no distorsionar con gastos futuros
_dg_limpio = df_gastos.copy() if not df_gastos.empty else pd.DataFrame()
if not _dg_limpio.empty:
    _dg_limpio = _dg_limpio[_dg_limpio['Pagado']]
    if 'En inventario' in _dg_limpio.columns:
        _dg_limpio = _dg_limpio[~_dg_limpio['En inventario']]
_amz_ing_l   = df_ventas[df_ventas['Canal']=='Amazon']['Total (USD)'].sum() if not df_ventas.empty and 'Cobrado' not in df_ventas.columns else (df_ventas[df_ventas['Cobrado'] & (df_ventas['Canal']=='Amazon')]['Total (USD)'].sum() if not df_ventas.empty else 0)
_dir_ing_l   = df_ventas[df_ventas['Canal']=='Directo']['Total (USD)'].sum() if not df_ventas.empty and 'Cobrado' not in df_ventas.columns else (df_ventas[df_ventas['Cobrado'] & (df_ventas['Canal']=='Directo')]['Total (USD)'].sum() if not df_ventas.empty else 0)
# usar ventas cobradas para la rentabilidad limpia
_dv_cob      = df_ventas[df_ventas['Cobrado']] if not df_ventas.empty and 'Cobrado' in df_ventas.columns else df_ventas
_amz_ing_l   = _dv_cob[_dv_cob['Canal']=='Amazon']['Total (USD)'].sum()  if not _dv_cob.empty else 0
_dir_ing_l   = _dv_cob[_dv_cob['Canal']=='Directo']['Total (USD)'].sum() if not _dv_cob.empty else 0
_pct_amz_l   = (_amz_ing_l / (_amz_ing_l + _dir_ing_l)) if (_amz_ing_l + _dir_ing_l) else 0.5
if not _dg_limpio.empty and 'Canal' in _dg_limpio.columns and 'Tipo' in _dg_limpio.columns:
    _dc_l    = _dg_limpio[_dg_limpio['Tipo']=='Directo']
    _ga_l    = _dc_l[_dc_l['Canal']=='Amazon']['Monto Total (USD)'].sum()
    _gd_l    = _dc_l[_dc_l['Canal']=='Directo']['Monto Total (USD)'].sum()
    _gab_l   = _dc_l[_dc_l['Canal']=='Ambos']['Monto Total (USD)'].sum()
    _gc_amz_l = _ga_l + _gab_l * _pct_amz_l
    _gc_dir_l = _gd_l + _gab_l * (1 - _pct_amz_l)
else:
    _gc_amz_l = 0; _gc_dir_l = 0
_fees_l       = df_amazon['Monto (USD)'].sum() if not df_amazon.empty else 0
_neto_amz_l   = _amz_ing_l + _fees_l - _gc_amz_l
_neto_dir_l   = _dir_ing_l - _gc_dir_l
_ra_limpio    = (_neto_amz_l / _amz_ing_l)  if _amz_ing_l  else 0
_rd_limpio    = (_neto_dir_l / _dir_ing_l)  if _dir_ing_l  else 0

if not df_inv.empty and 'Canal' in df_inv.columns:
    inv_gan_potencial = df_inv.apply(
        lambda r: r['Valor a Mercado (USD)'] * (_ra_limpio if r.get('Canal','Directo')=='Amazon' else _rd_limpio), axis=1
    ).sum()
    inv_mercado_total = df_inv['Valor a Mercado (USD)'].sum()
    inv_uds_total     = int(df_inv['Stock (ajustable)'].sum())
else:
    inv_gan_potencial = 0
    inv_mercado_total = 0
    inv_uds_total     = 0

unidades_amazon  = int(df_v[df_v['Canal']=='Amazon']['Unidades'].sum()) if not df_v.empty else 0
unidades_directo = int(df_v[df_v['Canal']=='Directo']['Unidades'].sum()) if not df_v.empty else 0
# mezcla por canal sobre TODAS las ventas (actividad comercial, no caja)
ventas_tot_all   = df_v['Total (USD)'].sum() if not df_v.empty else 0
amazon_ing_all   = df_v[df_v['Canal']=='Amazon']['Total (USD)'].sum() if not df_v.empty else 0
amazon_pct       = (amazon_ing_all / ventas_tot_all * 100) if ventas_tot_all else 0

# ── Header ────────────────────────────────────────────────────────
now = datetime.now().strftime("%d/%m/%Y %H:%M")
modo_chip = (
    '<span style="font-size:0.85rem;background:#3d1f0a;color:#fb923c;border:1px solid #5a3010;padding:6px 14px;border-radius:20px;">🔮 Proyectado</span>'
    if proyectado else
    '<span style="display:none;"></span>'
)
fecha_chip = f'<span style="font-size:0.85rem;color:{TEXT_MUTED};background:rgba(255,255,255,0.05);padding:6px 14px;border-radius:20px;border:1px solid {CARD_BORDER};">📅 {now} · {mes_sel}</span>'

st.markdown(f"""<div class="dash-header">
  <div class="dash-header-left">
    <div class="dash-logo">🦎</div>
    <div>
      <p class="dash-title">MORAES LEATHER</p>
      <p class="dash-subtitle">Dashboard financiero · Google Sheets en tiempo real</p>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:10px;">{modo_chip}{fecha_chip}</div>
</div>""", unsafe_allow_html=True)

# ── Toggle de escenario ───────────────────────────────────────────
_tg1, _tg2 = st.columns([3, 1])
with _tg2:
    st.toggle("🔮 Proyectado (todo cobrado y pagado)", key="proy_toggle",
              help="Asume que se cobraron todas las ventas y se pagaron todos los gastos pendientes.")

def dash_table(df):
    """Renderiza un DataFrame como tabla HTML con estilo del dashboard."""
    return st.write(
        '<div style="overflow-x:auto;">' +
        df.to_html(classes='dash-table', index=False, escape=False, border=0) +
        '</div>',
        unsafe_allow_html=True
    )

# ── P&L en cascada ───────────────────────────────────────────────
st.markdown('<p class="section-label">P&L — Estado de resultados</p>', unsafe_allow_html=True)
st.markdown('<div class="chart-card">', unsafe_allow_html=True)

def _pct_bar(pct, color):
    w = min(abs(pct), 100)
    return f'<div style="flex:1;background:#2a1a14;border-radius:3px;height:5px;"><div style="background:{color};width:{w:.0f}%;height:5px;border-radius:3px;"></div></div>'

def _pl_row(label, valor, pct, color, bold=False, indent=0, divider=False):
    pad   = f"padding-left:{indent*20}px;" if indent else ""
    fw    = "font-weight:700;" if bold else ""
    sign  = "+" if valor >= 0 else "−"
    val_s = f"{sign}${abs(valor):,.2f}"
    pct_s = f"{pct:+.1f}%" if pct != 0 else ""
    bar   = _pct_bar(pct, color)
    div   = f'<hr style="border:none;border-top:1px solid #3a2820;margin:6px 0;">' if divider else ''
    return f'''{div}<div style="display:flex;align-items:center;gap:12px;padding:6px 0;{pad}">
  <span style="flex:0 0 260px;font-family:Manrope,sans-serif;font-size:0.8rem;{fw}color:{'#f5ede8' if bold else '#a08070'};">{label}</span>
  {bar}
  <span style="flex:0 0 90px;text-align:right;font-family:Manrope,sans-serif;font-size:0.85rem;{fw}color:{color};">{val_s}</span>
  <span style="flex:0 0 60px;text-align:right;font-family:Manrope,sans-serif;font-size:0.75rem;color:#a08070;">{pct_s}</span>
</div>'''

html  = _pl_row("Ingresos cobrados",         total_ingresos,         100,                    GOLD,  bold=True)
html += _pl_row("− Costos directos",          -costos_directos,       -costos_directos/total_ingresos*100 if total_ingresos else 0, RED,   indent=1)
html += _pl_row("= Margen de contribución",   margen_contribucion,    margen_contribucion_pct,GREEN if margen_contribucion>=0 else RED, bold=True, divider=True)
html += _pl_row("− Gastos de estructura",     -gastos_estructura,     -gastos_estructura/total_ingresos*100 if total_ingresos else 0, RED,   indent=1)
html += _pl_row("= Utilidad operativa",       utilidad_operativa,     utilidad_operativa_pct, GREEN if utilidad_operativa>=0 else RED, bold=True, divider=True)

st.markdown(html, unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── Fila 1: KPIs principales ──────────────────────────────────────
st.markdown('<p class="section-label">Resumen general</p>', unsafe_allow_html=True)

def badge(val, fmt="pct"):
    if fmt == "pct":
        txt = f"{'▲' if val >= 0 else '▼'} {abs(val):.1f}%"
    else:
        txt = f"{'▲' if val >= 0 else '▼'} ${abs(val):,.0f}"
    cls = "badge-green" if val >= 0 else "badge-red"
    return f'<span class="kpi-badge {cls}">{txt}</span>'

k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.markdown(f"""
    <div class="kpi-card kpi-card-top" style="border-top-color:{GOLD};">
      <div class="kpi-icon">💰</div>
      <div class="kpi-label">{'Ingresos proyectados' if proyectado else 'Ingresos cobrados'}</div>
      <div class="kpi-value" style="color:{GOLD};">${total_ingresos:,.2f}</div>
      <div class="kpi-sub">Por cobrar: ${ingresos_por_cobrar:,.2f} · {unidades_amazon + unidades_directo} unidades</div>
      <span class="kpi-badge badge-amber">Amazon {amazon_pct:.0f}% · Directo {100-amazon_pct:.0f}%</span>
    </div>""", unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div class="kpi-card kpi-card-top" style="border-top-color:#f97316;">
      <div class="kpi-icon">📤</div>
      <div class="kpi-label">Gastos pagados</div>
      <div class="kpi-value" style="color:#f97316;">${total_gastos_pag:,.2f}</div>
      <div class="kpi-sub">Pendientes: ${pendientes:,.2f}</div>
      <span class="kpi-badge badge-amber">Fees Amazon ${abs(gastos_amazon_total):,.0f}</span>
    </div>""", unsafe_allow_html=True)

with k3:
    c = GREEN if utilidad_total >= 0 else RED
    st.markdown(f"""
    <div class="kpi-card kpi-card-top" style="border-top-color:{c};">
      <div class="kpi-icon">{'📈' if utilidad_total >= 0 else '📉'}</div>
      <div class="kpi-label">Utilidad neta</div>
      <div class="kpi-value" style="color:{c};">${utilidad_total:,.2f}</div>
      <div class="kpi-sub">Ingresos − Gastos pagados</div>
      {badge(rentabilidad_total)}
    </div>""", unsafe_allow_html=True)

with k4:
    c4 = GREEN if rentabilidad_total >= 0 else RED
    st.markdown(f"""
    <div class="kpi-card kpi-card-top" style="border-top-color:{AMBER};">
      <div class="kpi-icon">🎯</div>
      <div class="kpi-label">Rentabilidad total</div>
      <div class="kpi-value" style="color:{AMBER};">{rentabilidad_total:.1f}%</div>
      <div class="kpi-sub">Utilidad / Ingresos cobrados</div>
      {badge(utilidad_total, "usd")}
    </div>""", unsafe_allow_html=True)

with k5:
    if proyectado:
        _k5_val   = inv_gan_potencial
        _k5_label = 'Ganancia potencial inv.'
        _k5_sub   = f'Valor a mercado: ${inv_mercado_total:,.2f}'
        _k5_badge = f'<span class="kpi-badge badge-amber">{inv_uds_total} uds en stock</span>'
        _k5_color = GREEN if inv_gan_potencial >= 0 else RED
        _k5_icon  = '📈'
    else:
        _k5_val   = inv_mercado_total
        _k5_label = 'Inventario a mercado'
        _k5_sub   = f'Gan. potencial: ${inv_gan_potencial:,.2f} · {inv_uds_total} uds'
        _k5_badge = f'<span class="kpi-badge badge-amber">Amazon 21.7% · Directo {rentabilidad_directo:.1f}%</span>'
        _k5_color = AMBER_DARK
        _k5_icon  = '📦'
    st.markdown(f"""
    <div class="kpi-card kpi-card-top" style="border-top-color:{_k5_color};">
      <div class="kpi-icon">{_k5_icon}</div>
      <div class="kpi-label">{_k5_label}</div>
      <div class="kpi-value" style="color:{_k5_color};">${_k5_val:,.2f}</div>
      <div class="kpi-sub">{_k5_sub}</div>
      {_k5_badge}
    </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ── Fila 2: Canales ───────────────────────────────────────────────
_cl, _cr = st.columns([3,1])
with _cl:
    st.markdown('<p class="section-label">Desglose por canal</p>', unsafe_allow_html=True)
with _cr:
    con_inversion = st.toggle("📦 Con inversión pendiente", key="canal_inversion",
        help="Activa para incluir costos de inventario comprado pero aún no vendido (envíos, stock en FBA).")

# Recalcular canales según el toggle local
if con_inversion and not df_g.empty:
    # incluir también los costos marcados como "En inventario" (pagados pero de stock sin vender)
    _df_g_inv = df_g[df_g['Pagado']] if not proyectado else df_g
    _dg_c = _df_g_inv[(_df_g_inv['Tipo']=='Directo')] if 'Tipo' in _df_g_inv.columns else _df_g_inv
    _pct  = (amazon_ing/(amazon_ing+directo_ing)) if (amazon_ing+directo_ing) else 0.5
    _ga   = _dg_c[_dg_c['Canal']=='Amazon']['Monto Total (USD)'].sum()
    _gd   = _dg_c[_dg_c['Canal']=='Directo']['Monto Total (USD)'].sum()
    _gab  = _dg_c[_dg_c['Canal']=='Ambos']['Monto Total (USD)'].sum()
    _gastos_amz_c = _ga  + _gab * _pct
    _gastos_dir_c = _gd  + _gab * (1 - _pct)
    _neto_amz  = amazon_ing + gastos_amazon_total - _gastos_amz_c
    _neto_dir  = directo_ing - _gastos_dir_c
    _rent_amz  = (_neto_amz  / amazon_ing  * 100) if amazon_ing  else 0
    _rent_dir  = (_neto_dir  / directo_ing * 100) if directo_ing else 0
    _modo_label = '📦 Con inversión'
else:
    _neto_amz  = neto_amazon;        _rent_amz  = rentabilidad_amazon
    _neto_dir  = neto_directo;       _rent_dir  = rentabilidad_directo
    _gastos_amz_c = gastos_canal_amazon; _gastos_dir_c = gastos_no_amazon
    _modo_label = '✅ Sin inv. pendiente'

# En Proyectado: Amazon incluye venta proyectada del inventario en stock
if proyectado and not df_inv.empty and 'Canal' in df_inv.columns:
    _amz_inv       = df_inv[df_inv['Canal']=='Amazon']
    _amz_inv_rev   = (_amz_inv['Stock (ajustable)'] * _amz_inv['Precio Mercado (USD)']).sum()
    _fee_pct       = abs(gastos_amazon_total) / amazon_ing if amazon_ing else 0.445
    _amz_inv_fees  = _amz_inv_rev * _fee_pct
    # costos En inventario (pagados y pendientes) para Amazon
    _dg_einv = df_gastos[df_gastos['En inventario'] & (df_gastos['Canal']=='Amazon')] if not df_gastos.empty and 'En inventario' in df_gastos.columns else pd.DataFrame()
    _amz_inv_costs = _dg_einv['Monto Total (USD)'].sum() if not _dg_einv.empty else 0
    _amz_ing_proy      = amazon_ing + _amz_inv_rev
    _amz_fees_proy     = gastos_amazon_total - _amz_inv_fees   # negativo
    _amz_gastos_proy   = _gastos_amz_c + _amz_inv_costs
    _neto_amz_proy     = _amz_ing_proy + _amz_fees_proy - _amz_gastos_proy
    _rent_amz_proy     = (_neto_amz_proy / _amz_ing_proy * 100) if _amz_ing_proy else 0
    _show_amz_ing      = _amz_ing_proy
    _show_amz_costos   = _amz_gastos_proy + abs(_amz_fees_proy)
    _show_neto_amz     = _neto_amz_proy
    _show_rent_amz     = _rent_amz_proy
    _amz_uds_label     = f'{unidades_amazon} vendidas + {int(_amz_inv["Stock (ajustable)"].sum())} en stock'
else:
    _show_amz_ing    = amazon_ing
    _show_amz_costos = _gastos_amz_c + abs(gastos_amazon_total)
    _show_neto_amz   = _neto_amz
    _show_rent_amz   = _rent_amz
    _amz_uds_label   = f'{unidades_amazon} unidades'

c1, c2, c3 = st.columns(3)

with c1:
    rc = GREEN if _show_rent_amz >= 0 else RED
    st.markdown(f"""
    <div class="canal-card" style="border-top: 3px solid {CH_AMAZON};">
      <div class="canal-name">🟠 Canal Amazon{'&nbsp;&nbsp;<span style="font-size:0.65rem;background:#3d1f0a;color:#fb923c;padding:2px 7px;border-radius:10px;border:1px solid #5a3010;">🔮 Proyectado</span>' if proyectado else ''}</div>
      <div class="canal-value" style="color:{CH_AMAZON};">${_show_amz_ing:,.2f}</div>
      <div class="kpi-sub" style="color:{TEXT_MUTED};">{_amz_uds_label} · <em>{_modo_label}</em></div>
      <hr class="divider">
      <div class="canal-row">
        <div>
          <div class="canal-stat-label">Fees & costos</div>
          <div class="canal-stat-value" style="color:{RED};">${_show_amz_costos:,.2f}</div>
        </div>
        <div class="canal-stat">
          <div class="canal-stat-label">Margen Amazon</div>
          <div class="canal-stat-value" style="color:{GREEN if _show_neto_amz >= 0 else RED};">${_show_neto_amz:,.2f}</div>
        </div>
        <div class="canal-stat">
          <div class="canal-stat-label">Rentabilidad</div>
          <div class="canal-stat-value" style="color:{rc};">{_show_rent_amz:.1f}%</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

with c2:
    rd = GREEN if _rent_dir >= 0 else RED
    st.markdown(f"""
    <div class="canal-card" style="border-top: 3px solid {CH_DIRECTO};">
      <div class="canal-name">🟡 Canal Directo</div>
      <div class="canal-value" style="color:{CH_DIRECTO};">${directo_ing:,.2f}</div>
      <div class="kpi-sub" style="color:{TEXT_MUTED};">Ingresos brutos · {unidades_directo} unidades · <em>{_modo_label}</em></div>
      <hr class="divider">
      <div class="canal-row">
        <div>
          <div class="canal-stat-label">Costos directos</div>
          <div class="canal-stat-value" style="color:{RED};">${_gastos_dir_c:,.2f}</div>
        </div>
        <div class="canal-stat">
          <div class="canal-stat-label">Margen Directo</div>
          <div class="canal-stat-value" style="color:{GREEN if _neto_dir >= 0 else RED};">${_neto_dir:,.2f}</div>
        </div>
        <div class="canal-stat">
          <div class="canal-stat-label">Rentabilidad</div>
          <div class="canal-stat-value" style="color:{rd};">{_rent_dir:.1f}%</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="canal-card" style="border-top: 3px solid {AMBER};">
      <div class="canal-name">🦎 Comparativa de canales</div>
      <div style="margin-top:12px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
          <span style="color:{TEXT_MUTED};font-size:0.8rem;">Amazon</span>
          <span style="font-weight:600;color:{CH_AMAZON};">{amazon_pct:.1f}%</span>
        </div>
        <div style="background:#2a1a14;border-radius:4px;height:8px;margin-bottom:14px;">
          <div style="background:{CH_AMAZON};width:{amazon_pct:.1f}%;height:8px;border-radius:4px;"></div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
          <span style="color:{TEXT_MUTED};font-size:0.8rem;">Directo</span>
          <span style="font-weight:600;color:{CH_DIRECTO};">{100-amazon_pct:.1f}%</span>
        </div>
        <div style="background:#2a1a14;border-radius:4px;height:8px;margin-bottom:14px;">
          <div style="background:{CH_DIRECTO};width:{100-amazon_pct:.1f}%;height:8px;border-radius:4px;"></div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
          <span style="color:{TEXT_MUTED};font-size:0.8rem;">Rent. Amazon</span>
          <span style="font-weight:600;color:{'#4ade80' if _show_rent_amz>=0 else '#f87171'};">{_show_rent_amz:.1f}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;">
          <span style="color:{TEXT_MUTED};font-size:0.8rem;">Rent. Directo</span>
          <span style="font-weight:600;color:{'#4ade80' if _rent_dir>=0 else '#f87171'};">{_rent_dir:.1f}%</span>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

# ── Fila 3: Gráficos ──────────────────────────────────────────────
st.markdown('<p class="section-label">Análisis visual</p>', unsafe_allow_html=True)

PLOTLY_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(family='Inter', color=TEXT_MUTED, size=11),
    margin=dict(t=10, b=10, l=10, r=10),
)

g1, g2 = st.columns(2)

with g1:
    st.markdown('<div class="chart-card"><div class="chart-title">Ventas por canal</div>', unsafe_allow_html=True)
    if not df_v.empty:
        canal_data = df_v.groupby('Canal')['Total (USD)'].sum().reset_index()
        fig = px.pie(canal_data, values='Total (USD)', names='Canal',
                     color='Canal', color_discrete_map={'Amazon': CH_AMAZON, 'Directo': CH_DIRECTO},
                     hole=0.55)
        fig.update_traces(textposition='outside', textinfo='label+percent',
                          textfont=dict(size=11, color=TEXT_MAIN),
                          marker=dict(line=dict(color=SURFACE, width=2)))
        fig.update_layout(**PLOTLY_LAYOUT, height=260, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with g2:
    st.markdown('<div class="chart-card"><div class="chart-title">Gastos operativos por categoría</div>', unsafe_allow_html=True)
    if not df_g.empty:
        cat_col = next((c for c in df_g.columns if 'categor' in c.lower()), None)
        if cat_col:
            cat_data = df_g[df_g['Monto Total (USD)'] > 0].groupby(cat_col)['Monto Total (USD)'].sum().reset_index()
            cat_data = cat_data.sort_values('Monto Total (USD)', ascending=True)
            palette = CHART_SEQ
            fig2 = px.bar(cat_data, x='Monto Total (USD)', y=cat_col, orientation='h',
                          color=cat_col, color_discrete_sequence=palette)
            fig2.update_layout(**PLOTLY_LAYOUT, height=260, showlegend=False,
                               xaxis=dict(gridcolor=CARD_BORDER, zeroline=False),
                               yaxis=dict(gridcolor='rgba(0,0,0,0)'))
            fig2.update_traces(texttemplate='$%{x:,.0f}', textposition='outside',
                               textfont=dict(color=TEXT_MUTED, size=10))
            st.plotly_chart(fig2, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

g3, g4 = st.columns(2)

with g3:
    st.markdown('<div class="chart-card"><div class="chart-title">Ingresos por producto (SKU)</div>', unsafe_allow_html=True)
    if not df_v.empty and 'SKU' in df_v.columns:
        prod_data = df_v.groupby('SKU')['Total (USD)'].sum().reset_index().sort_values('Total (USD)', ascending=True)
        prod_data['SKU'] = prod_data['SKU'].astype(str)  # tratar SKU como categoría, no número
        fig3 = px.bar(prod_data, x='Total (USD)', y='SKU', orientation='h',
                      color_discrete_sequence=[AMBER])
        fig3.update_layout(**PLOTLY_LAYOUT, height=240, showlegend=False,
                           xaxis=dict(gridcolor=CARD_BORDER, zeroline=False),
                           yaxis=dict(gridcolor='rgba(0,0,0,0)', type='category'))
        fig3.update_traces(texttemplate='$%{x:,.0f}', textposition='outside',
                           textfont=dict(color=TEXT_MUTED, size=10))
        st.plotly_chart(fig3, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with g4:
    st.markdown('<div class="chart-card"><div class="chart-title">Costo vs Ganancia por producto</div>', unsafe_allow_html=True)
    if not df_margenes.empty:
        skus = df_margenes['SKU'].astype(str) + ' · ' + df_margenes['Canal'].astype(str)
        fig4 = go.Figure()
        fig4.add_trace(go.Bar(name='Costo', x=skus, y=df_margenes['Costo Total'],
                              marker_color='#4b3228'))
        fig4.add_trace(go.Bar(name='Ganancia', x=skus, y=df_margenes['Ganancia'],
                              marker_color=GOLD))
        fig4.update_layout(**PLOTLY_LAYOUT, barmode='stack', height=240,
                           legend=dict(orientation='h', y=1.15, font=dict(color=TEXT_MUTED, size=10)),
                           xaxis=dict(gridcolor=CARD_BORDER, tickfont=dict(size=9)),
                           yaxis=dict(gridcolor=CARD_BORDER))
        st.plotly_chart(fig4, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── Pagos pendientes ──────────────────────────────────────────────
st.markdown('<p class="section-label">Pagos pendientes</p>', unsafe_allow_html=True)
st.markdown('<div class="chart-card">', unsafe_allow_html=True)
if not df_g.empty:
    pdf = df_g[~df_g['Pagado']].copy()
    if not pdf.empty:
        cols_show = [c for c in ['Fecha','Descripción','Categoría','Monto Total (USD)','Notas'] if c in pdf.columns]
        pdf = pdf[cols_show]
        pdf['Monto Total (USD)'] = pdf['Monto Total (USD)'].apply(lambda x: f"${x:,.2f}")
        pdf = pdf.rename(columns={'Monto Total (USD)': 'Monto (USD)'})
        dash_table(pdf)
        st.markdown(f"<p style='color:{RED};font-weight:600;margin-top:8px;'>Total pendiente: ${pendientes:,.2f}</p>", unsafe_allow_html=True)
    else:
        st.markdown(f"<p style='color:{GREEN};'>✓ Sin pagos pendientes para este período.</p>", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ── Cuentas por cobrar ────────────────────────────────────────────
st.markdown('<p class="section-label">Cuentas por cobrar</p>', unsafe_allow_html=True)
st.markdown('<div class="chart-card">', unsafe_allow_html=True)
if not df_v.empty and 'Cobrado' in df_v.columns:
    cdf = df_v[~df_v['Cobrado']].copy()
    if not cdf.empty:
        cols_show = [c for c in ['Fecha','Producto','SKU','Canal','Total (USD)','Notas'] if c in cdf.columns]
        cdf = cdf[cols_show]
        cdf['Total (USD)'] = cdf['Total (USD)'].apply(lambda x: f"${x:,.2f}")
        dash_table(cdf)
        st.markdown(f"<p style='color:{RED};font-weight:600;margin-top:8px;'>Total por cobrar: ${ingresos_por_cobrar:,.2f}</p>", unsafe_allow_html=True)
    else:
        st.markdown(f"<p style='color:{GREEN};'>✓ Sin cuentas por cobrar para este período.</p>", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ── Inventario ───────────────────────────────────────────────────
st.markdown('<p class="section-label">Inventario en stock</p>', unsafe_allow_html=True)

if not df_inv.empty:
    # Ganancia potencial real = valor a mercado × rentabilidad limpia por canal
    # Usa siempre _ra_limpio/_rd_limpio (accrual, sin proyectado ni inversión pendiente)
    df_inv = df_inv.copy()
    df_inv['Ganancia Potencial (USD)'] = df_inv.apply(
        lambda r: r['Valor a Mercado (USD)'] * (_ra_limpio if r.get('Canal','Directo')=='Amazon' else _rd_limpio),
        axis=1
    )

    inv_capital   = df_inv['Valor en Stock (USD)'].sum()
    inv_mercado   = df_inv['Valor a Mercado (USD)'].sum()
    inv_ganancia  = df_inv['Ganancia Potencial (USD)'].sum()
    inv_unidades  = int(df_inv['Stock (ajustable)'].sum())
    inv_margen    = (inv_ganancia / inv_mercado * 100) if inv_mercado else 0

    ki1, ki2, ki3 = st.columns(3)
    with ki1:
        st.markdown(f"""
        <div class="kpi-card kpi-card-top" style="border-top-color:{AMBER};">
          <div class="kpi-icon">📦</div>
          <div class="kpi-label">Capital en stock (costo)</div>
          <div class="kpi-value" style="color:{AMBER};">${inv_capital:,.2f}</div>
          <div class="kpi-sub">{inv_unidades} unidades en stock</div>
        </div>""", unsafe_allow_html=True)
    with ki2:
        st.markdown(f"""
        <div class="kpi-card kpi-card-top" style="border-top-color:{GOLD};">
          <div class="kpi-icon">💎</div>
          <div class="kpi-label">Valor a mercado</div>
          <div class="kpi-value" style="color:{GOLD};">${inv_mercado:,.2f}</div>
          <div class="kpi-sub">Si se vende todo el stock actual</div>
        </div>""", unsafe_allow_html=True)
    with ki3:
        cg = GREEN if inv_ganancia >= 0 else RED
        st.markdown(f"""
        <div class="kpi-card kpi-card-top" style="border-top-color:{cg};">
          <div class="kpi-icon">{'📈' if inv_ganancia >= 0 else '📉'}</div>
          <div class="kpi-label">Ganancia potencial</div>
          <div class="kpi-value" style="color:{cg};">${inv_ganancia:,.2f}</div>
          <div class="kpi-sub">Margen {inv_margen:.1f}% sobre precio de mercado</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Tabla
    st.markdown('<div class="chart-card"><div class="chart-title" style="text-align:center;">Desglose por SKU</div>', unsafe_allow_html=True)
    tbl = df_inv[['SKU','Producto','Stock (ajustable)','Costo Unit. (USD)','Valor en Stock (USD)','Precio Mercado (USD)','Valor a Mercado (USD)','Ganancia Potencial (USD)']].copy()
    max_stock = tbl['Stock (ajustable)'].max() or 1
    def stock_bar(val):
        pct = val / max_stock * 100
        return f'<div style="display:flex;align-items:center;gap:8px;min-width:140px;"><span style="font-weight:600;min-width:32px;">{int(val)}</span><div style="flex:1;background:#2a1a14;border-radius:3px;height:6px;"><div style="background:{AMBER};width:{pct:.0f}%;height:6px;border-radius:3px;"></div></div></div>'
    tbl['Stock'] = tbl['Stock (ajustable)'].apply(stock_bar)
    tbl = tbl.drop(columns=['Stock (ajustable)'])
    tbl = tbl.rename(columns={
        'Costo Unit. (USD)': 'Costo/u',
        'Valor en Stock (USD)': 'Val. Costo',
        'Precio Mercado (USD)': 'P. Mercado',
        'Valor a Mercado (USD)': 'Val. Mercado',
        'Ganancia Potencial (USD)': 'Gan. Potencial',
    })
    for col in ['Costo/u','Val. Costo','P. Mercado','Val. Mercado','Gan. Potencial']:
        tbl[col] = tbl[col].apply(lambda x: f"${x:,.2f}")
    st.write(
        '<div style="overflow-x:auto;">'
        + tbl[['SKU','Producto','Stock','Costo/u','Val. Costo','P. Mercado','Val. Mercado','Gan. Potencial']].to_html(classes='dash-table', escape=False, index=False, border=0)
        + '</div>',
        unsafe_allow_html=True
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # Donut — mismo ancho que la tabla
    st.markdown('<div class="chart-card"><div class="chart-title" style="text-align:center;">Capital por SKU</div><div style="height:16px;"></div>', unsafe_allow_html=True)
    _, dc, _ = st.columns([1, 2, 1])
    with dc:
        fig_inv = px.pie(
            df_inv, values='Valor en Stock (USD)', names='SKU',
            hole=0.6, color_discrete_sequence=CHART_SEQ
        )
        fig_inv.update_traces(
            textposition='outside', textinfo='label+percent+value',
            texttemplate='<b>%{label}</b><br>%{percent:.0%} · $%{value:,.0f}',
            textfont=dict(size=11, color=TEXT_MAIN),
            marker=dict(line=dict(color=SURFACE, width=2))
        )
        fig_inv.update_layout(**PLOTLY_LAYOUT, height=400, showlegend=False)
        st.plotly_chart(fig_inv, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ── Tabla de márgenes ─────────────────────────────────────────────
st.markdown('<p class="section-label">Análisis de márgenes</p>', unsafe_allow_html=True)
st.markdown('<div class="chart-card">', unsafe_allow_html=True)
if not df_margenes.empty:
    dash_table(df_margenes)
st.markdown('</div>', unsafe_allow_html=True)
