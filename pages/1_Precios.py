"""Página de Precios y rentabilidad por producto.

Lee y escribe la hoja "MORAES_precios_ok" (pestaña Modelo). Solo escribe celdas
de entrada; las fórmulas del Sheet siguen haciendo los cálculos.
"""
import math

import pandas as pd
import streamlit as st
from gspread.exceptions import APIError, SpreadsheetNotFound
from gspread.utils import ValueRenderOption

import precios as P
from auth import autenticar
from constants import SHEET_PRECIOS_ID as _PRECIOS_DEFAULT

st.set_page_config(page_title="MORAES · Precios", page_icon="💲", layout="wide")

SHEET_PRECIOS_ID = st.secrets.get('sheet_precios_id') or _PRECIOS_DEFAULT
URL_SHEET = f"https://docs.google.com/spreadsheets/d/{SHEET_PRECIOS_ID}/edit"

SURFACE, CARD_BG, CARD_BORDER = '#1a1210', '#211815', '#3a2820'
TEXT_MAIN, TEXT_MUTED, AMBER = '#f5ede8', '#a08070', '#944925'
GREEN, RED, GOLD = '#4ade80', '#f87171', '#D9A441'

# Umbrales de color para márgenes (supuesto, ajustable)
MARGEN_BAJO = 0.20
MARGEN_OK = 0.35

st.markdown(f"""
<style>
  .stApp {{ background-color: {SURFACE}; color: {TEXT_MAIN}; }}
  .p-card {{ background:{CARD_BG}; border:1px solid {CARD_BORDER}; border-radius:12px; padding:16px 18px; }}
  .p-label {{ font-size:.7rem; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:{TEXT_MUTED}; }}
  .p-value {{ font-size:1.5rem; font-weight:700; }}
  .p-sub {{ font-size:.75rem; color:{TEXT_MUTED}; }}
</style>
""", unsafe_allow_html=True)


# ── Conexión con el Sheet ─────────────────────────────────────────

def _hoja():
    gc = autenticar()
    return gc, gc.open_by_key(SHEET_PRECIOS_ID).worksheet(P.HOJA)


def _leer_grids(ws):
    rango = f"A1:X{ws.row_count}"
    valores = ws.get(rango, value_render_option=ValueRenderOption.unformatted)
    formulas = ws.get(rango, value_render_option=ValueRenderOption.formula)
    return list(valores), list(formulas)


def _email_service_account(gc):
    try:
        return gc.http_client.auth.service_account_email
    except Exception:
        return None


def cargar():
    gc = None
    try:
        gc, ws = _hoja()
        valores, formulas = _leer_grids(ws)
    except (APIError, SpreadsheetNotFound, PermissionError) as e:
        email = _email_service_account(gc) if gc else None
        st.error(
            "No pude abrir la hoja de precios. Lo más probable es que no esté compartida "
            f"con la cuenta del dashboard{f' (**{email}**)' if email else ''}. "
            f"Compártela como *Editor* desde [la hoja]({URL_SHEET}) y recarga.\n\n`{e}`"
        )
        st.stop()
    params, prod = P.parsear(valores, formulas)
    st.session_state['precios_orig'] = (params, prod)
    st.session_state['precios_version'] = st.session_state.get('precios_version', 0) + 1


if 'precios_orig' not in st.session_state:
    with st.spinner("Leyendo hoja de precios…"):
        cargar()

params_orig, prod_orig = st.session_state['precios_orig']
ver = st.session_state['precios_version']


# ── Encabezado ────────────────────────────────────────────────────
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown("## 💲 Precios y rentabilidad por producto")
    st.caption(f"Conectado a la hoja [MORAES_precios_ok]({URL_SHEET}). "
               "Los cambios no se guardan hasta que presionas **Actualizar en Sheets**.")
with c2:
    st.page_link("app.py", label="← Volver al dashboard")
    if st.button("🔄 Recargar desde Sheets", width='stretch',
                 help="Descarta cambios sin guardar y vuelve a leer la hoja."):
        for k in [k for k in st.session_state if k.startswith('ed_')]:
            del st.session_state[k]
        cargar()
        st.rerun()


# ── Editores (pestaña Editar) se leen primero para alimentar la vista previa ──
tab_ver, tab_editar = st.tabs(["📊 Rentabilidad", "✏️ Editar precios y costos"])

with tab_editar:
    st.markdown("#### Parámetros generales")
    st.caption("Afectan a todos los productos. Los % están en tanto por uno (0.50 = 50%).")
    params_ed = st.data_editor(
        params_orig[['Celda', 'Parámetro', 'Valor']],
        key=f'ed_params_{ver}',
        hide_index=True,
        width='stretch',
        disabled=['Celda', 'Parámetro'],
        column_config={
            'Celda': st.column_config.TextColumn(width='small'),
            'Valor': st.column_config.NumberColumn(format='%.4g', required=True),
        },
    )

    st.markdown("#### Costos y precio por producto")
    st.caption("🔒 = esa celda tiene fórmula en el Sheet (p. ej. empaque = parámetro general). "
               "Si la cambias aquí no se guardará; cámbiala en el parámetro o en el Sheet.")
    _vista_ed = prod_orig[['Fila', 'Producto', 'Cuero', 'Costo proveedor', 'Empaque',
                           'Unid/caja', 'Precio retail']].copy()
    _vista_ed['🔒'] = prod_orig.apply(
        lambda r: ', '.join(n for l, n in P.ENTRADAS.items() if r[f'_f_{l}']), axis=1)
    prod_ed = st.data_editor(
        _vista_ed,
        key=f'ed_prod_{ver}',
        hide_index=True,
        width='stretch',
        height=min(38 * (len(_vista_ed) + 1), 600),
        disabled=['Fila', 'Producto', 'Cuero', '🔒'],
        column_config={
            'Fila': st.column_config.NumberColumn(width='small', help='Fila en el Sheet'),
            'Costo proveedor': st.column_config.NumberColumn('Costo prov. (USD @ tasa base)', format='$%.2f', min_value=0),
            'Empaque': st.column_config.NumberColumn(format='$%.2f', min_value=0),
            'Unid/caja': st.column_config.NumberColumn(format='%d', min_value=1, step=1),
            'Precio retail': st.column_config.NumberColumn(format='$%.0f', min_value=0),
        },
    )

# Aplicar ediciones a copias de los originales
params_nuevo = params_orig.copy()
params_nuevo['Valor'] = params_ed['Valor'].values
prod_nuevo = prod_orig.copy()
for col in P.ENTRADAS.values():
    prod_nuevo[col] = pd.to_numeric(prod_ed[col], errors='coerce').values

cambios = P.cambios_pendientes(params_orig, params_nuevo, prod_orig, prod_nuevo)
df = P.calcular(params_nuevo, prod_nuevo)
p = dict(zip(params_nuevo['Celda'], params_nuevo['Valor']))


# ── Pestaña Rentabilidad ──────────────────────────────────────────
def _pct(x):
    return '—' if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.0%}"


def _color_margen(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ''
    if v < MARGEN_BAJO:
        return f'color:{RED};font-weight:600'
    if v < MARGEN_OK:
        return f'color:{GOLD}'
    return f'color:{GREEN}'


with tab_ver:
    if cambios:
        st.info(f"Vista previa con **{len(cambios)} cambio(s) sin guardar**. "
                "Ve a *Editar* para guardarlos o descartarlos.")

    validos = df.dropna(subset=['Precio retail', 'Costo variable'])
    peor = validos.loc[validos['Margen WS 50–99 %'].idxmin()] if not validos.empty else None
    k1, k2, k3, k4 = st.columns(4)
    for col, label, valor, sub in [
        (k1, 'Productos × cuero', f"{len(validos)}", f"{validos['Producto'].nunique()} productos"),
        (k2, 'Margen retail promedio', _pct(validos['Margen retail %'].mean()), 'precio retail vs costo variable'),
        (k3, 'Margen WS 6–24 promedio', _pct(validos['Margen WS 6–24 %'].mean()), f"wholesale al {p['B10']:.0%} del retail"),
        (k4, 'Peor margen WS 50–99',
         _pct(peor['Margen WS 50–99 %']) if peor is not None else '—',
         f"{peor['Producto']} · {peor['Cuero']}" if peor is not None else ''),
    ]:
        col.markdown(f"<div class='p-card'><div class='p-label'>{label}</div>"
                     f"<div class='p-value'>{valor}</div><div class='p-sub'>{sub}</div></div>",
                     unsafe_allow_html=True)

    st.markdown("")
    f1, f2 = st.columns([2, 1])
    with f1:
        sel = st.multiselect("Filtrar productos", sorted(df['Producto'].unique()), placeholder="Todos")
    with f2:
        cueros = st.multiselect("Cuero", list(df['Cuero'].unique()), placeholder="Todos")
    vista = df
    if sel:
        vista = vista[vista['Producto'].isin(sel)]
    if cueros:
        vista = vista[vista['Cuero'].isin(cueros)]

    st.markdown("#### Retail y wholesale")
    st.caption(f"Colores de margen: rojo < {MARGEN_BAJO:.0%}, dorado < {MARGEN_OK:.0%}, verde ≥ {MARGEN_OK:.0%}. "
               f"Tasa actual {p['B5']:,.0f} COP/USD vs base {p['B4']:,.0f}.")
    cols_ws = ['Producto', 'Cuero', 'Costo variable', 'Precio retail', 'Margen retail %',
               'WS 6–24', 'Margen WS 6–24 %', 'WS 25–49', 'Margen WS 25–49 %',
               'WS 50–99', 'Margen WS 50–99 %', 'Retail ideal (4× costo)', 'Und/mes para cubrir fijos']
    margenes = [c for c in cols_ws if c.endswith('%')]
    dinero = ['Costo variable', 'Precio retail', 'WS 6–24', 'WS 25–49', 'WS 50–99', 'Retail ideal (4× costo)']
    st.dataframe(
        vista[cols_ws].style
        .format({**{c: '${:,.2f}' for c in ['Costo variable']},
                 **{c: '${:,.0f}' for c in dinero if c != 'Costo variable'},
                 **{c: '{:.0%}' for c in margenes},
                 'Und/mes para cubrir fijos': '{:,.0f}'}, na_rep='—')
        .map(_color_margen, subset=margenes),
        hide_index=True, width='stretch',
        height=min(36 * (len(vista) + 1), 640),
    )

    with st.expander("Precios corporativos y desglose de costo"):
        cols_corp = ['Producto', 'Cuero', 'Costo proveedor', 'Costo + FX', 'Empaque', 'Flete/und',
                     'Costo variable', 'Precio retail', 'Corp 12–30', 'Corp 31–60', 'Corp 61–99', 'Corp 100–200']
        st.dataframe(
            vista[cols_corp].style.format(
                {c: '${:,.2f}' for c in cols_corp[2:7]} | {c: '${:,.0f}' for c in cols_corp[7:]}, na_rep='—'),
            hide_index=True, width='stretch',
        )
        st.caption(f"Costo variable = costo prov. × (tasa base ÷ tasa actual) + empaque + flete/caja ÷ unid/caja "
                   f"+ arancel (${p['B9']:.2f}). 'Und/mes para cubrir fijos' = fijos mensuales "
                   f"(${p['B16']:,.0f}) ÷ ganancia por unidad a precio WS 6–24.")


# ── Guardar (pestaña Editar) ──────────────────────────────────────
with tab_editar:
    st.markdown("#### Cambios pendientes")
    if not cambios:
        st.caption("No hay cambios. Edita una celda arriba para ver aquí lo que se va a guardar.")
    else:
        tabla = pd.DataFrame([{
            'Celda': c['celda'], 'Qué': c['que'],
            'Antes': c['antes'], 'Después': c['despues'],
            'Se guarda': '🔒 No (fórmula)' if c['bloqueada'] else '✅ Sí',
        } for c in cambios])
        st.dataframe(tabla, hide_index=True, width='stretch')

        escribibles = P.payload_escritura(cambios)
        clave = st.secrets.get('clave_precios')
        autorizado = True
        if clave:
            autorizado = st.text_input("Clave para guardar", type="password") == clave
        else:
            st.warning("Sin clave configurada: cualquiera con el link del dashboard puede guardar precios. "
                       "Agrega `clave_precios` en los secrets de Streamlit para protegerlo.")

        b1, b2 = st.columns([1, 1])
        with b1:
            guardar = st.button(f"💾 Actualizar en Sheets ({len(escribibles)} celda(s))", type="primary",
                                disabled=not escribibles or not autorizado, width='stretch')
        with b2:
            if st.button("Descartar cambios", width='stretch'):
                st.session_state['precios_version'] += 1
                st.rerun()

        if guardar:
            try:
                _, ws = _hoja()
                # Chequeo de conflicto: ¿alguien cambió esas celdas en el Sheet desde que se cargó?
                valores_ahora, formulas_ahora = _leer_grids(ws)
                conflictos = []
                for c in cambios:
                    if c['bloqueada']:
                        continue
                    fila, col = P.celda_a_rc(c['celda'])
                    actual = P._get(formulas_ahora, fila, col)
                    if P.es_formula(actual):
                        conflictos.append(f"{c['celda']} ahora tiene fórmula")
                    elif P._distinto(P.a_numero(P._get(valores_ahora, fila, col)), c['antes']):
                        conflictos.append(f"{c['celda']} cambió en el Sheet")
                if conflictos:
                    st.error("No guardé nada porque la hoja cambió mientras editabas: "
                             + "; ".join(conflictos) + ". Presiona *Recargar desde Sheets* y vuelve a editar.")
                else:
                    datos = [{'range': d['range'], 'values': [[float(v) if v != '' else '' for v in d['values'][0]]]}
                             for d in escribibles]
                    ws.batch_update(datos, value_input_option='RAW')
                    for k in [k for k in st.session_state if k.startswith('ed_')]:
                        del st.session_state[k]
                    cargar()
                    st.session_state['precios_guardado'] = len(datos)
                    st.rerun()
            except APIError as e:
                st.error(f"Google Sheets rechazó la escritura (¿la cuenta del dashboard tiene permiso de Editor?): `{e}`")

if st.session_state.pop('precios_guardado', None):
    st.toast("✅ Hoja de precios actualizada. Los cálculos ya vienen del Sheet.")
