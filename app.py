import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

    # Local: token OAuth desde archivo pickle
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open('token.pickle', 'wb') as f:
                    pickle.dump(creds, f)
        return gspread.authorize(creds)

    raise RuntimeError("No se encontraron credenciales. Configura gcp_service_account en Streamlit secrets.")

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
</style>
""", unsafe_allow_html=True)

# ── Cargar datos ──────────────────────────────────────────────────
with st.spinner("Sincronizando con Google Sheets..."):
    df_gastos  = cargar_gastos_operativos()
    df_ventas  = cargar_ventas()
    df_margenes = cargar_margenes()
    df_amazon  = cargar_gastos_amazon()

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
df_g_pag = df_g if proyectado else (df_g[df_g['Pagado']] if not df_g.empty else df_g)

total_ingresos      = df_v_ing['Total (USD)'].sum() if not df_v_ing.empty else 0
ingresos_por_cobrar = 0 if proyectado else (df_v[~df_v['Cobrado']]['Total (USD)'].sum() if (not df_v.empty and 'Cobrado' in df_v.columns) else 0)
total_gastos_pag    = df_g_pag['Monto Total (USD)'].sum() if not df_g_pag.empty else 0
pendientes          = 0 if proyectado else (df_g[~df_g['Pagado']]['Monto Total (USD)'].sum() if not df_g.empty else 0)
utilidad_total      = total_ingresos - total_gastos_pag
rentabilidad_total  = (utilidad_total / total_ingresos * 100) if total_ingresos else 0

amazon_ing          = df_v_ing[df_v_ing['Canal']=='Amazon']['Total (USD)'].sum() if not df_v_ing.empty else 0
directo_ing         = df_v_ing[df_v_ing['Canal']=='Directo']['Total (USD)'].sum() if not df_v_ing.empty else 0
gastos_amazon_total = df_amazon['Monto (USD)'].sum() if not df_amazon.empty else 0
neto_amazon         = amazon_ing + gastos_amazon_total
rentabilidad_amazon = (neto_amazon / amazon_ing * 100) if amazon_ing else 0

gastos_no_amazon    = total_gastos_pag - abs(gastos_amazon_total)
neto_directo        = directo_ing - gastos_no_amazon
rentabilidad_directo = (neto_directo / directo_ing * 100) if directo_ing else 0

unidades_amazon  = int(df_v[df_v['Canal']=='Amazon']['Unidades'].sum()) if not df_v.empty else 0
unidades_directo = int(df_v[df_v['Canal']=='Directo']['Unidades'].sum()) if not df_v.empty else 0
# mezcla por canal sobre TODAS las ventas (actividad comercial, no caja)
ventas_tot_all   = df_v['Total (USD)'].sum() if not df_v.empty else 0
amazon_ing_all   = df_v[df_v['Canal']=='Amazon']['Total (USD)'].sum() if not df_v.empty else 0
amazon_pct       = (amazon_ing_all / ventas_tot_all * 100) if ventas_tot_all else 0

# ── Header ────────────────────────────────────────────────────────
now = datetime.now().strftime("%d/%m/%Y %H:%M")
modo_chip = (f'<span class="dash-date" style="background:#3d1f0a;color:#fb923c;border-color:#5a3010;">🔮 Proyectado</span>'
             if proyectado else '')
st.markdown(f"""
<div class="dash-header">
  <div class="dash-header-left">
    <div class="dash-logo">🦎</div>
    <div>
      <p class="dash-title">MORAES LEATHER</p>
      <p class="dash-subtitle">Dashboard financiero · Google Sheets en tiempo real</p>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:10px;">
    {modo_chip}
    <div class="dash-date">📅 {now} · {mes_sel}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Toggle de escenario ───────────────────────────────────────────
_tg1, _tg2 = st.columns([3, 1])
with _tg2:
    st.toggle("🔮 Proyectado (todo cobrado y pagado)", key="proy_toggle",
              help="Asume que se cobraron todas las ventas y se pagaron todos los gastos pendientes.")

# ── Fila 1: KPIs principales ──────────────────────────────────────
st.markdown('<p class="section-label">Resumen general</p>', unsafe_allow_html=True)

def badge(val, fmt="pct"):
    if fmt == "pct":
        txt = f"{'▲' if val >= 0 else '▼'} {abs(val):.1f}%"
    else:
        txt = f"{'▲' if val >= 0 else '▼'} ${abs(val):,.0f}"
    cls = "badge-green" if val >= 0 else "badge-red"
    return f'<span class="kpi-badge {cls}">{txt}</span>'

k1, k2, k3, k4 = st.columns(4)

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

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ── Fila 2: Canales ───────────────────────────────────────────────
st.markdown('<p class="section-label">Desglose por canal</p>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)

with c1:
    rent_color = GREEN if rentabilidad_amazon >= 0 else RED
    st.markdown(f"""
    <div class="canal-card" style="border-top: 3px solid {CH_AMAZON};">
      <div class="canal-name">🟠 Canal Amazon</div>
      <div class="canal-value" style="color:{CH_AMAZON};">${amazon_ing:,.2f}</div>
      <div class="kpi-sub" style="color:{TEXT_MUTED};">Ingresos brutos · {unidades_amazon} unidades</div>
      <hr class="divider">
      <div class="canal-row">
        <div>
          <div class="canal-stat-label">Fees & gastos</div>
          <div class="canal-stat-value" style="color:{RED};">${gastos_amazon_total:,.2f}</div>
        </div>
        <div class="canal-stat">
          <div class="canal-stat-label">Neto Amazon</div>
          <div class="canal-stat-value" style="color:{GREEN if neto_amazon >= 0 else RED};">${neto_amazon:,.2f}</div>
        </div>
        <div class="canal-stat">
          <div class="canal-stat-label">Rentabilidad</div>
          <div class="canal-stat-value" style="color:{rent_color};">{rentabilidad_amazon:.1f}%</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

with c2:
    rent_color_d = GREEN if rentabilidad_directo >= 0 else RED
    st.markdown(f"""
    <div class="canal-card" style="border-top: 3px solid {CH_DIRECTO};">
      <div class="canal-name">🟡 Canal Directo</div>
      <div class="canal-value" style="color:{CH_DIRECTO};">${directo_ing:,.2f}</div>
      <div class="kpi-sub" style="color:{TEXT_MUTED};">Ingresos brutos · {unidades_directo} unidades</div>
      <hr class="divider">
      <div class="canal-row">
        <div>
          <div class="canal-stat-label">Gastos directos</div>
          <div class="canal-stat-value" style="color:{RED};">${gastos_no_amazon:,.2f}</div>
        </div>
        <div class="canal-stat">
          <div class="canal-stat-label">Neto Directo</div>
          <div class="canal-stat-value" style="color:{GREEN if neto_directo >= 0 else RED};">${neto_directo:,.2f}</div>
        </div>
        <div class="canal-stat">
          <div class="canal-stat-label">Rentabilidad</div>
          <div class="canal-stat-value" style="color:{rent_color_d};">{rentabilidad_directo:.1f}%</div>
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
          <span style="font-weight:600;color:{'#4ade80' if rentabilidad_amazon>=0 else '#f87171'};">{rentabilidad_amazon:.1f}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;">
          <span style="color:{TEXT_MUTED};font-size:0.8rem;">Rent. Directo</span>
          <span style="font-weight:600;color:{'#4ade80' if rentabilidad_directo>=0 else '#f87171'};">{rentabilidad_directo:.1f}%</span>
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
        st.dataframe(
            pdf,
            use_container_width=True,
            hide_index=True,
            column_config={"Monto Total (USD)": st.column_config.TextColumn("Monto (USD)")}
        )
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
        st.dataframe(
            cdf,
            use_container_width=True,
            hide_index=True,
            column_config={"Total (USD)": st.column_config.TextColumn("Total (USD)")}
        )
        st.markdown(f"<p style='color:{RED};font-weight:600;margin-top:8px;'>Total por cobrar: ${ingresos_por_cobrar:,.2f}</p>", unsafe_allow_html=True)
    else:
        st.markdown(f"<p style='color:{GREEN};'>✓ Sin cuentas por cobrar para este período.</p>", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ── Tabla de márgenes ─────────────────────────────────────────────
st.markdown('<p class="section-label">Análisis de márgenes</p>', unsafe_allow_html=True)
st.markdown('<div class="chart-card">', unsafe_allow_html=True)
if not df_margenes.empty:
    st.dataframe(df_margenes, use_container_width=True, hide_index=True)
st.markdown('</div>', unsafe_allow_html=True)
