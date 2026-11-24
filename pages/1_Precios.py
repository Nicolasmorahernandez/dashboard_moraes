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
    'Proveedor': '#7a4a2e', 'Fabricación': '#7a4a2e', 'Ajuste cambiario': '#a0643d', 'Empaque': '#c49a6c',
    'Flete': '#8c7a6b', 'Arancel': '#5e5048', 'Ganancia': '#86c58a',
}
CHIP_TALLER = "<span class='chip'>Taller</span>"
CHIP_NUEVO = "<span class='chip nuevo'>Nuevo · sin guardar</span>"
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
.stButton > button[kind="primary"]:disabled {{ opacity:.35; }}
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
.chip.nuevo {{ color:{GREEN}; }}
.chip {{ display:inline-block; font-size:.66rem; letter-spacing:.1em; text-transform:uppercase; color:{GOLD}; border:1px solid {LINE}; border-radius:999px; padding:.1rem .55rem; margin-left:.4rem; vertical-align:middle; }}
.aviso {{ font-size:.78rem; color:{GOLD}; margin:.35rem 0; }}
table.np {{ width:100%; border-collapse:collapse; font-size:.8rem; margin:.6rem 0 .2rem; }}
table.np th {{ text-align:right; font-weight:500; color:{MUTED}; font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; padding:.3rem .4rem; border-bottom:1px solid {LINE}; }}
table.np td {{ text-align:right; padding:.45rem .4rem; border-bottom:1px solid {LINE}; color:{INK}; line-height:1.25; }}
table.np td em {{ font-style:normal; font-size:.74rem; color:{FAINT}; }}
table.np td.q {{ text-align:left; }}
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


def _leer_tab(sh, nombre):
    """Grid de una pestaña auxiliar, o None si no existe todavía."""
    try:
        ws = sh.worksheet(nombre)
    except WorksheetNotFound:
        return None
    return [list(f) for f in ws.get_all_values(value_render_option=ValueRenderOption.unformatted)]


def _leer_empaque(sh):
    return _leer_tab(sh, P.HOJA_EMPAQUE)


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
        grid_mat = _leer_tab(sh, P.HOJA_MATERIALES)
        grid_fab = _leer_tab(sh, P.HOJA_FAB)
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
    st.session_state['M_raw'] = grid_mat
    st.session_state['M_orig'] = P.parsear_materiales(grid_mat) if grid_mat is not None else list(P.MATERIALES_BASE)
    st.session_state['F_raw'] = grid_fab
    st.session_state['F_orig'] = P.parsear_fab(grid_fab)
    st.session_state['pend'] = {}
    st.session_state['pend_emp'] = {}
    st.session_state['pend_fab'] = {}
    st.session_state['pend_mat'] = None
    st.session_state['pend_nuevos'] = []
    st.session_state['fila_libre'] = P.ultima_fila_ocupada(valores) + 1
    st.session_state['carga'] = st.session_state.get('carga', 0) + 1


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
M_orig = st.session_state['M_orig']
F_orig = st.session_state['F_orig']
pend_fab = st.session_state.setdefault('pend_fab', {})   # {producto: bom nuevo, o None = vuelve a proveedor}


def _mat_igual(a, b):
    return [(n, u, round(float(x), 6)) for n, u, x in a] == [(n, u, round(float(x), 6)) for n, u, x in b]


def _fab_igual(a, b):
    if a is None or b is None:
        return a is b
    return (all(abs(a[k] - b[k]) < 1e-9 for k in P.FAB_CAMPOS)
            and [(c, round(q, 6)) for c, q in a['items']] == [(c, round(q, 6)) for c, q in b['items']])


if st.session_state.get('pend_mat') is not None and _mat_igual(st.session_state['pend_mat'], M_orig):
    st.session_state['pend_mat'] = None
for _prod in list(pend_fab):
    if _fab_igual(pend_fab[_prod], F_orig.get(_prod)):
        del pend_fab[_prod]


def mat_actual():
    return st.session_state.get('pend_mat') or M_orig


def fab_actual(prod):
    return pend_fab[prod] if prod in pend_fab else F_orig.get(prod)


precios_mat = {n: x for n, _, x in mat_actual()}
desglose_fab = {}   # fila -> desglose del costo fabricado
for _i, _r in prod_nuevo.iterrows():
    _bom = fab_actual(_r['Producto'])
    if _bom is not None:
        _d = P.costo_fabricado(_bom, _r['Cuero'], precios_mat)
        desglose_fab[int(_r['Fila'])] = _d
        prod_nuevo.at[_i, 'Costo proveedor'] = _d['total']
        prod_nuevo.at[_i, '_f_C'] = ''
df = P.calcular(params_nuevo, prod_nuevo)
p = dict(zip(params_nuevo['Celda'], params_nuevo['Valor']))

# Productos nuevos (sin guardar): filas al final de la tabla
pend_nuevos = st.session_state.setdefault('pend_nuevos', [])   # [{'nombre', 'unid', 'cueros'}]


def _ubicar_nuevos():
    """[(producto nuevo, fila inicial)] en el orden en que se escribirán."""
    out, fila_ = [], st.session_state['fila_libre']
    for nv in pend_nuevos:
        out.append((nv, fila_))
        fila_ += len(nv['cueros'])
    return out


def _cueros_nv(nv):
    """Cueros del producto nuevo; si es fabricado, el costo se recalcula con los precios de materiales."""
    if not nv.get('bom'):
        return nv['cueros']
    return [(c, P.costo_fabricado(nv['bom'], c, precios_mat)['total'], pr) for c, _, pr in nv['cueros']]


df_nuevos = pd.concat(
    [P.calcular(params_nuevo, P.df_producto_nuevo(nv['nombre'], nv['unid'], _cueros_nv(nv), f0, p['B7']))
     for nv, f0 in _ubicar_nuevos()], ignore_index=True) if pend_nuevos else None
# El empaque de productos va por su propio camino (modos); se excluye del diff genérico
_filas_fab = {f'C{f}' for f in desglose_fab}
cambios = [c for c in P.cambios_pendientes(params_orig, params_nuevo, prod_orig, prod_nuevo)
           if not (c['celda'][0] == 'E' and int(c['celda'][1:]) >= P.FILA_INICIO)
           and c['celda'] not in _filas_fab]
for _prod, _bom in pend_fab.items():
    cambios.append({'celda': 'C', 'que': f"{_prod} · {'fabricado por mí' if _bom is not None else 'comprado al proveedor'}",
                    'antes': math.nan, 'despues': math.nan, 'bloqueada': False, 'fab': _prod})
for _nv in pend_nuevos:
    cambios.append({'celda': 'N', 'que': f"Producto nuevo: {_nv['nombre']}", 'antes': math.nan,
                    'despues': math.nan, 'bloqueada': False, 'nuevo': True})
if st.session_state.get('pend_mat') is not None:
    cambios.append({'celda': 'M', 'que': 'Precios de materiales', 'antes': math.nan, 'despues': math.nan,
                    'bloqueada': False, 'materiales': True})
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


def _limpiar_widgets(solo_ficha=False):
    """Borra el estado de los widgets para que vuelvan a leer los valores actuales."""
    prefijos = ('emp_', 'fab_') if solo_ficha else ('in_', 'emp_', 'fab_', 'mat_')
    for k in [k for k in st.session_state if k.startswith(prefijos)
              and k not in ('emp_orig', 'emp_raw', 'emp_componentes')]:
        del st.session_state[k]


def ir(producto):
    st.session_state['producto'] = producto
    _limpiar_widgets(solo_ficha=True)
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


def _set_pend_fab(prod, nuevo):
    """Registra el bom nuevo (None = proveedor) y recarga si cambió."""
    orig = F_orig.get(prod)
    if _fab_igual(nuevo, orig):
        if prod in pend_fab:
            del pend_fab[prod]
            st.rerun()
    elif prod not in pend_fab or not _fab_igual(nuevo, pend_fab[prod]):
        pend_fab[prod] = nuevo
        st.rerun()


def bloque_origen(prod, filas_prod, o, fila):
    """Proveedor (costo C editable) o fabricado por mí (hoja de costos)."""
    actual = fab_actual(prod)
    c_con_formula = bool((filas_prod['_f_C'] != '').any()) and actual is None and prod not in F_orig
    opciones = {'prov': 'Proveedor', 'fab': 'Fabricado por mí'}
    if c_con_formula:
        origen = 'prov'
    else:
        origen = st.segmented_control("Origen del producto", list(opciones), format_func=opciones.get,
                                      default='fab' if actual is not None else 'prov',
                                      key=f'fab_origen_{prod}', label_visibility='collapsed') \
            or ('fab' if actual is not None else 'prov')
    if origen == 'prov':
        entrada(f'C{fila}', 'Costo proveedor (USD, a tasa base)', o['Costo proveedor'], bool(o['_f_C']))
        if c_con_formula:
            st.markdown("<div class='nota'>El costo tiene fórmula en el Sheet, así que no se puede "
                        "pasar a fabricado desde aquí.</div>", unsafe_allow_html=True)
        _set_pend_fab(prod, None)
        return
    # Al pasar a fabricado se descartan ediciones manuales del costo
    for f_ in filas_prod['Fila']:
        pend.pop(f'C{int(f_)}', None)
        st.session_state.pop(f'in_C{int(f_)}', None)
    bloque_fabricacion(prod, actual or {**P.FAB_DEFAULT, 'items': []})


def bloque_fabricacion(prod, bom):
    st.markdown("<div class='emp-t'>Hoja de costos (aplica a todos los cueros)</div>", unsafe_allow_html=True)
    a, b = st.columns(2)
    pies2 = a.number_input("Cuero (pie²)", value=float(bom['pies2']), min_value=0.0, step=0.1, format='%.2f',
                           key=f'fab_pies_{prod}', help="Pies² que gasta una unidad, sin contar desperdicio")
    desp = b.number_input("Desperdicio %", value=float(bom['desperdicio']) * 100, min_value=0.0, max_value=200.0,
                          step=1.0, format='%.0f', key=f'fab_desp_{prod}',
                          help="Recortes que se pierden al cortar. 20% es un supuesto inicial")
    minutos = a.number_input("Mano de obra (min)", value=float(bom['minutos']), min_value=0.0, step=5.0,
                             format='%.0f', key=f'fab_min_{prod}', help="Minutos por unidad: corte, costura, cantos")
    taller = b.number_input("Taller %", value=float(bom['taller']) * 100, min_value=0.0, max_value=100.0,
                            step=1.0, format='%.0f', key=f'fab_taller_{prod}',
                            help="Gastos del taller (luz, herramienta, cuchillas) sobre el costo. 5% es un supuesto")
    nombres = [n for n, _, _ in mat_actual()
               if n != P.VALOR_HORA and n not in {P.nombre_cuero(c) for c in P.CUEROS}]
    clave_base = f'fab_base_{prod}'
    if clave_base not in st.session_state:
        items = bom['items'] or [(n, 0.0) for n in ('Hilo', 'Herraje') if n in nombres]
        st.session_state[clave_base] = pd.DataFrame(items, columns=['Material', 'Cantidad'])
    tabla = st.data_editor(
        st.session_state[clave_base], key=f"fab_items_{prod}_{st.session_state.get('visita', 0)}",
        num_rows='dynamic', hide_index=True, width='stretch',
        column_config={'Material': st.column_config.SelectboxColumn(options=nombres, required=True),
                       'Cantidad': st.column_config.NumberColumn(min_value=0.0, format='%.2f')})
    items = [(str(c), float(q) if not _nan(q) else 0.0)
             for c, q in zip(tabla['Material'], tabla['Cantidad']) if c is not None and str(c).strip()]
    st.markdown("<div class='nota'>Cantidad por unidad, en la unidad de cada material (m de hilo, und de "
                "herraje…). Los precios y nuevos materiales se ponen en <b>Materiales</b>, arriba.</div>",
                unsafe_allow_html=True)
    nuevo = {'pies2': float(pies2 or 0), 'desperdicio': float(desp or 0) / 100, 'minutos': float(minutos or 0),
             'taller': float(taller or 0) / 100, 'items': items}
    _set_pend_fab(prod, nuevo)


def _aplicar_delta(base, delta):
    """Aplica los cambios de un st.data_editor (edited/added/deleted rows) a su DataFrame base."""
    out = base.copy()
    for i, cambios_fila in (delta.get('edited_rows') or {}).items():
        for col, v in cambios_fila.items():
            out.at[int(i), col] = v
    out = out.drop(index=[int(i) for i in (delta.get('deleted_rows') or [])])
    nuevas = pd.DataFrame(delta.get('added_rows') or [], columns=out.columns)
    return pd.concat([out, nuevas], ignore_index=True) if len(nuevas) else out.reset_index(drop=True)


def _on_materiales():
    tabla = _aplicar_delta(st.session_state['mat_base'], st.session_state['mat_ed'])
    lista = [(str(n).strip(), '' if _nan(u) or u is None else str(u).strip(), 0.0 if _nan(x) else float(x))
             for n, u, x in tabla.itertuples(index=False) if n is not None and not _nan(n) and str(n).strip()]
    st.session_state['pend_mat'] = None if _mat_igual(lista, M_orig) else lista


MARGEN_RETAIL_DEFAULT = 0.70   # supuesto: punto de partida, se cambia en el formulario


def precios_por_margen(nombre, unid, costos, margen, fila0):
    """costos: [(cuero, costo proveedor)]. Precio retail = costo variable ÷ (1 − margen),
    redondeado a dólar entero como los demás. Devuelve (cueros con precio, df calculado)."""
    tmp = P.calcular(params_nuevo, P.df_producto_nuevo(nombre, unid, [(c, q, 1.0) for c, q in costos], fila0, p['B7']))
    cueros = [(c, q, float(P.redondear(cv / (1 - margen))))
              for (c, q), cv in zip(costos, tmp['Costo variable'])]
    return cueros, P.calcular(params_nuevo, P.df_producto_nuevo(nombre, unid, cueros, fila0, p['B7']))


def tabla_precios_html(d):
    cols = [('Retail', 'Precio retail', 'Margen retail %'), ('WS 6–24', 'WS 6–24', 'Margen WS 6–24 %'),
            ('WS 25–49', 'WS 25–49', 'Margen WS 25–49 %'), ('WS 50–99', 'WS 50–99', 'Margen WS 50–99 %'),
            ('Corp 12–30', 'Corp 12–30', 'Margen Corp 12–30 %'), ('Corp 100–200', 'Corp 100–200',
                                                                   'Margen Corp 100–200 %')]
    cab = ''.join(f"<th>{t}</th>" for t, _, _ in cols)
    filas = ''
    for _, r_ in d.iterrows():
        celdas = ''.join(f"<td><b>{money(r_[c])}</b><br><em style='color:{color_m(r_[m])}'>{pct(r_[m])}</em></td>"
                         for _, c, m in cols)
        filas += (f"<tr><td class='q'>{html.escape(r_['Cuero'])}<br><em>costo {money(r_['Costo variable'], 2)}"
                  f"</em></td>{celdas}</tr>")
    return f"<table class='np'><tr><th></th>{cab}</tr>{filas}</table>"


def hoja_costos_nuevo(idx, bom, cueros):
    """Hoja de costos de un producto fabricado, con los precios de materiales ahí mismo.
    Devuelve (bom, catálogo de materiales actualizado)."""
    k = f'np_{idx}'
    catalogo = {n: (u, x) for n, u, x in mat_actual()}
    st.markdown("<div class='emp-t'>Hoja de costos por unidad (aplica a todos los cueros)</div>",
                unsafe_allow_html=True)
    a, b, c_, d = st.columns(4)
    pies2 = a.number_input("Cuero (pie²)", value=float(bom['pies2']), min_value=0.0, step=0.1, format='%.2f',
                           key=f'{k}_pies', help="Pies² que gasta una unidad, sin contar desperdicio")
    desp = b.number_input("Desperdicio %", value=float(bom['desperdicio']) * 100, min_value=0.0, max_value=200.0,
                          step=1.0, format='%.0f', key=f'{k}_desp', help="20% es un supuesto inicial")
    minutos = c_.number_input("Mano de obra (min)", value=float(bom['minutos']), min_value=0.0, step=5.0,
                              format='%.0f', key=f'{k}_min', help="Minutos por unidad: corte, costura, cantos")
    taller = d.number_input("Taller %", value=float(bom['taller']) * 100, min_value=0.0, max_value=100.0,
                            step=1.0, format='%.0f', key=f'{k}_taller',
                            help="Luz, herramienta, cuchillas, sobre el costo. 5% es un supuesto")
    excluir = {P.VALOR_HORA} | {P.nombre_cuero(c) for c in P.CUEROS}
    opciones = [n for n in catalogo if n not in excluir]
    previos = [cn for cn, _ in bom['items']]
    sel = st.multiselect("Materiales (herrajes, hilo, forro…)", opciones + [x for x in previos if x not in opciones],
                         default=previos or [x for x in ('Hilo', 'Herraje') if x in opciones],
                         accept_new_options=True, key=f'{k}_mats',
                         placeholder="Elige o escribe uno nuevo")
    cant_prev = dict(bom['items'])
    st.markdown("<div class='emp-t'>Precios (se guardan en la pestaña Materiales y sirven para otros productos)</div>",
                unsafe_allow_html=True)
    items, nuevos_precios = [], {}
    fijos = [(P.nombre_cuero(c), 'pie²', f"Cuero {c} (USD/pie²)") for c in cueros] + \
        [(P.VALOR_HORA, 'hora', "Mano de obra (USD/hora)")]
    for col_, (nombre_m, unidad, etiqueta) in zip(st.columns(4 if len(fijos) > 2 else len(fijos)) * 2, fijos):
        precio = col_.number_input(etiqueta, value=float(catalogo.get(nombre_m, (unidad, 0.0))[1]),
                                   min_value=0.0, step=0.5, format='%.2f', key=f'{k}_p_{nombre_m}')
        nuevos_precios[nombre_m] = (unidad, float(precio or 0))
    for n0 in range(0, len(sel), 2):
        cols_ = st.columns(4)
        for t, m in enumerate(sel[n0:n0 + 2]):
            unidad = catalogo.get(m, ('und', 0.0))[0] or 'und'
            q = cols_[2 * t].number_input(f"{m}: cantidad ({unidad})", value=float(cant_prev.get(m, 0.0)),
                                          min_value=0.0, step=0.5, format='%.2f', key=f'{k}_q_{m}')
            precio = cols_[2 * t + 1].number_input(f"{m}: USD por {unidad}",
                                                   value=float(catalogo.get(m, (unidad, 0.0))[1]),
                                                   min_value=0.0, step=0.5, format='%.2f', key=f'{k}_p_{m}')
            items.append((m, float(q or 0)))
            nuevos_precios[m] = (unidad, float(precio or 0))
    lista = [(n, nuevos_precios.get(n, (u, x))[0], nuevos_precios.get(n, (u, x))[1]) for n, (u, x) in catalogo.items()]
    lista += [(n, u, x) for n, (u, x) in nuevos_precios.items() if n not in catalogo]
    bom = {'pies2': float(pies2 or 0), 'desperdicio': float(desp or 0) / 100, 'minutos': float(minutos or 0),
           'taller': float(taller or 0) / 100, 'items': items}
    return bom, lista


@st.dialog("Nuevo producto", width='large')
def dialogo_nuevo(idx=None):
    """Crear (o editar, si idx) un producto nuevo sin guardar: costos primero, precio por margen."""
    previo = pend_nuevos[idx] if idx is not None else None
    a, b = st.columns([2, 1])
    nombre = a.text_input("Nombre", value=previo['nombre'] if previo else '',
                          placeholder="Ej. Card Holder", max_chars=60)
    unid = b.number_input("Unidades por caja", value=float(previo['unid']) if previo else 30.0,
                          min_value=1.0, step=1.0, format='%.0f', help="Para repartir el flete por unidad")
    costos_prev = {c: q for c, q, _ in previo['cueros']} if previo else {}
    bom_prev = (previo or {}).get('bom')
    origen = st.segmented_control("¿Quién lo hace?", ['prov', 'fab'],
                                  format_func={'prov': 'Lo compro al proveedor', 'fab': 'Lo fabrico yo'}.get,
                                  default='fab' if bom_prev else 'prov', key=f'np_origen_{idx}') \
        or ('fab' if bom_prev else 'prov')
    cueros = st.pills("Cueros", list(P.MULT_CUERO), selection_mode='multi',
                      default=list(costos_prev) if previo else ['Vaqueta'], key=f'np_cueros_{idx}') or []
    cueros = [c for c in P.MULT_CUERO if c in cueros]
    costos, bom, mats_nuevos = [], None, None
    if cueros and origen == 'prov':
        st.markdown("<div class='emp-t'>Costo del proveedor por unidad (USD, a la tasa base)</div>",
                    unsafe_allow_html=True)
        cols_ = st.columns(len(cueros))
        for col_, c in zip(cols_, cueros):
            q = col_.number_input(c, value=costos_prev.get(c), min_value=0.0, step=0.5, format='%.2f',
                                  placeholder='0.00', key=f'np_costo_{idx}_{c}')
            costos.append((c, q))
    elif cueros:
        bom, mats_nuevos = hoja_costos_nuevo(idx, bom_prev or {**P.FAB_DEFAULT, 'items': []}, cueros)
        precios_ = {n: x for n, _, x in mats_nuevos}
        costos = [(c, P.costo_fabricado(bom, c, precios_)['total']) for c in cueros]
        st.markdown("<div class='nota'>Costo de fabricación por unidad: " + ' · '.join(
            f"{html.escape(c)} <b>{money(q, 2)}</b>" for c, q in costos) + "</div>", unsafe_allow_html=True)
    margen = st.slider("Margen retail que quieres", min_value=10, max_value=90, step=1,
                       value=int(round((previo or {}).get('margen', MARGEN_RETAIL_DEFAULT) * 100)),
                       format='%d%%', key=f'np_margen_{idx}') / 100

    errores = []
    nombre = (nombre or '').strip()
    existentes = set(prod_orig['Producto']) | {nv['nombre'] for k, nv in enumerate(pend_nuevos) if k != idx}
    if not nombre:
        errores.append("Ponle un nombre.")
    elif nombre.lower() in {x.lower() for x in existentes}:
        errores.append("Ya hay un producto con ese nombre.")
    if not cueros:
        errores.append("Elige al menos un cuero.")
    elif any(q is None or q <= 0 for _, q in costos):
        errores.append("Pon el costo de cada cuero elegido." if origen == 'prov' else
                       "Llena la hoja de costos: el costo de fabricación está en $0.")

    con_precio = None
    if cueros and all(q is not None and q > 0 for _, q in costos):
        con_precio, d = precios_por_margen(nombre or 'nuevo', unid, costos, margen, st.session_state['fila_libre'])
        st.markdown(tabla_precios_html(d), unsafe_allow_html=True)
        st.markdown(f"<div class='nota'>Costo = costo base (proveedor o fabricación) con ajuste cambiario + empaque general "
                    f"({money(p['B7'], 2)}) + flete ({money(p['B8'])} ÷ {unid:.0f} und) + arancel. "
                    "Wholesale y corporativo salen del retail con los % de Ajustes. El retail se redondea "
                    "a dólar entero; después lo puedes ajustar en la ficha.</div>", unsafe_allow_html=True)
    for e in errores:
        st.markdown(f"<div class='aviso'>{html.escape(e)}</div>", unsafe_allow_html=True)
    if st.button("Agregar producto" if idx is None else "Actualizar", type='primary',
                 disabled=bool(errores), width='stretch'):
        nuevo = {'nombre': nombre, 'unid': float(unid), 'margen': margen, 'bom': bom,
                 'cueros': [(c, float(q), float(pr)) for c, q, pr in con_precio]}
        if mats_nuevos is not None:
            st.session_state['pend_mat'] = None if _mat_igual(mats_nuevos, M_orig) else mats_nuevos
            st.session_state.pop('mat_base', None)
            st.session_state.pop('mat_ed', None)
        if idx is None:
            pend_nuevos.append(nuevo)
        else:
            pend_nuevos[idx] = nuevo
        st.rerun()


# ── Encabezado ────────────────────────────────────────────────────
producto_sel = st.session_state.get('producto')

h1, h2 = st.columns([2.3, 2], vertical_alignment='bottom')
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
    b0, b1, b2 = st.columns(3)
    with b0.popover("Materiales", width='stretch'):
        st.markdown("**Precios de materiales**")
        st.caption("Para productos fabricados por ti. Cuero por pie², mano de obra por hora, el resto por "
                   "su unidad. En USD a la tasa base, igual que el costo proveedor: el ajuste cambiario "
                   "se suma encima. Agrega materiales con el + de la tabla.")
        st.session_state.setdefault('mat_base', pd.DataFrame(mat_actual(), columns=P.CAB_MATERIALES))
        st.data_editor(st.session_state['mat_base'], key='mat_ed', num_rows='dynamic', hide_index=True,
                       width='stretch', on_change=_on_materiales,
                       column_config={'Material': st.column_config.TextColumn(required=True),
                                      'Precio (USD)': st.column_config.NumberColumn(min_value=0.0, format='$%.2f')})
        if st.session_state['M_raw'] is None:
            st.caption("La pestaña Materiales se crea en el Sheet la primera vez que guardes.")
    with b1.popover("Ajustes", width='stretch'):
        st.markdown("**Ajustes generales**")
        st.caption("Aplican a todos los productos.")
        for _, r in params_orig.iterrows():
            es_pct = r['pct']
            entrada(r['Celda'], r['Parámetro'], r['Valor'], r['formula'],
                    fmt='%.2f' if es_pct else ('%.0f' if r['Valor'] >= 100 else '%.2f'),
                    step=0.01 if es_pct else (50.0 if r['Valor'] >= 100 else 0.5))
    if b2.button("Recargar", width='stretch', help="Descarta cambios sin guardar y vuelve a leer la hoja"):
        _limpiar_widgets()
        cargar()
        st.rerun()

st.markdown("<hr class='rule'>", unsafe_allow_html=True)


# ── Vista 1: catálogo ─────────────────────────────────────────────
if not producto_sel:
    productos = list(dict.fromkeys(df['Producto']))
    nuevos = [nv['nombre'] for nv in pend_nuevos]
    c_bus, c_nuevo = st.columns([3, 1], vertical_alignment='center')
    buscar = c_bus.text_input("Buscar", placeholder="Buscar producto…", label_visibility='collapsed')
    if c_nuevo.button("＋ Nuevo producto", width='stretch'):
        dialogo_nuevo()
    if buscar:
        productos = [x for x in productos if buscar.lower() in x.lower()]
        nuevos = [x for x in nuevos if buscar.lower() in x.lower()]
    for i, prod in enumerate(nuevos + productos):
        if i % 3 == 0:
            cols = st.columns(3)
        es_nuevo = i < len(nuevos)
        g = (df_nuevos if es_nuevo else df)
        g = g[g['Producto'] == prod]
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
                f"<div class='pc-name'>{html.escape(prod)}"
                f"{CHIP_NUEVO if es_nuevo else CHIP_TALLER if fab_actual(prod) is not None else ''}</div>"
                f"<div class='pc-row'>Retail <b>{precio_txt}</b></div>"
                f"<div class='pc-row'>Margen mínimo <b style='color:{mcol}'>{margen_txt}</b></div>"
                f"<div class='pc-row'>Cueros <b>{len(g)}</b></div>",
                unsafe_allow_html=True)
            if es_nuevo:
                k_ = nuevos.index(prod) if not buscar else [nv['nombre'] for nv in pend_nuevos].index(prod)
                e1, e2 = st.columns(2)
                if e1.button("Editar", key=f"edit_new_{k_}", width='stretch'):
                    dialogo_nuevo(k_)
                if e2.button("Quitar", key=f"del_new_{k_}", width='stretch'):
                    pend_nuevos.pop(k_)
                    st.rerun()
            else:
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
        bloque_origen(producto_sel, prod_orig[prod_orig['Producto'] == producto_sel], o, fila)
        entrada(f'J{fila}', 'Precio retail (USD)', o['Precio retail'], bool(o['_f_J']), fmt='%.0f', step=1.0)
        entrada(f'F{fila}', 'Unidades por caja', o['Unid/caja'], bool(o['_f_F']), fmt='%.0f', step=1.0, min_value=1.0)
        if o['_f_J']:
            st.markdown("<div class='nota'>El precio de este cuero tiene fórmula en el Sheet; se cambia allá.</div>",
                        unsafe_allow_html=True)
        bloque_empaque(producto_sel)
        if fila in desglose_fab:
            _d = desglose_fab[fila]
            if _d['precio_cuero'] == 0:
                st.markdown(f"<div class='aviso'>Falta el precio del cuero {html.escape(cuero)} por pie² en "
                            "<b>Materiales</b>.</div>", unsafe_allow_html=True)
            if _d['valor_hora'] == 0 and fab_actual(producto_sel)['minutos'] > 0:
                st.markdown("<div class='aviso'>Falta el valor hora de mano de obra en <b>Materiales</b>.</div>",
                            unsafe_allow_html=True)
            _sin = [c for c, q, x, _ in _d['detalle_mat'] if q > 0 and x == 0]
            if _sin:
                st.markdown(f"<div class='aviso'>Sin precio en Materiales: {html.escape(', '.join(_sin))}.</div>",
                            unsafe_allow_html=True)

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

        _dfab = desglose_fab.get(fila)
        partes = [
            ('Fabricación' if _dfab else 'Proveedor', r['Costo proveedor'], 'hecho por ti' if _dfab else ''),
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
            if n == 'Fabricación':
                _bom = fab_actual(producto_sel)
                _sub = [(f"Cuero · {_bom['pies2']:g} pie² × {money(_dfab['precio_cuero'], 2)} + {_bom['desperdicio']:.0%}",
                         _dfab['cuero'])]
                _sub += [(f"{c} · {q:g} × {money(x, 2)}", s_) for c, q, x, s_ in _dfab['detalle_mat']]
                _sub += [(f"Mano de obra · {_bom['minutos']:g} min × {money(_dfab['valor_hora'], 2)}/h", _dfab['mano']),
                         (f"Taller · {_bom['taller']:.0%}", _dfab['taller'])]
                lineas += ''.join(f"<div class='ln sub'><span>{html.escape(t)}</span><span>{money(x, 2)}</span></div>"
                                  for t, x in _sub)
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

def _escrituras():
    """(celdas para Modelo, {pestaña auxiliar: grid nuevo} solo las que cambian)."""
    _especiales = {'empaque', 'fab', 'materiales', 'nuevo'}
    datos = [{'range': d['range'], 'values': [[float(v) if v != '' else '' for v in d['values'][0]]]}
             for d in P.payload_escritura([c for c in cambios if not (_especiales & c.keys())])]
    componentes = {k: list(v) for k, v in st.session_state['emp_componentes'].items()}
    for prod, est in pend_emp.items():
        valor = P.valor_celda_empaque(prod, est)
        for f_ in prod_orig.loc[prod_orig['Producto'] == prod, 'Fila']:
            datos.append({'range': f'E{int(f_)}', 'values': [[valor]]})
        if est['modo'] == 'componentes':
            componentes[prod] = est['items']
        else:
            componentes.pop(prod, None)
    grids = {}
    if componentes != st.session_state['emp_componentes']:
        grids[P.HOJA_EMPAQUE] = P.grid_empaque(componentes)
    # Fabricados: C se escribe como número calculado
    filas_c = set(desglose_fab) if st.session_state.get('pend_mat') is not None else set()
    for prod, bom in pend_fab.items():
        if bom is not None:
            filas_c |= {int(f_) for f_ in prod_orig.loc[prod_orig['Producto'] == prod, 'Fila']}
    for f_ in sorted(filas_c):
        datos.append({'range': f'C{f_}', 'values': [[round(float(desglose_fab[f_]['total']), 4)]]})
    for nv, f0 in _ubicar_nuevos():
        filas_ = P.filas_producto_nuevo(nv['nombre'], nv['unid'], _cueros_nv(nv), f0)
        datos.append({'range': f'A{f0}:X{f0 + len(filas_) - 1}', 'values': filas_})
    nuevo_fab = {k: v for k, v in {**F_orig, **pend_fab}.items() if v is not None}
    nuevo_fab.update({nv['nombre']: nv['bom'] for nv in pend_nuevos if nv.get('bom')})
    if pend_fab or any(nv.get('bom') for nv in pend_nuevos):
        grids[P.HOJA_FAB] = P.grid_fab(nuevo_fab)
    if st.session_state.get('pend_mat') is not None or (st.session_state['M_raw'] is None and nuevo_fab):
        grids[P.HOJA_MATERIALES] = P.grid_materiales(mat_actual())
    return datos, grids


def _conflictos(sh, ws, datos):
    valores_ahora, formulas_ahora = _leer_grids(ws)
    vals_orig = {}
    for _, r_ in prod_orig.iterrows():
        vals_orig[f"E{int(r_['Fila'])}"] = (r_['_f_E'], r_['Empaque'])
        vals_orig[f"C{int(r_['Fila'])}"] = (r_['_f_C'], r_['Costo proveedor'])
    out = []
    for c in cambios:
        if {'empaque', 'fab', 'materiales', 'nuevo'} & c.keys() or c['bloqueada']:
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
                out.append(f"{d['range']} cambió en el Sheet")
    if pend_nuevos and P.ultima_fila_ocupada(valores_ahora) != st.session_state['fila_libre'] - 1:
        out.append("se agregaron o borraron filas al final de la tabla")
    for nombre, clave_raw in ((P.HOJA_EMPAQUE, 'emp_raw'), (P.HOJA_MATERIALES, 'M_raw'), (P.HOJA_FAB, 'F_raw')):
        if _leer_tab(sh, nombre) != st.session_state[clave_raw]:
            out.append(f"la pestaña {nombre} cambió en el Sheet")
    return list(dict.fromkeys(out))


if cambios:
    st.markdown("<hr class='rule'>", unsafe_allow_html=True)
    datos, grids_nuevos = _escrituras()
    s1, s2, s3 = st.columns([2.2, 1, 1], vertical_alignment='center')
    with s1:
        def _fmt(c):
            if 'empaque' in c:
                return f"{c['que']}: {money(c['antes'], 2)} → {money(c['despues'], 2)} ({c['nota']})"
            if 'fab' in c or 'materiales' in c or 'nuevo' in c:
                return c['que']
            return f"{c['que']}: {c['antes']:g} → {c['despues']:g}"
        detalle = ' · '.join(_fmt(c) for c in cambios[:3])
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
        pend_fab.clear()
        pend_nuevos.clear()
        st.session_state['pend_mat'] = None
        st.rerun()
    if s2.button("Guardar en Sheets", type="primary", width='stretch',
                 disabled=not (datos or grids_nuevos) or not autorizado):
        try:
            _, sh = _libro()
            ws = sh.worksheet(P.HOJA)
            conflictos = _conflictos(sh, ws, datos)
            if conflictos:
                st.error("No guardé nada porque la hoja cambió mientras editabas: "
                         + "; ".join(conflictos) + ". Presiona *Recargar*.")
            else:
                # primero las pestañas auxiliares (Empaque tiene fórmulas que la usan), luego Modelo
                for nombre, grid in grids_nuevos.items():
                    try:
                        ws_aux = sh.worksheet(nombre)
                    except WorksheetNotFound:
                        ws_aux = sh.add_worksheet(nombre, rows=max(200, len(grid) + 50), cols=len(grid[0]))
                    ws_aux.clear()
                    ws_aux.update(grid, 'A1', value_input_option='RAW')
                if pend_nuevos:
                    falta = st.session_state['fila_libre'] + sum(len(nv['cueros']) for nv in pend_nuevos) - 1 - ws.row_count
                    if falta > 0:
                        ws.add_rows(falta)
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
