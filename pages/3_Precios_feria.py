"""Precios feria: costos reales de lo que se lleva a una feria (solo Nicolás).

Por cada producto/cuero que se lleva: unidades, precio, costo del producto,
empaque y envío. Arranca con los valores de la hoja Modelo y se ajustan aquí
(empaques exclusivos de feria, envío del lote). Con eso calcula costo total,
margen y descuento máximo; la página Feria usa estos mismos números.
Se guarda en la pestaña "Feria" de MORAES_precios_ok (solo valores ajustados).
"""
import base64
import html
import math
from pathlib import Path

import streamlit as st
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from gspread.utils import ValueRenderOption

import feria as F
import precios as P
from auth import autenticar
from constants import SHEET_PRECIOS_ID as _PRECIOS_DEFAULT
from estilo_feria import CSS, LINE, INK, MUTED, FAINT, ACENTO, MIEL, VERDE, ROJO

st.set_page_config(page_title="MORAES · Precios feria", page_icon="🧾", layout="wide",
                   initial_sidebar_state="collapsed")
SHEET_ID = st.secrets.get('sheet_precios_id') or _PRECIOS_DEFAULT
CLAVE = st.secrets.get('clave_precios')

st.markdown(CSS, unsafe_allow_html=True)
st.markdown(f"""<style>
.block-container {{ max-width:1180px; }}
.fila-c {{ font-family:'Fraunces',serif; font-size:1.05rem; color:{INK}; margin:.9rem 0 .1rem; }}
.res {{ display:flex; gap:1.1rem; flex-wrap:wrap; font-size:.85rem; color:{MUTED};
        padding:.35rem 0 .6rem; border-bottom:1px dashed {LINE}; }}
.res b {{ color:{INK}; font-size:.95rem; }}
.aj {{ color:{ACENTO}; font-size:.72rem; font-weight:600; letter-spacing:.05em; }}
.mini img {{ height:110px !important; }}
.mini.vacia {{ height:110px !important; font-size:2rem !important; }}
/* Popovers (Editar, ✎ Nombre, ＋ Color): sin la franja oscura del tema global */
[data-testid="stPopoverBody"] > div {{ background:transparent !important; }}
[data-testid="stPopoverBody"] label, [data-testid="stPopoverBody"] label p {{ color:{MUTED} !important; }}
</style>""", unsafe_allow_html=True)

if CLAVE and not (st.session_state.get('precios_ok') or st.session_state.get('admin')):
    st.markdown("<p class='eyebrow'>MORAES</p><div class='titulo'>Precios feria</div>", unsafe_allow_html=True)
    with st.form('acceso_pf'):
        c = st.text_input("Clave", type='password')
        if st.form_submit_button("Entrar", type='primary'):
            if c == CLAVE:
                st.session_state['precios_ok'] = True
                st.rerun()
            st.error("Clave incorrecta.")
    st.stop()


# ── Datos ─────────────────────────────────────────────────────────
def _libro():
    return autenticar().open_by_key(SHEET_ID)


@st.cache_data(ttl=600, show_spinner=False)
def cargar_base(_sid):
    ws = _libro().worksheet(P.HOJA)
    rango = f"A1:X{ws.row_count}"
    valores = ws.get(rango, value_render_option=ValueRenderOption.unformatted)
    formulas = ws.get(rango, value_render_option=ValueRenderOption.formula)
    params, prod = P.parsear(list(valores), list(formulas))
    df = P.calcular(params, prod)
    arancel = dict(zip(params['Celda'], params['Valor'])).get('B9', 0.0)
    return F.defaults_modelo(df, arancel)


def _ws_feria(sh, crear=False):
    try:
        return sh.worksheet(F.HOJA_FERIA)
    except WorksheetNotFound:
        return sh.add_worksheet(F.HOJA_FERIA, rows=300, cols=10) if crear else None


def cargar_feria():
    sh = _libro()
    ws = _ws_feria(sh)
    grid = ws.get_all_values(value_render_option=ValueRenderOption.unformatted) if ws else []
    try:
        ws_v = sh.worksheet(F.HOJA_VENTAS)
        hay_ventas = {str(r.get('Feria', '')).strip() for r in F.parsear_ventas(ws_v.get_all_values())}
    except WorksheetNotFound:
        hay_ventas = set()
    cfg, stock, ajustes = F.parsear_feria(grid)
    semilla = not stock and not ajustes
    if semilla:                      # primera vez: la lista a mano de Nicolás, sin guardar
        stock = dict(F.SEMILLA)
    emp_cat, emp_desp = F.parsear_empaques(grid)
    emp_semilla = emp_cat is None and emp_desp is None
    if emp_cat is None:              # todavía sin empaques guardados: los del pedido, costos en 0
        emp_cat = dict(F.CATALOGO_SEMILLA)
    if emp_desp is None:
        emp_desp = {p: list(v) for p, v in F.DESPIECE_SEMILLA.items()}
    st.session_state['pf'] = {'cfg': cfg, 'stock': stock, 'ajustes': ajustes, 'ferias_con_ventas': hay_ventas,
                              'semilla': semilla, 'emp_cat': emp_cat, 'emp_desp': emp_desp,
                              'emp_semilla': emp_semilla}
    for k in [k for k in st.session_state if k.startswith('pf_')]:
        del st.session_state[k]
    st.session_state['pf_items'] = list(dict.fromkeys(list(stock) + list(ajustes)))


try:
    base = cargar_base(SHEET_ID)
    if 'pf' not in st.session_state:
        cargar_feria()
except (APIError, SpreadsheetNotFound, PermissionError) as e:
    st.error(f"No pude abrir la hoja de precios.\n\n`{e}`")
    st.stop()

pf = st.session_state['pf']
cfg0, stock0, aj0 = pf['cfg'], pf['stock'], pf['ajustes']
productos = list(dict.fromkeys(p for p, _ in base))


def money(x, dec=0):
    return '—' if x is None or (isinstance(x, float) and math.isnan(x)) else f"{'-' if x < 0 else ''}${abs(x):,.{dec}f}"


def pct(x):
    return '—' if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.0%}"


CARPETA_FOTOS = Path(__file__).resolve().parent.parent / 'fotos'


@st.cache_data(show_spinner=False)
def _foto_uri(nombre):
    ruta = CARPETA_FOTOS / nombre
    return 'data:image/webp;base64,' + base64.b64encode(ruta.read_bytes()).decode() if ruta.exists() else None


def foto_mini(prod):
    uri = _foto_uri(F.FOTOS[prod]) if prod in F.FOTOS else None
    if not uri:
        return f"<div class='ph vacia mini'>{html.escape(prod[:1])}</div>"
    return f"<div class='ph mini'><img src='{uri}' alt=''></div>"


def _k(campo, k):
    return f"pf_{campo}_{k[0]}_{k[1]}"


# ── Encabezado y ajustes de la feria ──────────────────────────────
st.markdown("<p class='eyebrow'>MORAES · Precios feria</p>"
            "<div class='titulo'>Costos de la feria</div>"
            "<p class='pm'>Todo arranca con los valores de la hoja de precios. Cambia lo que sea distinto "
            "en esta feria (empaque nuevo, envío del lote, precio). Valentina no ve esta página.</p>",
            unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns([2, 1, 1, 1.3])
nombre = c1.text_input("Nombre de la feria", value=cfg0['feria'], key='pf_nombre')
dmax = c2.number_input("Descuento máximo %", 0, 90, int(round(cfg0['desc_max'] * 100)), step=1, key='pf_dmax')
mmin = c3.number_input("Margen mínimo %", 0, 95, int(round(cfg0['margen_min'] * 100)), step=1, key='pf_mmin',
                       help="El descuento nunca deja la venta por debajo de este margen")
otros = c4.number_input("Otros gastos de la feria ($)", 0.0, value=float(cfg0['otros_gastos']), step=10.0,
                        key='pf_otros', help="Stand, inscripción, transporte, comida. No se cargan a cada "
                        "producto: se usan para el punto de equilibrio.")
cfg = {'feria': nombre.strip() or 'Feria', 'desc_max': dmax / 100, 'margen_min': mmin / 100,
       'otros_gastos': float(otros)}

items = st.session_state.setdefault('pf_items', [])
claves = list(items)
nuevos = {p for p, _ in items if not any(F.base_de(base, k) for k in items if k[0] == p)}

# Valores actuales (widgets) por producto/cuero
for k in claves:
    st.session_state.setdefault(_k('stock', k), int(stock0.get(k, 0)))
    v0 = F.valores_feria(base, aj0, k)
    for c in F.CAMPOS:
        st.session_state.setdefault(_k(c, k), round(float(v0[c]), 2) if not math.isnan(v0[c]) else 0.0)


def actuales():
    stock = {k: int(st.session_state[_k('stock', k)]) for k in claves}
    ajustes = {}
    for k in claves:
        aj = {}
        for c in F.CAMPOS:
            v, d = float(st.session_state[_k(c, k)]), F.base_de(base, k).get(c, math.nan)
            if math.isnan(d) or abs(v - d) > 0.005:
                aj[c] = v
        if aj:
            ajustes[k] = aj
    return stock, ajustes


stock, ajustes = actuales()

# ── Reparto del envío ─────────────────────────────────────────────
with st.expander("Repartir el envío del lote"):
    st.markdown("<div class='nota'>Pon lo que pagaste en total por mandar las cajas. Se reparte entre las "
                "unidades que llevas según su tamaño (unidades por caja en la hoja): un Duffle carga más "
                "envío que un Luggage Tag. Después puedes corregir cualquier valor a mano.</div>",
                unsafe_allow_html=True)
    e1, e2 = st.columns([2, 1], vertical_alignment='bottom')
    total_env = e1.number_input("Envío total ($)", 0.0, step=10.0, key='pf_env_total')
    if e2.button("Repartir", width='stretch', disabled=not any(q > 0 for q in stock.values())):
        for k, v in F.repartir_envio(base, stock, total_env).items():
            st.session_state[_k('envio', k)] = round(v, 2)
        st.rerun()

# ── Empaques de la feria (despiece) ───────────────────────────────
# Catálogo de trabajo (nombre → costo por unidad) y despiece por producto, en session_state.
cat_w = st.session_state.setdefault('pf_cat', dict(pf['emp_cat']))
for _e, _c in cat_w.items():
    st.session_state.setdefault(f'pf_cc_{_e}', float(_c))
catalogo = {e: float(st.session_state.get(f'pf_cc_{e}', c)) for e, c in cat_w.items()}
prods_feria = list(dict.fromkeys(p for p, _ in claves))


def _desp_de(prod):
    """Despiece actual de un producto: lo elegido en su tarjeta, o lo guardado."""
    sel = st.session_state.get(f'pf_dm_{prod}')
    if sel is None:
        return [(e, float(q)) for e, q in pf['emp_desp'].get(prod, [])]
    return [(e, float(st.session_state.get(f'pf_dq_{prod}_{e}', 1.0))) for e in sel]


def _mover(viejo, nuevo):
    """Pasa el valor de una clave de session_state a otra (si existe)."""
    if viejo in st.session_state:
        st.session_state[nuevo] = st.session_state.pop(viejo)


def _renombrar_empaque(viejo):
    """Callback de 'Editar' en un empaque: cambia el nombre en el catálogo y en los productos que lo usan,
    conservando costo y cantidades."""
    nuevo = str(st.session_state.get(f'pf_en_{viejo}', '')).strip()
    cat = st.session_state['pf_cat']
    if not nuevo or nuevo == viejo:
        return
    if nuevo in cat:
        st.toast(f"Ya existe un empaque llamado «{nuevo}».")
        return
    costo = float(st.session_state.get(f'pf_cc_{viejo}', cat.get(viejo, 0.0)))
    st.session_state['pf_cat'] = {(nuevo if e == viejo else e): (costo if e == viejo else c) for e, c in cat.items()}
    st.session_state.pop(f'pf_cc_{viejo}', None)
    st.session_state[f'pf_cc_{nuevo}'] = costo
    for k in [k for k in list(st.session_state) if k.startswith('pf_dm_')]:
        sel = st.session_state[k]
        if isinstance(sel, list) and viejo in sel:
            prod = k[len('pf_dm_'):]
            st.session_state[k] = [nuevo if e == viejo else e for e in sel]
            _mover(f'pf_dq_{prod}_{viejo}', f'pf_dq_{prod}_{nuevo}')
    st.session_state['pf']['emp_desp'] = {p: [(nuevo if e == viejo else e, q) for e, q in partes]
                                          for p, partes in st.session_state['pf']['emp_desp'].items()}
    st.toast(f"Empaque renombrado: {viejo} → {nuevo}. Recuerda «Guardar feria».")


def _renombrar_producto(viejo):
    """Callback de '✎ Nombre' (solo productos nuevos): cambia el nombre en todos sus colores,
    conservando unidades, precio, costos y empaques."""
    nuevo = str(st.session_state.get(f'pf_pn_{viejo}', '')).strip()
    lista = st.session_state['pf_items']
    if not nuevo or nuevo == viejo:
        return
    if any(p == nuevo for p, _ in lista):
        st.toast(f"Ya hay un producto llamado «{nuevo}».")
        return
    for i, k in enumerate(list(lista)):
        if k[0] != viejo:
            continue
        nk = (nuevo, k[1])
        for c in ['stock'] + list(F.CAMPOS):
            _mover(_k(c, k), _k(c, nk))
        lista[i] = nk
    for k in [k for k in list(st.session_state) if k.startswith(f'pf_dq_{viejo}_')]:
        _mover(k, f'pf_dq_{nuevo}_' + k[len(f'pf_dq_{viejo}_'):])
    _mover(f'pf_dm_{viejo}', f'pf_dm_{nuevo}')
    desp = st.session_state['pf']['emp_desp']
    if viejo in desp:
        desp[nuevo] = desp.pop(viejo)
    sig = st.session_state.get('pf_emp_sig')
    if isinstance(sig, dict) and viejo in sig:
        sig[nuevo] = sig.pop(viejo)
    st.toast(f"Producto renombrado: {viejo} → {nuevo}. Recuerda «Guardar feria».")


despiece = {p: _desp_de(p) for p in dict.fromkeys(prods_feria + list(pf['emp_desp']))}
despiece = {p: v for p, v in despiece.items() if v}
emp_total = {p: F.empaque_por_despiece(catalogo, partes) for p, partes in despiece.items()}

with st.expander("Empaques de la feria (costos)", expanded=bool(pf.get('emp_semilla'))):
    st.markdown("<div class='nota'>Costo por unidad de cada empaque (bolsa, caja, logo, marquilla…). "
                "Qué lleva cada producto lo eliges en su tarjeta, abajo. Cuando cambias un costo, el "
                "<b>Empaque</b> de los productos que lo usan se recalcula solo.</div>", unsafe_allow_html=True)
    for e in list(cat_w):
        c1, c2, c4, c3 = st.columns([3, 1.4, .7, .7], vertical_alignment='bottom')
        c1.markdown(f"<div class='fila-c'>{html.escape(e)}</div>", unsafe_allow_html=True)
        c2.number_input("Costo por unidad ($)", 0.0, step=0.05, format='%.2f', key=f'pf_cc_{e}')
        with c4.popover("Editar", width='stretch'):
            st.text_input("Nuevo nombre", value=e, key=f'pf_en_{e}')
            st.button("Guardar nombre", key=f'pf_enb_{e}', width='stretch',
                      on_click=_renombrar_empaque, args=(e,))
        if c3.button("Quitar", key=f'pf_cq_{e}', width='stretch'):
            del cat_w[e]
            st.session_state.pop(f'pf_cc_{e}', None)
            st.rerun()
    n1, n2, n3 = st.columns([3, 1.4, .7], vertical_alignment='bottom')
    nuevo_e = n1.text_input("Nuevo empaque", placeholder="Ej: logo estampado, marquilla, papel seda…",
                            key='pf_ne_nombre')
    nuevo_c = n2.number_input("Costo por unidad ($)", 0.0, step=0.05, format='%.2f', key='pf_ne_costo')
    if n3.button("Agregar", key='pf_ne_btn', width='stretch') and nuevo_e.strip():
        cat_w[nuevo_e.strip()] = float(nuevo_c)
        st.session_state[f'pf_cc_{nuevo_e.strip()}'] = float(nuevo_c)
        for _x in ('pf_ne_nombre', 'pf_ne_costo'):
            st.session_state.pop(_x, None)
        st.rerun()
    _sin_costo = sorted({e for partes in despiece.values() for e, _ in partes if not catalogo.get(e)})
    if _sin_costo:
        st.markdown("<div class='aviso'>Falta el costo de: " + ', '.join(html.escape(e) for e in _sin_costo)
                    + ". Mientras esté en 0, no suma al empaque.</div>", unsafe_allow_html=True)

# Cuando cambia el despiece (o el costo de un empaque) de un producto, su Empaque se recalcula
# en todos sus colores. Al cargar no se toca nada: se respeta lo guardado.
_firma = {p: tuple((e, round(q, 4), round(catalogo.get(e, 0.0), 4)) for e, q in partes)
          for p, partes in despiece.items()}
_previa = st.session_state.get('pf_emp_sig')
if _previa is not None:
    for p, f in _firma.items():
        if _previa.get(p) != f:
            for k in [k for k in claves if k[0] == p]:
                st.session_state[_k('empaque', k)] = round(emp_total[p], 2)
st.session_state['pf_emp_sig'] = _firma
stock, ajustes = actuales()

# ── Resumen ───────────────────────────────────────────────────────
r = F.resumen_feria(base, stock, ajustes, cfg)
eq = (f"<span>Para cubrir otros gastos <b>{r['equilibrio_und']} und</b></span>"
      if r['equilibrio_und'] else '')
st.markdown(f"<div class='resumen'><span>Llevas <b>{r['unidades']}</b> und</span>"
            f"<span>Venta a precio lleno <b>{money(r['venta'])}</b></span>"
            f"<span>Costo total <b>{money(r['costo'])}</b></span>"
            f"<span>Ganancia <b>{money(r['ganancia'])}</b></span>"
            f"<span>Después de otros gastos <b>{money(r['neto'])}</b></span>{eq}</div>",
            unsafe_allow_html=True)
if pf.get('semilla'):
    st.markdown("<div class='aviso'>Esto es tu lista a mano, todavía sin guardar. Revisa unidades y valores "
                "y dale <b>Guardar feria</b> abajo.</div>", unsafe_allow_html=True)
if nuevos:
    st.markdown("<div class='aviso'>Productos nuevos (aún no están en la hoja de precios): "
                + ', '.join(html.escape(p) for p in sorted(nuevos))
                + ". Ponles precio y costos aquí; mientras el precio esté en 0, Valentina no los ve.</div>",
                unsafe_allow_html=True)

# ── Agregar producto ──────────────────────────────────────────────
with st.expander("Agregar producto o color"):
    a1, a2, a3, a4 = st.columns([2, 1.2, 1.2, 1], vertical_alignment='bottom')
    _todos = productos + sorted({p for p, _ in items} - set(productos)) + ['＋ Producto nuevo…']
    n_prod = a1.selectbox("Producto", _todos, key='pf_n_prod')
    if n_prod == '＋ Producto nuevo…':
        n_prod = a1.text_input("Nombre del producto nuevo", key='pf_n_nuevo').strip()
    n_cuero = a2.selectbox("Cuero", F.CUEROS_HOJA, key='pf_n_cuero')
    n_color = a3.text_input("Color (opcional)", placeholder="negra, café, azul…", key='pf_n_color')
    if a4.button("Agregar", width='stretch'):
        var = f"{n_cuero} {n_color.strip()}".strip()
        if n_prod and (n_prod, var) not in items:
            items.append((n_prod, var))
        st.rerun()

# ── Productos ─────────────────────────────────────────────────────
ETQ = {'precio': 'Precio', 'costo': 'Costo producto', 'empaque': 'Empaque', 'envio': 'Envío'}
for prod in list(dict.fromkeys(p for p, _ in claves)):
    with st.container(border=True):
        a, b = st.columns([1, 6], gap='medium')
        a.markdown(foto_mini(prod), unsafe_allow_html=True)
        with b:
            _cod = F.CODIGOS_NUEVOS.get(prod)
            st.markdown(f"<p class='pn'>{html.escape(prod)}"
                        f"{f' <span class=aj>· NUEVO · cód. {_cod}</span>' if _cod else (' <span class=aj>· NUEVO</span>' if prod in nuevos else '')}"
                        "</p>", unsafe_allow_html=True)
            if prod in nuevos:      # solo los nuevos: los de la hoja de precios se llaman como en la hoja
                with st.popover("✎ Nombre"):
                    st.text_input("Nuevo nombre del producto", value=prod, key=f'pf_pn_{prod}')
                    st.button("Guardar nombre", key=f'pf_pnb_{prod}', width='stretch',
                              on_click=_renombrar_producto, args=(prod,))
            d1, d2 = st.columns([3, 1], vertical_alignment='bottom')
            _sel0 = [e for e, _ in despiece.get(prod, []) if e in cat_w]
            st.session_state.setdefault(f'pf_dm_{prod}', _sel0)
            _sel = d1.multiselect("Empaque que lleva", list(cat_w), key=f'pf_dm_{prod}',
                                  placeholder="Sin empaque de feria (usa el de siempre)")
            with d2.popover("＋ Color", width='stretch'):
                _cu = st.selectbox("Cuero", F.CUEROS_HOJA, key=f'pf_ac_cuero_{prod}')
                _co = st.text_input("Color (opcional)", placeholder="negra, café, azul…", key=f'pf_ac_color_{prod}')
                if st.button("Agregar", key=f'pf_ac_btn_{prod}', width='stretch'):
                    _var = f"{_cu} {_co.strip()}".strip()
                    if (prod, _var) not in items:
                        items.append((prod, _var))
                    st.rerun()
            if _sel:
                _qc = st.columns(4)
                for i_, e in enumerate(_sel):
                    _q0 = dict(despiece.get(prod, [])).get(e, 1.0)
                    st.session_state.setdefault(f'pf_dq_{prod}_{e}', float(_q0))
                    _qc[i_ % 4].number_input(f"Cantidad · {e}", 0.0, step=1.0, format='%g',
                                                    key=f'pf_dq_{prod}_{e}')
            if prod in despiece:
                _det = ' + '.join(f"{html.escape(e)}{f' ×{q:g}' if q != 1 else ''} ({money(catalogo.get(e, 0.0), 2)})"
                                  for e, q in despiece[prod])
                st.markdown(f"<div class='nota'>Empaque por despiece: {_det} = <b>{money(emp_total[prod], 2)}</b> "
                            f"por unidad</div>", unsafe_allow_html=True)
            for k in [k for k in claves if k[0] == prod]:
                v = {c: float(st.session_state[_k(c, k)]) for c in F.CAMPOS}
                res = F.resultado(v, cfg)
                ajust = [ETQ[c].lower() for c in ajustes.get(k, {})]
                st.markdown(f"<div class='fila-c'>{html.escape(k[1])}"
                            f"{f' <span class=aj>· ajustado: {html.escape(chr(44).join(ajust))}</span>' if ajust else ''}"
                            "</div>", unsafe_allow_html=True)
                cols = st.columns([1, 1, 1, 1, 1, .55], vertical_alignment='bottom')
                cols[0].number_input("Unidades", 0, step=1, key=_k('stock', k))
                if cols[5].button("Quitar", key=f"pfq_{k[0]}_{k[1]}", width='stretch'):
                    items.remove(k)
                    st.rerun()
                for col, c in zip(cols[1:5], F.CAMPOS):
                    d = F.base_de(base, k).get(c, math.nan)
                    col.number_input(ETQ[c], 0.0, step=1.0 if c == 'precio' else 0.5, format='%.2f', key=_k(c, k),
                                     help=f"Hoja de precios: {money(d, 2)}")
                mcol = ROJO if res['margen'] < cfg['margen_min'] else MIEL if res['margen'] < 0.5 else VERDE
                st.markdown(f"<div class='res'><span>Costo total <b>{money(res['costo_total'], 2)}</b></span>"
                            f"<span>Margen <b style='color:{mcol}'>{pct(res['margen'])}</b></span>"
                            f"<span>Descuento máx. <b>{res['desc_tope']}%</b></span>"
                            f"<span>Precio mínimo <b>{money(res['precio_min'])}</b></span></div>",
                            unsafe_allow_html=True)

# ── Guardar ───────────────────────────────────────────────────────
st.markdown("")
if cfg['feria'] != cfg0['feria'] and cfg0['feria'] in pf['ferias_con_ventas']:
    st.markdown("<div class='aviso'>Al cambiar el nombre empiezas una feria nueva: el conteo de vendidos "
                "arranca de cero.</div>", unsafe_allow_html=True)
g1, g2 = st.columns([3, 1])
if g1.button("Guardar feria", type='primary', width='stretch'):
    try:
        sh = _libro()
        ws = _ws_feria(sh, crear=True)
        ws.clear()
        ws.update(F.grid_feria(cfg, {k: q for k, q in stock.items() if q > 0 or k in ajustes}, ajustes,
                               catalogo=catalogo, despiece=despiece),
                  'A1', value_input_option='RAW')
        try:
            sh.worksheet(F.HOJA_VENTAS)
        except WorksheetNotFound:
            wv = sh.add_worksheet(F.HOJA_VENTAS, rows=1000, cols=len(F.CAB_VENTAS))
            wv.update([F.CAB_VENTAS], 'A1', value_input_option='RAW')
        cargar_feria()
        st.session_state['pf_guardado'] = True
        st.rerun()
    except APIError as e:
        st.error(f"No pude guardar: `{e}`")
if g2.button("Recargar", width='stretch', help="Descarta cambios sin guardar"):
    cargar_feria()
    st.rerun()
if st.session_state.pop('pf_guardado', None):
    st.markdown("<div class='ok'>✓ Feria guardada. La página de Valentina ya usa estos precios y costos.</div>",
                unsafe_allow_html=True)
