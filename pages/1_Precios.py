"""Precios por producto.

Vista 1: catálogo de productos (tarjetas).
Vista 2: ficha de un producto: editar costo/precio por cuero, desglose del
costo y precios por volumen. Guarda en la hoja MORAES_precios_ok.

Solo escribe celdas de entrada (nunca fórmulas). Los cálculos los hace el Sheet;
aquí se replican para la vista previa (ver precios.py).
"""
import html
import math

import pandas as pd
import streamlit as st
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from gspread.utils import ValueRenderOption

import precios as P
from auth import autenticar
from constants import SHEET_PRECIOS_ID as _PRECIOS_DEFAULT

st.set_page_config(page_title="MORAES · Precios", page_icon="💲", layout="wide",
                   initial_sidebar_state="collapsed")

SHEET_PRECIOS_ID = st.secrets.get('sheet_precios_id') or _PRECIOS_DEFAULT
URL_SHEET = f"https://docs.google.com/spreadsheets/d/{SHEET_PRECIOS_ID}/edit"

# Paleta
BG, CARD, LINE = '#14100e', '#1d1714', '#30251f'
INK, MUTED, FAINT = '#f3ebe4', '#a38d7e', '#6f5d52'
COGNAC, GOLD, GREEN, RED = '#c27c4a', '#d9a441', '#86c58a', '#e07a6e'
SEG = {  # colores del desglose de costo
    'Proveedor': '#7a4a2e', 'Ajuste cambiario': '#a0643d', 'Empaque': '#c49a6c',
    'Flete': '#8c7a6b', 'Arancel': '#5e5048', 'Ganancia': '#86c58a',
}
MARGEN_BAJO, MARGEN_OK = 0.20, 0.35   # supuesto: rojo < 20%, dorado < 35%

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Inter:wght@400;500;600&display=swap');
.stApp {{ background:{BG}; color:{INK}; font-family:'Inter',sans-serif; }}
[data-testid="stHeader"] {{ background:transparent; }}
.block-container {{ max-width:1100px; padding-top:2.2rem; }}
h1,h2,h3 {{ font-family:'Cormorant Garamond',serif !important; font-weight:600 !important; color:{INK} !important; letter-spacing:.01em; }}
.eyebrow {{ font-size:.68rem; letter-spacing:.18em; text-transform:uppercase; color:{MUTED}; margin:0 0 .2rem; }}
.titulo {{ font-family:'Cormorant Garamond',serif; font-size:2.8rem; font-weight:600; line-height:1.05; margin:0; color:{INK}; }}
.sub {{ color:{MUTED}; font-size:.86rem; margin:.35rem 0 0; }}
.sub a {{ color:{COGNAC}; text-decoration:none; }}
.rule {{ border:none; border-top:1px solid {LINE}; margin:1.4rem 0 1.6rem; }}

/* Tarjetas de catálogo */
[data-testid="stVerticalBlockBorderWrapper"] {{ background:{CARD}; border-color:{LINE} !important; border-radius:14px; }}
.pc-name {{ font-family:'Cormorant Garamond',serif; font-size:1.5rem; line-height:1.15; color:{INK}; margin:0 0 .7rem; }}
.pc-row {{ display:flex; justify-content:space-between; align-items:baseline; font-size:.8rem; color:{MUTED}; margin:.15rem 0; }}
.pc-row b {{ color:{INK}; font-weight:600; font-size:.95rem; }}

/* Botones */
button[data-testid^="stBaseButton-secondary"], .stPopover button {{ background:transparent; border:1px solid {LINE}; color:{INK}; border-radius:999px; font-size:.82rem; }}
button[data-testid^="stBaseButton-secondary"]:hover, .stPopover button:hover {{ border-color:{COGNAC}; color:{COGNAC}; }}
.stButton > button[kind="primary"] {{ background:{COGNAC}; border-color:{COGNAC}; color:#1a0f09; font-weight:600; }}
.stButton > button[kind="primary"]:hover {{ background:{GOLD}; border-color:{GOLD}; color:#1a0f09; }}

/* Inputs */
[data-testid="stNumberInput"] input {{ background:{BG}; color:{INK}; font-size:1.05rem; }}
[data-testid="stNumberInput"] label p {{ color:{MUTED}; font-size:.78rem; letter-spacing:.04em; }}

/* Ficha */
.panel {{ background:{CARD}; border:1px solid {LINE}; border-radius:14px; padding:1.3rem 1.4rem; }}
.panel-t {{ font-size:.68rem; letter-spacing:.16em; text-transform:uppercase; color:{MUTED}; margin:0 0 1rem; }}
.big {{ display:flex; gap:2.2rem; margin-bottom:1.2rem; }}
.big div span {{ display:block; font-size:.7rem; letter-spacing:.12em; text-transform:uppercase; color:{MUTED}; }}
.big div b {{ font-family:'Cormorant Garamond',serif; font-size:2.3rem; font-weight:600; color:{INK}; line-height:1.1; }}
.bar {{ display:flex; height:14px; border-radius:7px; overflow:hidden; margin:.2rem 0 1.1rem; }}
.ln {{ display:flex; justify-content:space-between; padding:.45rem 0; border-bottom:1px solid {LINE}; font-size:.88rem; color:{INK}; }}
.ln:last-child {{ border-bottom:none; }}
.ln i {{ display:inline-block; width:9px; height:9px; border-radius:2px; margin-right:.55rem; }}
.ln small {{ color:{FAINT}; margin-left:.4rem; }}
.ln.total {{ font-weight:600; border-top:1px solid {MUTED}; border-bottom:none; margin-top:.2rem; }}
.tiers {{ display:grid; grid-template-columns:repeat(4,1fr); gap:.7rem; }}
.tier {{ background:{BG}; border:1px solid {LINE}; border-radius:12px; padding:.85rem .95rem; }}
.tier span {{ font-size:.68rem; letter-spacing:.1em; text-transform:uppercase; color:{MUTED}; }}
.tier b {{ display:block; font-family:'Cormorant Garamond',serif; font-size:1.7rem; font-weight:600; color:{INK}; margin:.15rem 0; }}
.tier em {{ font-style:normal; font-size:.8rem; }}
.corp {{ display:flex; flex-wrap:wrap; gap:1.4rem; font-size:.84rem; color:{MUTED}; margin-top:.9rem; }}
.corp b {{ color:{INK}; font-weight:600; }}
.nota {{ font-size:.76rem; color:{FAINT}; margin-top:.5rem; }}
.pend {{ font-size:.82rem; color:{GOLD}; }}
.ln.sub {{ padding:.25rem 0 .25rem 1.35rem; font-size:.8rem; color:{MUTED}; border-bottom:1px dashed {LINE}; }}
.emp-t {{ font-size:.78rem; letter-spacing:.04em; color:{MUTED}; margin:.9rem 0 .35rem; }}
@media (max-width: 760px) {{
  .tiers {{ grid-template-columns:repeat(2,1fr); }}
  .titulo {{ font-size:2rem; }}
  .big {{ gap:1.2rem; }}
}}
</style>
""", unsafe_allow_html=True)


# ── Datos ─────────────────────────────────────────────────────────

def _libro():
    gc = autenticar()
    return gc, gc.open_by_key(SHEET_PRECIOS_ID)


def _hoja():
    gc, sh = _libro()
    return gc, sh.worksheet(P.HOJA)


def _leer_empaque(sh):
    """Grid de la pestaña Empaque, o None si no existe todavía."""
    try:
        ws = sh.worksheet(P.HOJA_EMPAQUE)
    except WorksheetNotFound:
        return None
    return [list(f) for f in ws.get_all_values(value_render_option=ValueRenderOption.unformatted)]


def _leer_grids(ws):
    rango = f"A1:X{ws.row_count}"
    return (list(ws.get(rango, value_render_option=ValueRenderOption.unformatted)),
            list(ws.get(rango, value_render_option=ValueRenderOption.formula)))


def cargar():
    gc = None
    try:
        gc, sh = _libro()
        ws = sh.worksheet(P.HOJA)
        valores, formulas = _leer_grids(ws)
        grid_emp = _leer_empaque(sh)
    except (APIError, SpreadsheetNotFound, PermissionError) as e:
        email = None
        try:
            email = gc.http_client.auth.service_account_email
        except Exception:
            pass
        st.error("No pude abrir la hoja de precios. Compártela como *Editor* con la cuenta del dashboard"
                 f"{f' (**{email}**)' if email else ''} desde [la hoja]({URL_SHEET}) y recarga.\n\n`{e}`")
        st.stop()
    params, prod = P.parsear(valores, formulas)
    componentes = P.parsear_empaque(grid_emp or [])
    st.session_state['precios_orig'] = (params, prod)
    st.session_state['emp_raw'] = grid_emp
    st.session_state['emp_orig'] = P.estado_empaque(prod, componentes)
    st.session_state['emp_componentes'] = componentes
    st.session_state['pend'] = {}
    st.session_state['pend_emp'] = {}


if 'precios_orig' not in st.session_state:
    with st.spinner("Leyendo hoja de precios…"):
        cargar()

params_orig, prod_orig = st.session_state['precios_orig']
pend = st.session_state.setdefault('pend', {})   # {celda: valor nuevo}


def _aplicar(params, prod):
    """Copias de los originales con los cambios pendientes aplicados."""
    params, prod = params.copy(), prod.copy()
    for celda, v in pend.items():
        if celda in set(params['Celda']):
            params.loc[params['Celda'] == celda, 'Valor'] = v
        else:
            fila, col = P.celda_a_rc(celda)
            prod.loc[prod['Fila'] == fila, P.ENTRADAS[P.LETRAS[col]]] = v
    return params, prod


emp_orig = st.session_state['emp_orig']
pend_emp = st.session_state.setdefault('pend_emp', {})   # {producto: estado de empaque nuevo}
EDITABLE_EMP = ('default', 'manual', 'componentes')


def emp_actual(prod):
    return pend_emp.get(prod, emp_orig[prod])


params_nuevo, prod_nuevo = _aplicar(params_orig, prod_orig)
_b7 = params_nuevo.loc[params_nuevo['Celda'] == 'B7', 'Valor'].iloc[0]
for _prod, _est in emp_orig.items():
    _est = emp_actual(_prod)
    if _est['modo'] in EDITABLE_EMP:
        _m = prod_nuevo['Producto'] == _prod
        prod_nuevo.loc[_m, 'Empaque'] = P.empaque_efectivo(_est, _b7)
        prod_nuevo.loc[_m, '_f_E'] = ''
df = P.calcular(params_nuevo, prod_nuevo)
p = dict(zip(params_nuevo['Celda'], params_nuevo['Valor']))
# El empaque de productos va por su propio camino (modos); se excluye del diff genérico
cambios = [c for c in P.cambios_pendientes(params_orig, params_nuevo, prod_orig, prod_nuevo)
           if not (c['celda'][0] == 'E' and int(c['celda'][1:]) >= P.FILA_INICIO)]
NOMBRE_MODO = {'default': 'predeterminado', 'manual': 'total manual', 'componentes': 'por componentes'}


def _emp_igual(a, b):
    if a['modo'] != b['modo']:
        return False
    if a['modo'] == 'manual':
        return not P._distinto(a['total'], b['total'])
    if a['modo'] == 'componentes':
        return [(c, round(v, 6)) for c, v in a['items']] == [(c, round(v, 6)) for c, v in b['items']]
    return True


for _prod in list(pend_emp):
    if _emp_igual(pend_emp[_prod], emp_orig[_prod]):
        del pend_emp[_prod]
for _prod, _est in pend_emp.items():
    cambios.append({'celda': 'E', 'que': f"{_prod} · Empaque",
                    'antes': P.empaque_efectivo(emp_orig[_prod], p['B7']),
                    'despues': P.empaque_efectivo(_est, p['B7']),
                    'bloqueada': False, 'empaque': _prod,
                    'nota': NOMBRE_MODO[_est['modo']]})


# ── Helpers de formato ────────────────────────────────────────────

def _nan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def money(x, dec=0):
    return '—' if _nan(x) else f"{'-' if x < 0 else ''}${abs(x):,.{dec}f}"


def pct(x):
    return '—' if _nan(x) else f"{x:.0%}"


def color_m(m):
    if _nan(m):
        return MUTED
    return RED if m < MARGEN_BAJO else GOLD if m < MARGEN_OK else GREEN


def _valor_orig(celda):
    fila, col = P.celda_a_rc(celda)
    if celda in set(params_orig['Celda']):
        return params_orig.loc[params_orig['Celda'] == celda, 'Valor'].iloc[0]
    return prod_orig.loc[prod_orig['Fila'] == fila, P.ENTRADAS[P.LETRAS[col]]].iloc[0]


def _on_change(celda):
    v = st.session_state[f'in_{celda}']
    if not P._distinto(v, _valor_orig(celda)):
        pend.pop(celda, None)
    else:
        pend[celda] = v


def entrada(celda, label, valor, bloqueada=False, fmt='%.2f', step=0.5, min_value=0.0, ayuda=None):
    st.session_state.setdefault(f'in_{celda}', None if _nan(valor) else float(valor))
    st.number_input(label, key=f'in_{celda}', format=fmt, step=step, min_value=min_value,
                    disabled=bloqueada, on_change=_on_change, args=(celda,),
                    help=ayuda or (f"Celda {celda}" + (" · tiene fórmula en el Sheet, se cambia allá" if bloqueada else "")))


def ir(producto):
    st.session_state['producto'] = producto
    for k in [k for k in st.session_state if k.startswith('emp_')
              and k not in ('emp_orig', 'emp_raw', 'emp_componentes')]:
        del st.session_state[k]
    st.session_state['visita'] = st.session_state.get('visita', 0) + 1


def bloque_empaque(prod):
    """Editor de empaque del producto (aplica a todos sus cueros)."""
    est = emp_actual(prod)
    st.markdown("<div class='emp-t'>Empaque por unidad</div>", unsafe_allow_html=True)
    if est['modo'] not in EDITABLE_EMP:
        st.number_input("Empaque", value=None if _nan(est['total']) else float(est['total']),
                        disabled=True, label_visibility='collapsed', key='emp_bloq')
        st.markdown("<div class='nota'>Este producto tiene un empaque distinto por cuero o una fórmula "
                    "especial en el Sheet; cámbialo allá.</div>", unsafe_allow_html=True)
        return
    opciones = {'default': f"General ({money(p['B7'], 2)})", 'manual': 'Total', 'componentes': 'Detallado'}
    modo = st.segmented_control("Modo de empaque", list(opciones), format_func=opciones.get,
                                default=est['modo'], key=f'emp_modo_{prod}',
                                label_visibility='collapsed') or est['modo']
    nuevo = {'modo': modo, 'total': est['total'], 'items': list(est['items'])}
    if modo == 'default':
        st.markdown(f"<div class='nota'>Usa el empaque general de Ajustes: {money(p['B7'], 2)} por unidad.</div>",
                    unsafe_allow_html=True)
    elif modo == 'manual':
        base = est['total'] if est['modo'] == 'manual' else P.empaque_efectivo(est, p['B7'])
        nuevo['total'] = st.number_input("Total empaque (USD)", value=None if _nan(base) else float(base),
                                         min_value=0.0, step=0.25, format='%.2f', key=f'emp_total_{prod}')
        if nuevo['total'] is None:
            nuevo['total'] = math.nan
    else:
        clave_base = f'emp_base_{prod}'
        if clave_base not in st.session_state:
            actual = P.empaque_efectivo(est, p['B7'])
            # Si no hay detalle, arranca con el total actual "sin detallar" para no bajar el costo a $0
            items = est['items'] or ([('Sin detallar', float(actual))] if not _nan(actual) and actual > 0 else []) \
                + [(c, 0.0) for c in P.CONCEPTOS_SUGERIDOS]
            st.session_state[clave_base] = pd.DataFrame(items, columns=['Concepto', 'Valor'])
        tabla = st.data_editor(
            st.session_state[clave_base], key=f"emp_items_{prod}_{st.session_state.get('visita', 0)}",
            num_rows='dynamic', hide_index=True, width='stretch',
            column_config={'Concepto': st.column_config.TextColumn(required=True),
                           'Valor': st.column_config.NumberColumn('USD', format='$%.2f', min_value=0.0)})
        nuevo['items'] = [(str(c).strip(), float(v) if not _nan(v) else 0.0)
                          for c, v in zip(tabla['Concepto'], tabla['Valor'])
                          if c is not None and str(c).strip()]
        st.markdown(f"<div class='nota'>Total: <b>{money(sum(v for _, v in nuevo['items']), 2)}</b>. "
                    "Reparte el valor de “Sin detallar” en bolsa, logo, caja… y bórralo; "
                    "agrega otros insumos con el + de la tabla.</div>", unsafe_allow_html=True)
    st.markdown("<div class='nota'>Aplica a todos los cueros de este producto.</div>", unsafe_allow_html=True)
    if _emp_igual(nuevo, emp_orig[prod]):
        if pend_emp.pop(prod, None) is not None:
            st.rerun()
    elif prod not in pend_emp or not _emp_igual(nuevo, pend_emp[prod]):
        pend_emp[prod] = nuevo
        st.rerun()


# ── Encabezado ────────────────────────────────────────────────────
producto_sel = st.session_state.get('producto')

h1, h2 = st.columns([3, 1.3], vertical_alignment='bottom')
with h1:
    st.markdown("<p class='eyebrow'>MORAES · Precios</p>", unsafe_allow_html=True)
    if producto_sel:
        st.markdown(f"<div class='titulo'>{html.escape(producto_sel)}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='titulo'>Productos</div>"
                    f"<p class='sub'>Elige un producto para ver sus costos y cambiar su precio. "
                    f"Conectado a <a href='{URL_SHEET}' target='_blank'>MORAES_precios_ok</a>.</p>",
                    unsafe_allow_html=True)
with h2:
    b1, b2 = st.columns(2)
    with b1.popover("Ajustes", width='stretch'):
        st.markdown("**Ajustes generales**")
        st.caption("Aplican a todos los productos.")
        for _, r in params_orig.iterrows():
            es_pct = r['pct']
            entrada(r['Celda'], r['Parámetro'], r['Valor'], r['formula'],
                    fmt='%.2f' if es_pct else ('%.0f' if r['Valor'] >= 100 else '%.2f'),
                    step=0.01 if es_pct else (50.0 if r['Valor'] >= 100 else 0.5))
    if b2.button("Recargar", width='stretch', help="Descarta cambios sin guardar y vuelve a leer la hoja"):
        for k in [k for k in st.session_state if k.startswith('in_')]:
            del st.session_state[k]
        cargar()
        st.rerun()

st.markdown("<hr class='rule'>", unsafe_allow_html=True)


# ── Vista 1: catálogo ─────────────────────────────────────────────
if not producto_sel:
    productos = list(dict.fromkeys(df['Producto']))
    buscar = st.text_input("Buscar", placeholder="Buscar producto…", label_visibility='collapsed')
    if buscar:
        productos = [x for x in productos if buscar.lower() in x.lower()]
    for i, prod in enumerate(productos):
        if i % 3 == 0:
            cols = st.columns(3)
        g = df[df['Producto'] == prod]
        v = g.dropna(subset=['Precio retail', 'Costo variable'])
        if v.empty:
            precio_txt, margen_txt, mcol = 'sin precio', '—', MUTED
        else:
            lo, hi = v['Precio retail'].min(), v['Precio retail'].max()
            precio_txt = money(lo) if lo == hi else f"{money(lo)}–{money(hi)}"
            m = v['Margen retail %'].min()
            margen_txt, mcol = pct(m), color_m(m)
        with cols[i % 3].container(border=True):
            st.markdown(
                f"<div class='pc-name'>{html.escape(prod)}</div>"
                f"<div class='pc-row'>Retail <b>{precio_txt}</b></div>"
                f"<div class='pc-row'>Margen mínimo <b style='color:{mcol}'>{margen_txt}</b></div>"
                f"<div class='pc-row'>Cueros <b>{len(g)}</b></div>",
                unsafe_allow_html=True)
            st.button("Abrir", key=f"open_{i}", on_click=ir, args=(prod,), width='stretch')


# ── Vista 2: ficha de producto ────────────────────────────────────
else:
    g = df[df['Producto'] == producto_sel]
    if g.empty:
        st.session_state.pop('producto', None)
        st.rerun()

    top1, top2 = st.columns([1, 2.4], vertical_alignment='center')
    top1.button("← Todos los productos", on_click=ir, args=(None,))
    cueros = list(g['Cuero'])
    with top2:
        cuero = st.segmented_control("Cuero", cueros, default=cueros[0], key=f"cuero_{producto_sel}",
                                     label_visibility='collapsed') or cueros[0]
    r = g[g['Cuero'] == cuero].iloc[0]
    o = prod_orig[prod_orig['Fila'] == r['Fila']].iloc[0]
    fila = int(r['Fila'])

    st.markdown("")
    izq, der = st.columns([1, 1.9], gap='large')

    # Entradas editables
    with izq:
        st.markdown(f"<div class='panel-t'>Editar · {html.escape(cuero)}</div>", unsafe_allow_html=True)
        entrada(f'C{fila}', 'Costo proveedor (USD, a tasa base)', o['Costo proveedor'], bool(o['_f_C']))
        entrada(f'J{fila}', 'Precio retail (USD)', o['Precio retail'], bool(o['_f_J']), fmt='%.0f', step=1.0)
        entrada(f'F{fila}', 'Unidades por caja', o['Unid/caja'], bool(o['_f_F']), fmt='%.0f', step=1.0, min_value=1.0)
        if o['_f_J']:
            st.markdown("<div class='nota'>El precio de este cuero tiene fórmula en el Sheet; se cambia allá.</div>",
                        unsafe_allow_html=True)
        bloque_empaque(producto_sel)

    # Desglose
    with der:
        costo, precio = r['Costo variable'], r['Precio retail']
        ganancia = precio - costo if not (_nan(precio) or _nan(costo)) else math.nan
        _cab = (
            "<div class='panel'><div class='panel-t'>Rentabilidad retail</div>"
            "<div class='big'>"
            f"<div><span>Precio</span><b>{money(precio)}</b></div>"
            f"<div><span>Costo</span><b>{money(costo, 2)}</b></div>"
            f"<div><span>Ganancia</span><b style='color:{color_m(r['Margen retail %'])}'>{money(ganancia, 2)}</b></div>"
            f"<div><span>Margen</span><b style='color:{color_m(r['Margen retail %'])}'>{pct(r['Margen retail %'])}</b></div>"
            "</div>")
        cabecera = _cab

        partes = [
            ('Proveedor', r['Costo proveedor'], ''),
            ('Ajuste cambiario', r['Costo + FX'] - r['Costo proveedor'],
             f"tasa {p['B4']:,.0f} ÷ {p['B5']:,.0f}"),
            ('Empaque', r['Empaque'], ''),
            ('Flete', r['Flete/und'], f"{money(p['B8'])} ÷ {r['Unid/caja']:.0f} und"),
            ('Arancel', p['B9'], ''),
        ]
        if _nan(precio) or _nan(costo) or precio <= 0:
            barra = ''
        else:
            segs = partes + [('Ganancia', max(ganancia, 0), '')]
            total = max(precio, costo)
            barra = "<div class='bar'>" + ''.join(
                f"<div title='{n}' style='width:{max(v, 0) / total * 100:.2f}%;background:{SEG[n]}'></div>"
                for n, v, _ in segs if not _nan(v) and v > 0) + "</div>"
        _est = emp_actual(producto_sel)
        partes[2] = ('Empaque', r['Empaque'],
                     {'default': 'general', 'manual': '', 'componentes': 'detallado'}.get(_est['modo'], ''))
        lineas = ''
        for n, v, nota in partes:
            lineas += (f"<div class='ln'><span><i style='background:{SEG[n]}'></i>{n}"
                       f"{f'<small>{nota}</small>' if nota else ''}</span><span>{money(v, 2)}</span></div>")
            if n == 'Empaque' and _est['modo'] == 'componentes':
                lineas += ''.join(f"<div class='ln sub'><span>{html.escape(c)}</span><span>{money(x, 2)}</span></div>"
                                  for c, x in _est['items'])
        st.markdown(
            cabecera + barra + lineas +
            f"<div class='ln total'><span>Costo variable por unidad</span><span>{money(costo, 2)}</span></div>"
            "</div>", unsafe_allow_html=True)

    # Precios por volumen
    st.markdown("")
    def _tarjetas(tiers):
        return ''.join(
            f"<div class='tier'><span>{t}</span><b>{money(r[c])}</b>"
            f"<em style='color:{color_m(r[m])}'>{pct(r[m])} margen · {money(r[c] - r['Costo variable'], 2)}/und</em></div>"
            for t, c, m in tiers)

    ws_tiers = [('Retail', 'Precio retail', 'Margen retail %'),
                ('Wholesale 6–24', 'WS 6–24', 'Margen WS 6–24 %'),
                ('Wholesale 25–49', 'WS 25–49', 'Margen WS 25–49 %'),
                ('Wholesale 50–99', 'WS 50–99', 'Margen WS 50–99 %')]
    corp_tiers = [(f'Corporativo {n}', f'Corp {n}', f'Margen Corp {n} %')
                  for n in ['12–30', '31–60', '61–99', '100–200']]
    und = r['Und/mes para cubrir fijos']
    fijos = money(p['B16'])
    st.markdown(
        "<div class='panel'><div class='panel-t'>Retail y wholesale</div>"
        f"<div class='tiers'>{_tarjetas(ws_tiers)}</div>"
        f"<div class='nota'>Wholesale = {p['B10']:.0%} / {p['B11']:.0%} / {p['B12']:.0%} del retail. "
        f"{'' if _nan(und) else f'A precio WS 6–24 necesitas ~{und:,.0f} und/mes para cubrir {fijos} de fijos.'}</div>"
        "</div>", unsafe_allow_html=True)
    st.markdown("")
    st.markdown(
        "<div class='panel'><div class='panel-t'>Corporativo</div>"
        f"<div class='tiers'>{_tarjetas(corp_tiers)}</div>"
        f"<div class='nota'>Corporativo = {p['B13']:.0%} / {p['B14']:.0%} / {p['B15']:.0%} / {p['E15']:.0%} del retail "
        f"(se cambian en Ajustes). Retail ideal (4× costo): <b>{money(r['Retail ideal (4× costo)'])}</b>.</div>"
        "</div>", unsafe_allow_html=True)


# ── Barra de guardado (solo si hay cambios) ───────────────────────

def _limpiar_widgets():
    for k in [k for k in st.session_state if k.startswith('in_') or
              (k.startswith('emp_') and k not in ('emp_orig', 'emp_raw', 'emp_componentes'))]:
        del st.session_state[k]


def _escrituras():
    """(celdas para Modelo, grid nuevo para la pestaña Empaque o None si no cambia)."""
    datos = [{'range': d['range'], 'values': [[float(v) if v != '' else '' for v in d['values'][0]]]}
             for d in P.payload_escritura([c for c in cambios if 'empaque' not in c])]
    componentes = {k: list(v) for k, v in st.session_state['emp_componentes'].items()}
    for prod, est in pend_emp.items():
        valor = P.valor_celda_empaque(prod, est)
        for f_ in prod_orig.loc[prod_orig['Producto'] == prod, 'Fila']:
            datos.append({'range': f'E{int(f_)}', 'values': [[valor]]})
        if est['modo'] == 'componentes':
            componentes[prod] = est['items']
        else:
            componentes.pop(prod, None)
    grid = None
    if componentes != st.session_state['emp_componentes']:
        grid = P.grid_empaque(componentes)
    return datos, grid


def _conflictos(sh, ws, datos):
    valores_ahora, formulas_ahora = _leer_grids(ws)
    vals_orig = {}
    for _, r_ in prod_orig.iterrows():
        vals_orig[f"E{int(r_['Fila'])}"] = (r_['_f_E'], r_['Empaque'])
    out = []
    for c in cambios:
        if 'empaque' in c or c['bloqueada']:
            continue
        f_, col_ = P.celda_a_rc(c['celda'])
        if P.es_formula(P._get(formulas_ahora, f_, col_)):
            out.append(f"{c['celda']} ahora tiene fórmula")
        elif P._distinto(P.a_numero(P._get(valores_ahora, f_, col_)), c['antes']):
            out.append(f"{c['celda']} cambió en el Sheet")
    for d in datos:
        if d['range'] in vals_orig:
            f_, col_ = P.celda_a_rc(d['range'])
            frm, val = vals_orig[d['range']]
            frm_ahora = P._get(formulas_ahora, f_, col_)
            frm_ahora = frm_ahora if P.es_formula(frm_ahora) else ''
            if frm_ahora != frm or (not frm and P._distinto(P.a_numero(P._get(valores_ahora, f_, col_)), val)):
                out.append(f"{d['range']} (empaque) cambió en el Sheet")
    if _leer_empaque(sh) != st.session_state['emp_raw']:
        out.append("la pestaña Empaque cambió en el Sheet")
    return out


if cambios:
    st.markdown("<hr class='rule'>", unsafe_allow_html=True)
    datos, grid_emp_nuevo = _escrituras()
    s1, s2, s3 = st.columns([2.2, 1, 1], vertical_alignment='center')
    with s1:
        def _fmt(c):
            if 'empaque' in c:
                return f"{c['que']}: {money(c['antes'], 2)} → {money(c['despues'], 2)} ({c['nota']})"
            return f"{c['que']}: {c['antes']:g} → {c['despues']:g}"
        detalle = ' · '.join(_fmt(c) for c in cambios[:3] if not (_nan(c['antes']) and _nan(c['despues'])))
        st.markdown(f"<span class='pend'>● {len(cambios)} cambio(s) sin guardar</span>"
                    f"<div class='nota'>{html.escape(detalle)}{' …' if len(cambios) > 3 else ''}</div>",
                    unsafe_allow_html=True)
        clave = st.secrets.get('clave_precios')
        autorizado = (st.text_input("Clave", type="password", label_visibility='collapsed',
                                    placeholder="Clave para guardar") == clave) if clave else True
    if s3.button("Descartar", width='stretch'):
        _limpiar_widgets()
        pend.clear()
        pend_emp.clear()
        st.rerun()
    if s2.button("Guardar en Sheets", type="primary", width='stretch',
                 disabled=not (datos or grid_emp_nuevo) or not autorizado):
        try:
            _, sh = _libro()
            ws = sh.worksheet(P.HOJA)
            conflictos = _conflictos(sh, ws, datos)
            if conflictos:
                st.error("No guardé nada porque la hoja cambió mientras editabas: "
                         + "; ".join(conflictos) + ". Presiona *Recargar*.")
            else:
                if grid_emp_nuevo is not None:   # primero el detalle, luego las fórmulas que lo usan
                    try:
                        ws_emp = sh.worksheet(P.HOJA_EMPAQUE)
                    except WorksheetNotFound:
                        ws_emp = sh.add_worksheet(P.HOJA_EMPAQUE, rows=200, cols=3)
                    ws_emp.clear()
                    ws_emp.update(grid_emp_nuevo, 'A1', value_input_option='RAW')
                if datos:
                    ws.batch_update(datos, value_input_option='USER_ENTERED')
                _limpiar_widgets()
                cargar()
                st.session_state['precios_guardado'] = True
                st.rerun()
        except APIError as e:
            st.error(f"Google Sheets rechazó la escritura: `{e}`")

if st.session_state.pop('precios_guardado', None):
    st.toast("Hoja de precios actualizada")
