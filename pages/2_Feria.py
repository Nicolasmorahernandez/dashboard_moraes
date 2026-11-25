"""Feria: vista de venta para celular.

Muestra solo lo que se llevó a la feria (inventario propio), con precio y
stock, sin costos ni márgenes. La vendedora aplica un descuento dentro del tope
y del margen mínimo que define el dueño, y registra cada venta con "Vendí".
Todo queda en la hoja MORAES_precios_ok (pestañas Feria y Ventas feria).
"""
import base64
import html
import math
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from gspread.utils import ValueRenderOption

import feria as F
import precios as P
from auth import autenticar
from constants import SHEET_PRECIOS_ID as _PRECIOS_DEFAULT

st.set_page_config(page_title="MORAES · Feria", page_icon="🛍️", layout="centered",
                   initial_sidebar_state="collapsed")

SHEET_ID = st.secrets.get('sheet_precios_id') or _PRECIOS_DEFAULT
ZONA = ZoneInfo(st.secrets.get('zona_horaria', 'America/Bogota'))
CLAVE_FERIA = st.secrets.get('clave_feria')
CLAVE_ADMIN = st.secrets.get('clave_precios')

# Paleta propia de la feria: cálida y clara, distinta del dashboard
BG, CARD, LINE = '#f6eee3', '#fffaf3', '#e6d6c2'
INK, MUTED, FAINT = '#3a2618', '#8a6a52', '#b39a84'
ACENTO, MIEL, VERDE, ROJO = '#b4532a', '#c98a3a', '#5f7a35', '#b0442f'

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=DM+Sans:wght@400;500;600&display=swap');
.stApp {{ background:{BG}; color:{INK}; font-family:'DM Sans',sans-serif; }}
[data-testid="stHeader"] {{ background:transparent; }}
[data-testid="stHeader"] * {{ color:{MUTED} !important; }}
[data-testid="stSidebarNav"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"], [data-testid="stSidebar"] {{ display:none; }}
.block-container {{ max-width:920px; padding-top:1.2rem; padding-bottom:4rem; }}
[data-testid="stWidgetLabel"] p {{ color:{INK} !important; font-weight:500; }}
.eyebrow {{ font-size:.7rem; letter-spacing:.2em; text-transform:uppercase; color:{ACENTO}; margin:0; font-weight:600; }}
.titulo {{ font-family:'Fraunces',serif; font-size:2.4rem; font-weight:600; line-height:1.05; color:{INK}; margin:.15rem 0 .3rem; }}
.resumen {{ display:flex; gap:.6rem; margin:.4rem 0 1.1rem; flex-wrap:wrap; }}
.resumen span {{ background:{CARD}; border:1px solid {LINE}; border-radius:999px; padding:.3rem .8rem; font-size:.85rem; color:{MUTED}; }}
.resumen b {{ color:{INK}; }}
[data-testid="stVerticalBlock"] {{ border-color:{LINE} !important; }}
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] {{ background:{CARD}; border-radius:18px;
    box-shadow:0 2px 10px rgba(120,80,40,.06); }}
.ph {{ background:#f6f1eb; border-radius:12px; overflow:hidden; display:flex; justify-content:center; margin-bottom:.6rem; }}
.ph img {{ width:100%; height:230px; object-fit:contain; }}
.ph.grande img {{ height:360px; }}
.ph.vacia {{ height:230px; align-items:center; font-family:'Fraunces',serif; font-size:3rem; color:{FAINT}; }}
.pn {{ font-family:'Fraunces',serif; font-size:1.35rem; line-height:1.15; color:{INK}; margin:0; }}
.pm {{ font-size:.85rem; color:{MUTED}; margin:.25rem 0 .1rem; }}
.pm b {{ color:{INK}; font-size:1rem; }}
.precio {{ font-family:'Fraunces',serif; font-size:3.2rem; font-weight:600; color:{INK}; line-height:1; margin:.2rem 0; }}
.tachado {{ font-family:'DM Sans',sans-serif; font-size:1.1rem; color:{FAINT}; text-decoration:line-through; margin-left:.6rem; font-weight:400; }}
.ahorro {{ display:inline-block; background:#f4e2d4; color:{ACENTO}; border-radius:999px; padding:.15rem .6rem; font-size:.8rem; font-weight:600; margin-left:.5rem; vertical-align:middle; }}
.nota {{ font-size:.8rem; color:{MUTED}; margin:.3rem 0; }}
.aviso {{ font-size:.9rem; color:{INK}; background:#f8e7cf; border:1px solid #ecd0a6; border-radius:12px; padding:.7rem .9rem; margin:.4rem 0 .8rem; }}
.ok {{ font-size:.95rem; color:#2f4417; background:#e5ecd2; border:1px solid #cfdcae; border-radius:12px; padding:.7rem .9rem; margin:.2rem 0 1rem; }}
.stock-ok {{ color:{VERDE} !important; font-weight:600; }} .stock-bajo {{ color:{MIEL} !important; font-weight:600; }} .stock-no {{ color:{ROJO} !important; font-weight:600; }}
/* Botones */
.stButton > button, .stFormSubmitButton > button {{ min-height:3rem; border-radius:12px; font-size:1rem; }}
button[kind="primary"], button[kind="primaryFormSubmit"] {{ background:{ACENTO} !important; border-color:{ACENTO} !important; color:#fff !important; font-weight:600; }}
button[kind="primary"] *, button[kind="primaryFormSubmit"] * {{ color:#fff !important; }}
button[kind="primary"]:disabled {{ opacity:.35; }}
button[kind="secondary"] {{ background:{CARD} !important; border:1px solid {LINE} !important; color:{INK} !important; }}
button[kind="secondary"]:hover {{ border-color:{ACENTO} !important; color:{ACENTO} !important; }}
/* Cuero / pago (segmentados) */
[data-testid="stButtonGroup"] button {{ background:{CARD} !important; color:{INK} !important; border-color:{LINE} !important; min-height:2.8rem; }}
[data-testid="stButtonGroup"] button * {{ color:{INK} !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background:{ACENTO} !important; border-color:{ACENTO} !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] * {{ color:#fff !important; }}
/* Campos */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="input"] input, [data-testid="stNumberInputContainer"] {{
    background:{CARD} !important; color:{INK} !important; border-color:{LINE} !important; }}
[data-testid="stTextInputRootElement"] {{ background:{CARD} !important; border-color:{LINE} !important; }}
.stApp input {{ background:transparent !important; color:{INK} !important; -webkit-text-fill-color:{INK} !important;
    font-size:1.05rem; opacity:1 !important; }}
.stApp input::placeholder {{ color:{FAINT} !important; -webkit-text-fill-color:{FAINT} !important; }}
[data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] {{ background:{CARD} !important; color:{INK} !important; }}
[data-testid="stNumberInputStepDown"] svg, [data-testid="stNumberInputStepUp"] svg {{ fill:{INK} !important; }}
[data-testid="stSliderThumbValue"] {{ color:{ACENTO} !important; font-weight:600; }}
[data-testid="stSliderTickBar"] * {{ color:{MUTED} !important; }}
/* Expanders y formularios */
[data-testid="stExpander"] details {{ background:{CARD}; border:1px solid {LINE} !important; border-radius:14px; }}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * {{ color:{INK} !important; }}
[data-testid="stExpander"] svg {{ fill:{MUTED}; }}
[data-testid="stForm"] {{ background:{CARD}; border:1px solid {LINE}; border-radius:18px; }}
.vt {{ display:flex; justify-content:space-between; gap:.6rem; font-size:.88rem; padding:.5rem 0; border-bottom:1px dashed {LINE}; }}
.vt.anulada {{ color:{FAINT}; text-decoration:line-through; }}
</style>
""", unsafe_allow_html=True)


# ── Acceso ────────────────────────────────────────────────────────
if CLAVE_FERIA and not st.session_state.get('feria_ok'):
    st.markdown("<p class='eyebrow'>MORAES</p><div class='titulo'>Feria</div>", unsafe_allow_html=True)
    with st.form('login'):
        nombre = st.text_input("Tu nombre", value='Valentina')
        clave = st.text_input("Clave", type='password')
        if st.form_submit_button("Entrar", type='primary', width='stretch'):
            if clave == CLAVE_FERIA or (CLAVE_ADMIN and clave == CLAVE_ADMIN):
                st.session_state['feria_ok'] = True
                st.session_state['vendedora'] = nombre.strip() or 'Vendedora'
                st.session_state['admin'] = bool(CLAVE_ADMIN and clave == CLAVE_ADMIN)
                st.rerun()
            st.error("Clave incorrecta.")
    st.stop()
if not CLAVE_FERIA:
    st.session_state.setdefault('vendedora', 'Vendedora')
    st.session_state.setdefault('admin', True)   # sin clave configurada (local): todo visible


# ── Datos ─────────────────────────────────────────────────────────

def _libro():
    return autenticar().open_by_key(SHEET_ID)


def _tab(sh, nombre, crear_con=None):
    try:
        return sh.worksheet(nombre)
    except WorksheetNotFound:
        if crear_con is None:
            return None
        ws = sh.add_worksheet(nombre, rows=1000, cols=len(crear_con))
        ws.update([crear_con], 'A1', value_input_option='RAW')
        return ws


@st.cache_data(ttl=600, show_spinner=False)
def cargar_precios(_sid):
    """Precio retail y costo variable por producto/cuero (el costo no se muestra)."""
    ws = _libro().worksheet(P.HOJA)
    rango = f"A1:X{ws.row_count}"
    valores = ws.get(rango, value_render_option=ValueRenderOption.unformatted)
    formulas = ws.get(rango, value_render_option=ValueRenderOption.formula)
    params, prod = P.parsear(list(valores), list(formulas))
    df = P.calcular(params, prod)
    return {(r['Producto'], r['Cuero']): (float(r['Precio retail']), float(r['Costo variable']))
            for _, r in df.iterrows() if not math.isnan(r['Precio retail'])}


def cargar_feria():
    sh = _libro()
    ws_f = _tab(sh, F.HOJA_FERIA)
    grid_f = ws_f.get_all_values(value_render_option=ValueRenderOption.unformatted) if ws_f else []
    ws_v = _tab(sh, F.HOJA_VENTAS)
    grid_v = ws_v.get_all_values(value_render_option=ValueRenderOption.unformatted) if ws_v else []
    cfg, stock = F.parsear_feria(grid_f)
    st.session_state['cfg'] = cfg
    st.session_state['stock'] = stock
    st.session_state['hay_feria'] = ws_f is not None
    st.session_state['ventas'] = F.parsear_ventas(grid_v)


try:
    precios = cargar_precios(SHEET_ID)
    if 'cfg' not in st.session_state:
        cargar_feria()
except (APIError, SpreadsheetNotFound, PermissionError) as e:
    st.error(f"No pude abrir la hoja. Avísale a Nicolás.\n\n`{e}`")
    st.stop()

cfg, stock = st.session_state['cfg'], st.session_state['stock']
ventas = st.session_state['ventas']
vend = F.vendidos(ventas, cfg['feria'])


def disponible(prod, cuero):
    return stock.get((prod, cuero), 0) - vend.get((prod, cuero), 0)


def money(x):
    return '—' if x is None or (isinstance(x, float) and math.isnan(x)) else f"${x:,.0f}"


ahora = datetime.now(ZONA)
hoy = ahora.strftime('%Y-%m-%d')
de_hoy = [r for r in ventas if str(r.get('Feria', '')).strip() == cfg['feria']
          and str(r.get('Fecha', '')).strip() == hoy and str(r.get('Estado', '')).lower() != 'anulada']


# ── Encabezado ────────────────────────────────────────────────────
st.markdown(f"<p class='eyebrow'>MORAES · {html.escape(st.session_state['vendedora'])}</p>"
            f"<div class='titulo'>{html.escape(cfg['feria'])}</div>"
            f"<div class='resumen'><span>Hoy <b>{sum(r['Cantidad'] for r in de_hoy)}</b> und</span>"
            f"<span>Vendido <b>{money(sum(r['Total'] for r in de_hoy))}</b></span></div>",
            unsafe_allow_html=True)

if st.session_state.pop('vendido_ok', None):
    st.markdown(f"<div class='ok'>✓ {html.escape(st.session_state.pop('vendido_txt', 'Venta registrada'))}</div>",
                unsafe_allow_html=True)


CARPETA_FOTOS = Path(__file__).resolve().parent.parent / 'fotos'


@st.cache_data(show_spinner=False)
def _foto_uri(nombre_archivo):
    ruta = CARPETA_FOTOS / nombre_archivo
    if not ruta.exists():
        return None
    return 'data:image/webp;base64,' + base64.b64encode(ruta.read_bytes()).decode()


def foto_html(prod, grande=False):
    uri = _foto_uri(F.FOTOS[prod]) if prod in F.FOTOS else None
    if not uri:
        return f"<div class='ph vacia'>{html.escape(prod[:1])}</div>"
    return f"<div class='ph{' grande' if grande else ''}'><img src='{uri}' alt='{html.escape(prod)}'></div>"


def _ir(prod):
    st.session_state['f_prod'] = prod
    for k in [k for k in st.session_state if k.startswith('f_w_')]:
        del st.session_state[k]


sel = st.session_state.get('f_prod')
en_feria = sorted({p for (p, c), q in stock.items() if q > 0 and (p, c) in precios})

# ── Catálogo ──────────────────────────────────────────────────────
if not sel:
    if not en_feria:
        st.markdown("<div class='aviso'>Todavía no hay inventario cargado para esta feria. "
                    "Nicolás lo carga en <b>Preparar feria</b>, abajo.</div>", unsafe_allow_html=True)
    buscar = st.text_input("Buscar", placeholder="Buscar producto…", label_visibility='collapsed') if en_feria else ''
    visibles = [p for p in en_feria if not buscar or buscar.lower() in p.lower()]
    cols = st.columns(2, gap='medium')
    for i, prod in enumerate(visibles):
        cueros = [c for (p, c), q in stock.items() if p == prod and q > 0 and (p, c) in precios]
        ps = [precios[(prod, c)][0] for c in cueros]
        disp = sum(max(disponible(prod, c), 0) for c in cueros)
        rango = money(min(ps)) if min(ps) == max(ps) else f"{money(min(ps))} – {money(max(ps))}"
        clase = 'stock-no' if disp <= 0 else 'stock-bajo' if disp <= 2 else 'stock-ok'
        txt_disp = 'Agotado' if disp <= 0 else f"{disp} disponible{'s' if disp != 1 else ''}"
        with cols[i % 2].container(border=True):
            st.markdown(f"{foto_html(prod)}<p class='pn'>{html.escape(prod)}</p>"
                        f"<p class='pm'><b>{rango}</b> · <span class='{clase}'>{txt_disp}</span></p>"
                        f"<p class='pm'>{' · '.join(map(html.escape, cueros))}</p>", unsafe_allow_html=True)
            st.button("Vender", key=f"v_{prod}", on_click=_ir, args=(prod,), width='stretch',
                      disabled=disp <= 0, type='primary')

# ── Ficha de venta ────────────────────────────────────────────────
else:
    st.button("← Productos", on_click=_ir, args=(None,))
    cueros = [c for (p, c), q in stock.items() if p == sel and q > 0 and (p, c) in precios]
    izq, der = st.columns([1, 1.15], gap='large')
    izq.markdown(foto_html(sel, grande=True), unsafe_allow_html=True)
    with der:
        st.markdown(f"<p class='pn' style='font-size:2rem'>{html.escape(sel)}</p>", unsafe_allow_html=True)
        etiqueta = {c: f"{c} ({max(disponible(sel, c), 0)})" for c in cueros}
        cuero = st.segmented_control("Cuero", cueros, format_func=etiqueta.get, default=cueros[0] if cueros else None,
                                     key=f'f_w_cuero') or (cueros[0] if cueros else None)
        if not cuero:
            st.stop()
        precio, costo = precios[(sel, cuero)]
        disp = disponible(sel, cuero)
        tope = F.descuento_tope(precio, costo, cfg['desc_max'], cfg['margen_min'])
        if tope > 0:
            desc = st.slider(f"Descuento (hasta {tope}%)", 0, tope, 0, step=1, format='%d%%', key='f_w_desc')
        else:
            desc = 0
            st.markdown("<div class='nota'>Este producto no tiene descuento.</div>", unsafe_allow_html=True)
        final = F.precio_final(precio, desc)
        st.markdown(f"<div class='precio'>{money(final)}"
                    f"{f'<span class=tachado>{money(precio)}</span><span class=ahorro>−{desc}%</span>' if desc else ''}</div>",
                    unsafe_allow_html=True)
        clase = 'stock-no' if disp <= 0 else 'stock-bajo' if disp <= 2 else 'stock-ok'
        st.markdown(f"<p class='pm'><span class='{clase}'>{max(disp, 0)} disponible{'' if disp == 1 else 's'}</span> en {html.escape(cuero)}</p>",
                    unsafe_allow_html=True)
        cant = st.number_input("Cantidad", min_value=1, max_value=max(disp, 1), value=1, step=1, key='f_w_cant')
        pago = st.segmented_control("Pago", F.PAGOS, default=F.PAGOS[0], key='f_w_pago') or F.PAGOS[0]
        cliente = st.text_input("Cliente (opcional)", placeholder="Nombre, correo o Instagram", key='f_w_cliente')
        if cant > 1:
            st.markdown(f"<div class='nota'>Total: <b>{money(final * cant)}</b></div>", unsafe_allow_html=True)
        if st.button(f"Vendí · {money(final * cant)}", type='primary', width='stretch', disabled=disp < cant):
            try:
                sh = _libro()
                ws_v = _tab(sh, F.HOJA_VENTAS, crear_con=F.CAB_VENTAS)
                ahora = datetime.now(ZONA)
                fila = F.fila_venta(ahora.strftime('%Y-%m-%d'), ahora.strftime('%H:%M'), cfg['feria'], sel, cuero,
                                    cant, precio, desc, final, pago, cliente.strip(), st.session_state['vendedora'])
                resp = ws_v.append_row(fila, value_input_option='RAW', table_range='A1')
                m = re.search(r'![A-Z]+(\d+)', (resp or {}).get('updates', {}).get('updatedRange', ''))
                st.session_state['ultima_venta'] = int(m.group(1)) if m else None
                cargar_feria()
                _ir(None)
                st.session_state['vendido_ok'] = True
                st.session_state['vendido_txt'] = f"Vendido: {sel} {cuero} × {cant} · {money(final * cant)}"
                st.rerun()
            except APIError as e:
                st.error(f"No se guardó la venta. Revisa la conexión e intenta de nuevo.\n\n`{e}`")


# ── Ventas de hoy ─────────────────────────────────────────────────
st.markdown("")
with st.expander(f"Ventas de hoy ({len(de_hoy)})"):
    hoy_todas = [r for r in ventas if str(r.get('Feria', '')).strip() == cfg['feria']
                 and str(r.get('Fecha', '')).strip() == hoy]
    if not hoy_todas:
        st.markdown("<div class='nota'>Aún no hay ventas hoy.</div>", unsafe_allow_html=True)
    for r in reversed(hoy_todas):
        anul = str(r.get('Estado', '')).lower() == 'anulada'
        st.markdown(f"<div class='vt{' anulada' if anul else ''}'><span>{html.escape(str(r.get('Hora', '')))} · "
                    f"{html.escape(str(r['Producto']))} {html.escape(str(r['Cuero']))} × {r['Cantidad']} · "
                    f"{html.escape(str(r.get('Pago', '')))}</span><span>{money(r['Total'])}</span></div>",
                    unsafe_allow_html=True)
    por_pago = {}
    for r in de_hoy:
        por_pago[r.get('Pago', '')] = por_pago.get(r.get('Pago', ''), 0) + r['Total']
    if por_pago:
        st.markdown("<div class='nota'>" + ' · '.join(f"{html.escape(str(k))} {money(v)}" for k, v in por_pago.items())
                    + "</div>", unsafe_allow_html=True)
    ultima = st.session_state.get('ultima_venta')
    if ultima and any(r['_fila'] == ultima and str(r.get('Estado', '')).lower() != 'anulada' for r in ventas):
        if st.button("Anular mi última venta", width='stretch'):
            try:
                ws_v = _libro().worksheet(F.HOJA_VENTAS)
                ws_v.update_cell(ultima, F.CAB_VENTAS.index('Estado') + 1, 'anulada')
                st.session_state['ultima_venta'] = None
                cargar_feria()
                st.rerun()
            except APIError as e:
                st.error(f"No pude anular: `{e}`")
    if st.button("Actualizar", width='stretch', help="Vuelve a leer ventas e inventario (si otra persona vendió)"):
        cargar_feria()
        st.rerun()


# ── Preparar feria (solo Nicolás) ─────────────────────────────────
with st.expander("Preparar feria (Nicolás)"):
    if CLAVE_ADMIN and not st.session_state.get('admin'):
        if st.text_input("Clave de administrador", type='password', key='adm_clave') == CLAVE_ADMIN:
            st.session_state['admin'] = True
            st.rerun()
        st.stop()
    st.markdown("<div class='nota'>Inventario propio de la feria: lo que llevas, no la bodega. Las ventas "
                "lo van descontando.</div>", unsafe_allow_html=True)
    nombre_f = st.text_input("Nombre de la feria", value=cfg['feria'], key='adm_nombre')
    a, b = st.columns(2)
    dmax = a.number_input("Descuento máximo %", 0, 90, int(round(cfg['desc_max'] * 100)), step=1, key='adm_dmax')
    mmin = b.number_input("Margen mínimo %", 0, 95, int(round(cfg['margen_min'] * 100)), step=1, key='adm_mmin',
                          help="El descuento nunca deja la venta por debajo de este margen")
    st.markdown("<div class='nota'>Unidades que llevas de cada producto y cuero:</div>", unsafe_allow_html=True)
    nuevo_stock = {}
    productos = list(dict.fromkeys(p for p, _ in precios))
    for prod in productos:
        cueros_p = [c for p, c in precios if p == prod]
        total = sum(stock.get((prod, c), 0) for c in cueros_p)
        st.markdown(f"<p class='pm' style='margin-top:.8rem'><b>{html.escape(prod)}</b>"
                    f"{f' · {total} und' if total else ''}</p>", unsafe_allow_html=True)
        cols = st.columns(4)
        for col, c in zip(cols, cueros_p):
            q = col.number_input(c, min_value=0, value=int(stock.get((prod, c), 0)), step=1,
                                 key=f'adm_q_{prod}_{c}')
            if q:
                nuevo_stock[(prod, c)] = int(q)
    if nombre_f.strip() != cfg['feria'] and any(str(r.get('Feria', '')).strip() == cfg['feria'] for r in ventas):
        st.markdown("<div class='aviso'>Al cambiar el nombre empiezas una feria nueva: el conteo de vendidos "
                    "arranca de cero con el inventario de arriba.</div>", unsafe_allow_html=True)
    if st.button("Guardar feria", type='primary', width='stretch'):
        nuevo_cfg = {'feria': nombre_f.strip() or 'Feria', 'desc_max': dmax / 100, 'margen_min': mmin / 100}
        try:
            sh = _libro()
            ws_f = _tab(sh, F.HOJA_FERIA, crear_con=['Feria', nuevo_cfg['feria']])
            ws_f.clear()
            ws_f.update(F.grid_feria(nuevo_cfg, nuevo_stock), 'A1', value_input_option='RAW')
            _tab(sh, F.HOJA_VENTAS, crear_con=F.CAB_VENTAS)
            cargar_feria()
            st.rerun()
        except APIError as e:
            st.error(f"No pude guardar: `{e}`")
