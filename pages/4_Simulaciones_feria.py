"""Simulaciones de feria (solo Nicolás): ¿cuánto se gana si vendo X % con Y % de descuento,
con todos los gastos administrativos y con combos? Lee los costos de «Precios feria»
(pestaña Feria de MORAES_precios_ok); no escribe nada en el Sheet."""
import html
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from gspread.utils import ValueRenderOption

import feria as F
import precios as P
import simulacion_feria as S
from auth import autenticar
from constants import SHEET_PRECIOS_ID as _PRECIOS_DEFAULT
from estilo_feria import CSS, CARD, LINE, INK, MUTED, FAINT, ACENTO, MIEL, VERDE, ROJO

st.set_page_config(page_title="MORAES · Simulaciones feria", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")
SHEET_ID = st.secrets.get('sheet_precios_id') or _PRECIOS_DEFAULT
CLAVE = st.secrets.get('clave_precios')

st.markdown(CSS, unsafe_allow_html=True)
st.markdown(f"""<style>
.block-container {{ max-width:1180px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:.7rem; margin:.6rem 0 1rem; }}
.kpi {{ background:{CARD}; border:1px solid {LINE}; border-radius:16px; padding:.8rem 1rem; }}
.kpi small {{ color:{MUTED}; font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; }}
.kpi div {{ font-family:'Fraunces',serif; font-size:1.7rem; color:{INK}; line-height:1.15; }}
.kpi.pos div {{ color:{VERDE}; }} .kpi.neg div {{ color:{ROJO}; }}
.kpi span {{ color:{MUTED}; font-size:.78rem; }}
.sec {{ font-family:'Fraunces',serif; font-size:1.35rem; color:{INK}; margin:1.4rem 0 .2rem; }}
.nota {{ color:{MUTED}; font-size:.85rem; margin-bottom:.5rem; }}
[data-testid="stPopoverBody"] > div {{ background:transparent !important; }}
.tb {{ width:100%; border-collapse:collapse; background:{CARD}; border-radius:12px; overflow:hidden; font-size:.88rem; }}
.tb th {{ text-align:left; color:{MUTED}; font-weight:600; font-size:.72rem; letter-spacing:.06em; text-transform:uppercase;
          padding:.55rem .7rem; border-bottom:1px solid {LINE}; }}
.tb td {{ padding:.5rem .7rem; border-bottom:1px dashed {LINE}; color:{INK}; }}
</style>""", unsafe_allow_html=True)

if CLAVE and not (st.session_state.get('precios_ok') or st.session_state.get('admin')):
    st.markdown("<p class='eyebrow'>MORAES</p><div class='titulo'>Simulaciones</div>", unsafe_allow_html=True)
    with st.form('acceso_sim'):
        c = st.text_input("Clave", type='password')
        if st.form_submit_button("Entrar", type='primary'):
            if c == CLAVE:
                st.session_state['precios_ok'] = True
                st.rerun()
            st.error("Clave incorrecta.")
    st.stop()


# ── Datos (solo lectura) ──────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner="Leyendo costos de la feria…")
def cargar(_sid):
    sh = autenticar().open_by_key(_sid)
    ws = sh.worksheet(P.HOJA)
    rango = f"A1:X{ws.row_count}"
    valores = ws.get(rango, value_render_option=ValueRenderOption.unformatted)
    formulas = ws.get(rango, value_render_option=ValueRenderOption.formula)
    params, prod = P.parsear(list(valores), list(formulas))
    df = P.calcular(params, prod)
    arancel = dict(zip(params['Celda'], params['Valor'])).get('B9', 0.0)
    base = F.defaults_modelo(df, arancel)
    try:
        grid = sh.worksheet(F.HOJA_FERIA).get_all_values(value_render_option=ValueRenderOption.unformatted)
    except WorksheetNotFound:
        grid = []
    cfg, stock, ajustes = F.parsear_feria(grid)
    semilla = not stock and not ajustes
    if semilla:
        stock = dict(F.SEMILLA)
    cat, desp = F.parsear_empaques(grid)
    cat = F.CATALOGO_SEMILLA if cat is None else cat
    desp = F.DESPIECE_SEMILLA if desp is None else desp
    return base, cfg, stock, ajustes, cat, desp, semilla


try:
    base, cfg, stock, ajustes, cat, desp, semilla = cargar(SHEET_ID)
except (APIError, SpreadsheetNotFound, PermissionError) as e:
    st.error(f"No pude abrir la hoja de precios.\n\n`{e}`")
    st.stop()

items = []
for k, q in stock.items():
    if q <= 0:
        continue
    v = F.valores_feria(base, ajustes, k)
    if math.isnan(v['precio']) or v['precio'] <= 0:
        continue                                  # sin precio no se puede simular
    emp = F.empaque_por_despiece(cat, desp[k[0]]) if k[0] in desp and 'empaque' not in ajustes.get(k, {}) else v['empaque']
    costo = sum(0 if math.isnan(x) else x for x in (v['costo'], emp, v['envio']))
    items.append({'producto': k[0], 'cuero': k[1], 'stock': q, 'precio': v['precio'], 'costo': costo})

money = lambda x, d=0: '—' if x is None or (isinstance(x, float) and math.isnan(x)) else f"{'-' if x < 0 else ''}${abs(x):,.{d}f}"

def tabla(df):
    th = ''.join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    tr = ''.join('<tr>' + ''.join(f"<td>{html.escape(str(v))}</td>" for v in row) + '</tr>' for row in df.itertuples(index=False))
    st.markdown(f"<table class='tb'><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>", unsafe_allow_html=True)


st.markdown("<p class='eyebrow'>MORAES · Feria</p><div class='titulo'>Simulaciones</div>"
            "<p class='nota'>Mueve los controles y mira cómo cambia la ganancia. Usa los costos de «Precios feria»; "
            "no guarda ni cambia nada en el Sheet.</p>", unsafe_allow_html=True)
if semilla:
    st.markdown("<div class='nota'>La pestaña «Feria» del Sheet aún no tiene datos guardados: uso la lista inicial y los costos de la hoja Modelo.</div>", unsafe_allow_html=True)
if not items:
    st.warning("No hay productos con precio para simular.")
    st.stop()

claves = [(i['producto'], i['cuero']) for i in items]
etq = {k: f"{k[0]} · {k[1]}" for k in claves}
inv_etq = {v: k for k, v in etq.items()}
unid_tot = sum(i['stock'] for i in items)
inv_venta = sum(i['stock'] * i['precio'] for i in items)
inv_costo = sum(i['stock'] * i['costo'] for i in items)


# ── Guardado en la pestaña «Simulador feria» ──────────────────────
HOJA_SIM = 'Simulador feria'
NOMBRES_GASTO = ['Stand / inscripción', 'Transporte', 'Comida', 'Ayuda / Valentina', 'Publicidad y otros']
_ESC = [('% vendido', 'sim_v', int), ('Descuento %', 'sim_d', int), ('% con tarjeta', 'sim_t', int),
        ('Comisión tarjeta %', 'sim_c', float), ('Otros % de ventas', 'sim_o', float)]


def _num(x, d=0.0):
    try:
        return float(str(x).replace(',', '.'))
    except ValueError:
        return d


def _aplicar(grid):
    """Pone en session_state lo guardado en la pestaña (escenario, gastos y combos)."""
    seccion = None
    gastos, combos_g = [], []
    for f in grid:
        f = list(f) + [''] * 4
        a = str(f[0]).strip()
        if a in ('Escenario', 'Gasto', 'Combo'):
            seccion = a
            continue
        if not a:
            continue
        if seccion == 'Escenario':
            for et, k, tipo in _ESC:
                if a == et:
                    st.session_state[k] = tipo(_num(f[1]))
            if a == 'Contar todo el inventario':
                st.session_state['sim_todo'] = bool(_num(f[1], 1))
        elif seccion == 'Gasto':
            gastos.append((a, _num(f[1])))
        elif seccion == 'Combo':
            combos_g.append((a, str(f[1]), _num(f[2], 15), int(_num(f[3], 1))))
    if gastos:
        st.session_state['sim_ng'] = len(gastos)
        for n, (nom, m) in enumerate(gastos):
            st.session_state[f'sim_gn{n}'], st.session_state[f'sim_gm{n}'] = nom, m
    st.session_state['sim_ncombos'] = len(combos_g)
    for n, (nom, prods, dc, cant) in enumerate(combos_g):
        sel = []
        for parte in [x for x in prods.split(' + ') if x.strip()]:
            et, _, q = parte.rpartition('×')
            et = et.strip()
            if et in inv_etq:
                sel.append((et, int(_num(q, 1))))
        st.session_state[f'sim_cn{n}'], st.session_state[f'sim_cd{n}'], st.session_state[f'sim_cq{n}'] = nom, int(dc), cant
        st.session_state[f'sim_cs{n}'] = [e for e, _ in sel]
        for j, (_, q) in enumerate(sel):
            st.session_state[f'sim_cu{n}_{j}'] = q


def _grid_actual():
    g = [['Escenario', 'Valor']]
    g += [[et, st.session_state[k]] for et, k, _ in _ESC]
    g += [['Contar todo el inventario', 1 if st.session_state.get('sim_todo', True) else 0], [], ['Gasto', 'Monto']]
    for n in range(st.session_state['sim_ng']):
        g.append([st.session_state.get(f'sim_gn{n}', ''), st.session_state.get(f'sim_gm{n}', 0.0)])
    g += [[], ['Combo', 'Productos', 'Descuento %', 'Cantidad']]
    for n in range(st.session_state['sim_ncombos']):
        sel = st.session_state.get(f'sim_cs{n}', [])
        prods = ' + '.join(f"{e}×{st.session_state.get(f'sim_cu{n}_{j}', 1)}" for j, e in enumerate(sel))
        g.append([st.session_state.get(f'sim_cn{n}', f'Combo {n + 1}'), prods,
                  st.session_state.get(f'sim_cd{n}', 15), st.session_state.get(f'sim_cq{n}', 0)])
    return g


@st.cache_data(ttl=60, show_spinner=False)
def _leer_guardado(_sid, _v):
    try:
        return autenticar().open_by_key(_sid).worksheet(HOJA_SIM).get_all_values()
    except WorksheetNotFound:
        return []


if 'sim_init' not in st.session_state:
    st.session_state['sim_init'] = True
    for k, v in {'sim_v': 70, 'sim_d': int(round(cfg['desc_max'] * 100)), 'sim_t': 40, 'sim_c': 3.0,
                 'sim_o': 0.0, 'sim_todo': True, 'sim_ng': len(NOMBRES_GASTO), 'sim_ncombos': 0}.items():
        st.session_state.setdefault(k, v)
    for n, nom in enumerate(NOMBRES_GASTO):
        st.session_state.setdefault(f'sim_gn{n}', nom)
        st.session_state.setdefault(f'sim_gm{n}', float(cfg['otros_gastos']) if n == len(NOMBRES_GASTO) - 1 else 0.0)
    _g = _leer_guardado(SHEET_ID, st.session_state.get('sim_ver', 0))
    if _g:
        _aplicar(_g)

# ── Escenario ─────────────────────────────────────────────────────
st.markdown("<div class='sec'>Escenario</div>", unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)
vend = c1.slider("% del inventario que se vende", 0, 100, step=5, key='sim_v',
                 help="Aplica a las unidades que no van en combos.")
desc = c2.slider("Descuento general %", 0, 50, step=1, key='sim_d',
                 help="Se aplica al precio de lista de todo lo que se vende suelto.")
tarj = c3.slider("% de ventas con tarjeta", 0, 100, step=5, key='sim_t')
comi = c4.number_input("Comisión de tarjeta %", 0.0, 10.0, step=0.1, key='sim_c')

# ── Gastos administrativos ────────────────────────────────────────
st.markdown("<div class='sec'>Gastos administrativos de la feria</div>", unsafe_allow_html=True)
st.markdown("<div class='nota'>Todo lo que cuesta estar en la feria y no es producto. Pon el monto de cada concepto.</div>",
            unsafe_allow_html=True)
fijos = 0.0
for n in range(st.session_state['sim_ng']):
    g1_, g2_ = st.columns([3, 1.5])
    g1_.text_input("Concepto", key=f'sim_gn{n}', label_visibility='collapsed')
    fijos += g2_.number_input("Monto ($)", 0.0, step=5.0, key=f'sim_gm{n}', label_visibility='collapsed')
h1, h2, h3 = st.columns([1, 1, 4], vertical_alignment='center')
if h1.button("＋ Gasto", width='stretch'):
    st.session_state['sim_ng'] += 1
    st.rerun()
if h2.button("Quitar último ", width='stretch', disabled=st.session_state['sim_ng'] == 0):
    st.session_state['sim_ng'] -= 1
    st.rerun()
h3.markdown(f"<div class='nota' style='margin:0'>Total gastos fijos: <b>{money(fijos, 2)}</b></div>", unsafe_allow_html=True)
otros_pct = st.number_input("Otros gastos como % de las ventas (empaque de regalo, impuestos…)", 0.0, 30.0, step=0.5,
                            key='sim_o') / 100

# ── Combos ────────────────────────────────────────────────────────
st.markdown("<div class='sec'>Combos</div>", unsafe_allow_html=True)
st.markdown("<div class='nota'>Arma paquetes con un descuento extra, encima del descuento general. Los combos se llevan primero las unidades del inventario y "
            "el resto se vende suelto con el % de arriba.</div>", unsafe_allow_html=True)
b1, b2, _ = st.columns([1, 1, 4])
if b1.button("＋ Agregar combo", width='stretch'):
    st.session_state['sim_ncombos'] += 1
if b2.button("Quitar último", width='stretch', disabled=st.session_state['sim_ncombos'] == 0):
    st.session_state['sim_ncombos'] -= 1
combos = []
for n in range(st.session_state['sim_ncombos']):
    with st.container(border=True):
        a, b, c, d = st.columns([2.2, 2.6, 1, 1])
        st.session_state.setdefault(f'sim_cn{n}', f"Combo {n + 1}")
        nom = a.text_input("Nombre", key=f'sim_cn{n}')
        sel = [inv_etq[x] for x in b.multiselect("Productos", list(inv_etq), key=f'sim_cs{n}')]
        st.session_state.setdefault(f'sim_cd{n}', 15)
        st.session_state.setdefault(f'sim_cq{n}', 10)
        dc = c.number_input("Descuento extra del combo %", 0, 60, step=1, key=f'sim_cd{n}')
        cant = d.number_input("Combos vendidos", 0, 500, step=1, key=f'sim_cq{n}')
        partes = []
        if sel:
            cols = st.columns(min(len(sel), 4))
            for j, k in enumerate(sel):
                st.session_state.setdefault(f'sim_cu{n}_{j}', 1)
                q = cols[j % len(cols)].number_input(f"Unid. de {etq[k]}", 1, 10, step=1, key=f'sim_cu{n}_{j}')
                partes.append((k, q))
        if partes:
            _l = sum(next(i['precio'] for i in items if (i['producto'], i['cuero']) == k) * q for k, q in partes)
            _g = _l * (1 - desc / 100)
            _c = _g * (1 - dc / 100)
            st.markdown(f"<div class='nota'>Lista <b>{money(_l, 2)}</b> · con descuento general <b>{money(_g, 2)}</b> · "
                        f"combo (−{dc}% extra) <b>{money(_c, 2)}</b> · descuento total <b>{1 - (1 - desc / 100) * (1 - dc / 100):.0%}</b></div>",
                        unsafe_allow_html=True)
        combos.append({'nombre': nom, 'partes': partes, 'desc': dc / 100, 'cantidad': cant})

s1, s2, _s = st.columns([1.3, 1.3, 3.4], vertical_alignment='center')
if s1.button("Guardar simulación", type='primary', width='stretch'):
    try:
        _sh = autenticar().open_by_key(SHEET_ID)
        try:
            _ws = _sh.worksheet(HOJA_SIM)
        except WorksheetNotFound:
            _ws = _sh.add_worksheet(HOJA_SIM, rows=100, cols=6)
        _ws.clear()
        _ws.update(_grid_actual(), 'A1', value_input_option='RAW')
        _leer_guardado.clear()
        _s.success("Guardado en la pestaña «Simulador feria» del Sheet.")
    except (APIError, PermissionError) as e:
        _s.error(f"No pude guardar: {e}")
if s2.button("Recargar lo guardado", width='stretch'):
    _leer_guardado.clear()
    _g = _leer_guardado(SHEET_ID, 0)
    if _g:
        _aplicar(_g)
        st.rerun()
    _s.info("Todavía no hay nada guardado.")

# ── Resultado ─────────────────────────────────────────────────────
todo = st.toggle("Contar todo el inventario como costo, se venda o no", key='sim_todo',
                 help="Todo se compró o fabricó para la feria: lo que no se vende ya está pagado.")
kw = dict(costear_todo=todo, gastos_fijos=fijos, pct_tarjeta=tarj / 100, comision=comi / 100, otros_pct=otros_pct, combos=combos)
r = S.simular(items, vend / 100, desc / 100, **kw)
eq = S.punto_equilibrio(items, desc / 100, **kw)

st.markdown("<div class='sec'>Resultado</div>", unsafe_allow_html=True)
signo = 'pos' if r['neto'] >= 0 else 'neg'
margen_neto = r['neto'] / r['ingresos'] if r['ingresos'] else math.nan
st.markdown(f"""<div class='kpis'>
<div class='kpi'><small>Ingresos</small><div>{money(r['ingresos'])}</div><span>{r['unidades']} de {unid_tot} unidades</span></div>
<div class='kpi'><small>{'Costo de todo el inventario' if todo else 'Costo de lo vendido'}</small><div>{money(r['cogs'])}</div><span>producto + empaque + envío (envío del lote incluido)</span></div>
<div class='kpi'><small>Gastos</small><div>{money(r['gastos'])}</div><span>incluye {money(r['comisiones'])} de tarjeta</span></div>
<div class='kpi {signo}'><small>Ganancia neta</small><div>{money(r['neto'])}</div><span>margen neto {'—' if math.isnan(margen_neto) else f'{margen_neto:.0%}'}</span></div>
<div class='kpi'><small>Punto de equilibrio</small><div>{'no se cubre' if eq is None else f'{eq}%'}</div><span>del inventario vendido, con este descuento</span></div>
<div class='kpi'><small>Queda sin vender</small><div>{money(r['sin_vender'])}</div><span>a costo; {'ya está pagado arriba' if todo else 'no se resta'}</span></div>
</div>""", unsafe_allow_html=True)

LAYOUT = dict(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(family='DM Sans', color=INK),
              margin=dict(l=60, r=20, t=50, b=60), height=380)

g1, g2 = st.columns(2)
with g1:
    fig = go.Figure(go.Waterfall(
        x=['Ingresos', 'Costo inventario' if todo else 'Costo vendido', 'Gastos', 'Ganancia neta'], measure=['absolute', 'relative', 'relative', 'total'],
        y=[r['ingresos'], -r['cogs'], -r['gastos'], 0], text=[money(r['ingresos']), money(-r['cogs']), money(-r['gastos']), money(r['neto'])],
        textposition='outside', connector=dict(line=dict(color=LINE)),
        increasing=dict(marker=dict(color=VERDE)), decreasing=dict(marker=dict(color=ROJO)),
        totals=dict(marker=dict(color=ACENTO if r['neto'] >= 0 else ROJO))))
    fig.update_layout(title='De la venta a la ganancia', showlegend=False, yaxis=dict(gridcolor=LINE, tickprefix='$'), **LAYOUT)
    st.plotly_chart(fig, width='stretch', theme=None)
with g2:
    xs = list(range(0, 101, 5))
    fig = go.Figure()
    for d, col in [(0, FAINT), (desc, ACENTO), (min(desc + 10, 60), MIEL)]:
        fig.add_scatter(x=xs, y=[S.simular(items, x / 100, d / 100, **kw)['neto'] for x in xs],
                        name=f"{d}% desc." + (" (tu escenario)" if d == desc else ''), mode='lines',
                        line=dict(color=col, width=3 if d == desc else 2))
    fig.add_hline(y=0, line_color=INK, line_width=1)
    fig.add_vline(x=vend, line_dash='dot', line_color=MUTED)
    fig.update_layout(title='Ganancia neta según % vendido', xaxis=dict(title='% del inventario vendido', ticksuffix='%'),
                      yaxis=dict(gridcolor=LINE, tickprefix='$'), legend=dict(orientation='h', y=-0.25), **LAYOUT)
    st.plotly_chart(fig, width='stretch', theme=None)

# Mapa de calor: % vendido × descuento
vs = list(range(10, 101, 10))
ds = list(range(0, 41, 5))
Z = S.mapa_sensibilidad(items, [v / 100 for v in vs], [d / 100 for d in ds], **kw)
fig = go.Figure(go.Heatmap(z=Z, x=[f"{v}%" for v in vs], y=[f"{d}%" for d in ds], zmid=0,
                           colorscale=[[0, ROJO], [.5, '#f6eee3'], [1, VERDE]],
                           text=[[money(z) for z in fila] for fila in Z], texttemplate='%{text}', hovertemplate='Vendido %{x}, desc. %{y}: %{text}<extra></extra>'))
fig.update_layout(title='Ganancia neta: % vendido (→) contra descuento (↓)', xaxis_title='% del inventario vendido',
                  yaxis_title='Descuento', **{**LAYOUT, 'height': 400})
fig.update_yaxes(autorange='reversed')
st.plotly_chart(fig, width='stretch', theme=None)

# Escenarios
st.markdown("<div class='sec'>Tres escenarios</div>", unsafe_allow_html=True)
esc = []
for nom, v in [('Pesimista', .4), ('Base', vend / 100), ('Optimista', 1.0)]:
    x = S.simular(items, v, desc / 100, **kw)
    esc.append({'Escenario': nom, '% vendido': f"{v:.0%}", 'Unidades': x['unidades'], 'Ingresos': money(x['ingresos']),
                'Costo': money(x['cogs']), 'Gastos': money(x['gastos']), 'Ganancia neta': money(x['neto'])})
tabla(pd.DataFrame(esc))

# Por producto y combos
g3, g4 = st.columns(2)
with g3:
    dp = sorted(r['productos'], key=lambda d: d['ganancia'])
    fig = go.Figure(go.Bar(y=[f"{d['producto']} · {d['cuero']}" for d in dp], x=[d['ganancia'] for d in dp], orientation='h',
                           marker_color=[VERDE if d['ganancia'] >= 0 else ROJO for d in dp],
                           text=[money(d['ganancia']) for d in dp], textposition='outside'))
    fig.update_layout(title='Ganancia bruta por producto (vendido suelto)', xaxis=dict(gridcolor=LINE, tickprefix='$'),
                      **{**LAYOUT, 'height': max(360, 26 * len(dp) + 80)})
    st.plotly_chart(fig, width='stretch', theme=None)
with g4:
    st.markdown("<div class='sec' style='margin-top:.2rem'>Combos</div>", unsafe_allow_html=True)
    if r['combos']:
        tabla(pd.DataFrame([{'Combo': c['nombre'], 'Vendidos': c['vendidos'], 'Precio lista': money(c['precio_lista'], 2), 'Suelto con desc. general': money(c.get('precio_suelto', c['precio_lista']), 2),
                                    'Precio combo': money(c['precio'], 2),
                                    'Margen': '—' if math.isnan(c['margen']) else f"{c['margen']:.0%}",
                                    'Ganancia': money(c['ganancia'])} for c in r['combos']]))
        st.caption("Si un combo pide más unidades de las que hay, se limita al stock disponible.")
    else:
        st.markdown("<div class='nota'>Aún no hay combos. Agrega uno arriba para ver cuánto aportan.</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='nota'>Inventario llevado: <b>{unid_tot}</b> unidades · "
                f"valor a precio de lista <b>{money(inv_venta)}</b> · costo <b>{money(inv_costo)}</b>.</div>", unsafe_allow_html=True)
