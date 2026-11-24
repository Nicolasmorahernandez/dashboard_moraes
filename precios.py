"""Lógica de la página de Precios (hoja MORAES_precios_ok, pestaña "Modelo").

Separado de la UI para poder probarlo sin Streamlit ni Google Sheets.

Reglas:
- Solo se escriben celdas de ENTRADA (parámetros y columnas C, E, F, J de
  productos). Nunca se escribe una celda que en el Sheet tenga fórmula.
- Los cálculos (costo variable, márgenes, wholesale, corporativo…) los hace
  el propio Sheet. Aquí se replican solo para la vista previa mientras se edita.
"""
import math
import re

import pandas as pd

HOJA = 'Modelo'
FILA_CABECERA = 18          # fila con "Producto | Cuero | ..."
FILA_INICIO = 19            # primera fila de producto

# Parámetros editables: celda -> etiqueta (la etiqueta real se lee del Sheet
# cuando existe; esta es la de respaldo).
PARAMETROS = {
    'B4':  'Tasa BASE / ideal (COP por USD)',
    'B5':  'Tasa de COTIZACIÓN actual (COP/USD)',
    'B7':  'Empaque por unidad ($)',
    'B8':  'Flete por caja ($)',
    'B9':  'Arancel / importación por unidad ($)',
    'B10': 'Wholesale 6–24 (% del precio)',
    'B11': 'Wholesale 25–49 (% del precio)',
    'B12': 'Wholesale 50–99 (% del precio)',
    'B13': 'Corporativo 12–30 (% del precio)',
    'B14': 'Corporativo 31–60 (% del precio)',
    'B15': 'Corporativo 61–99 (% del precio)',
    'E15': 'Corporativo 100–200 (% del precio)',
    'B16': 'Sueldo + fijos mensuales objetivo ($)',
    'E5':  'Multiplicador cuero · Vaqueta',
    'E6':  'Multiplicador cuero · Napa',
    'E7':  'Multiplicador cuero · Crazy Horse',
    'E8':  'Multiplicador cuero · Hampton',
}
PARAMS_PORCENTAJE = {'B10', 'B11', 'B12', 'B13', 'B14', 'B15', 'E15'}

# Columnas de entrada por producto: letra -> nombre en la app
ENTRADAS = {
    'C': 'Costo proveedor',
    'E': 'Empaque',
    'F': 'Unid/caja',
    'J': 'Precio retail',
}

LETRAS = 'ABCDEFGHIJKLMNOPQRSTUVWX'


def col_idx(letra):
    return LETRAS.index(letra)


def celda_a_rc(celda):
    """'B10' -> (fila 10, índice de columna 1)."""
    m = re.fullmatch(r'([A-Z])(\d+)', celda)
    return int(m.group(2)), col_idx(m.group(1))


def _get(grid, fila, col):
    """grid: lista de filas (1-indexed por fila en el Sheet). Devuelve '' si no hay."""
    i = fila - 1
    if i < 0 or i >= len(grid):
        return ''
    r = grid[i]
    return r[col] if col < len(r) else ''


def es_formula(v):
    return isinstance(v, str) and v.startswith('=')


def a_numero(v):
    if v is None or v == '':
        return math.nan
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace('$', '').replace(',', '')
    pct = s.endswith('%')
    s = s.rstrip('%')
    try:
        n = float(s)
    except ValueError:
        return math.nan
    return n / 100 if pct else n


def redondear(x):
    """ROUND() de Google Sheets: mitad hacia afuera (Python redondea al par)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return math.nan
    return math.floor(abs(x) + 0.5) * (1 if x >= 0 else -1)


# ── Lectura ───────────────────────────────────────────────────────

def parsear(valores, formulas):
    """valores: grid UNFORMATTED_VALUE; formulas: grid FORMULA (mismo rango A1:X).

    Devuelve (df_params, df_productos). Cada df guarda, por cada entrada, si la
    celda del Sheet es fórmula (no editable) y su valor original, para poder
    calcular qué cambió.
    """
    params = []
    for celda, etiqueta_def in PARAMETROS.items():
        fila, col = celda_a_rc(celda)
        etiqueta = str(_get(valores, fila, col - 1) or '').strip()
        if celda.startswith('E') and celda != 'E15':
            etiqueta = f"Multiplicador cuero · {etiqueta}" if etiqueta else etiqueta_def
        if not etiqueta:
            etiqueta = etiqueta_def
        params.append({
            'Celda': celda,
            'Parámetro': etiqueta.split(' — ')[0],
            'Valor': a_numero(_get(valores, fila, col)),
            'formula': es_formula(_get(formulas, fila, col)),
            'pct': celda in PARAMS_PORCENTAJE,
        })
    df_params = pd.DataFrame(params)

    filas = []
    producto = ''
    for fila in range(FILA_INICIO, len(valores) + 1):
        nombre = str(_get(valores, fila, 0) or '').strip()
        cuero = str(_get(valores, fila, 1) or '').strip()
        if nombre:
            producto = nombre
        if not cuero:
            continue          # fila vacía / separador
        reg = {'Fila': fila, 'Producto': producto, 'Cuero': cuero}
        for letra, nombre_col in ENTRADAS.items():
            c = col_idx(letra)
            reg[nombre_col] = a_numero(_get(valores, fila, c))
            reg[f'_f_{letra}'] = _get(formulas, fila, c) if es_formula(_get(formulas, fila, c)) else ''
        filas.append(reg)
    df_prod = pd.DataFrame(filas)
    return df_params, df_prod


# ── Vista previa de cálculos (replica fórmulas del Sheet) ─────────

def _resolver_formula_entrada(formula, p, df, fila_actual):
    """Soporta las fórmulas de entrada que existen hoy en el Sheet:
    '=$B$7' (empaque global) y '=J51*E6' (precio = precio base × multiplicador).
    Devuelve None si no la reconoce (se usa el valor leído del Sheet)."""
    f = formula.replace('$', '').upper()
    m = re.fullmatch(r'=([BE]\d+)', f)
    if m and m.group(1) in p:
        return p[m.group(1)]
    m = re.fullmatch(r'=J(\d+)\*([BE]\d+)', f)
    if m and m.group(2) in p:
        base = df.loc[df['Fila'] == int(m.group(1)), 'Precio retail']
        if not base.empty:
            return base.iloc[0] * p[m.group(2)]
    return None


def calcular(df_params, df_prod):
    """Devuelve df con todas las columnas calculadas, igual que el Sheet."""
    p = dict(zip(df_params['Celda'], df_params['Valor']))
    df = df_prod.copy()

    # Re-resolver entradas que son fórmula (p. ej. si cambió el empaque global)
    for letra, nombre_col in ENTRADAS.items():
        fcol = f'_f_{letra}'
        for i, f in df[fcol].items():
            if f:
                v = _resolver_formula_entrada(f, p, df, df.at[i, 'Fila'])
                if v is not None:
                    df.at[i, nombre_col] = v

    fx = p['B4'] / p['B5'] if p.get('B5') else math.nan
    df['Costo + FX'] = df['Costo proveedor'] * fx
    df['Flete/und'] = p['B8'] / df['Unid/caja'].replace(0, math.nan)
    df['Costo variable'] = df['Costo + FX'] + df['Empaque'] + df['Flete/und'] + p['B9']

    precio = df['Precio retail']
    costo = df['Costo variable']

    def margen(pv):
        return (pv - costo) / pv.replace(0, math.nan)

    df['Margen retail %'] = margen(precio)
    for nombre, celda in [('WS 6–24', 'B10'), ('WS 25–49', 'B11'), ('WS 50–99', 'B12')]:
        df[nombre] = (precio * p[celda]).map(redondear)
        df[f'Margen {nombre} %'] = margen(df[nombre])
    for nombre, celda in [('Corp 12–30', 'B13'), ('Corp 31–60', 'B14'),
                          ('Corp 61–99', 'B15'), ('Corp 100–200', 'E15')]:
        df[nombre] = (precio * p[celda]).map(redondear)
        df[f'Margen {nombre} %'] = margen(df[nombre])
    df['Retail ideal (4× costo)'] = (costo * 4).map(redondear)
    ganancia_ws = df['WS 6–24'] - costo
    df['Und/mes para cubrir fijos'] = (p['B16'] / ganancia_ws).where(ganancia_ws > 0)
    return df


# ── Escritura ─────────────────────────────────────────────────────

def _distinto(a, b):
    a_nan = a is None or (isinstance(a, float) and math.isnan(a))
    b_nan = b is None or (isinstance(b, float) and math.isnan(b))
    if a_nan and b_nan:
        return False
    if a_nan != b_nan:
        return True
    return abs(float(a) - float(b)) > 1e-9


def cambios_pendientes(params_orig, params_nuevo, prod_orig, prod_nuevo):
    """Lista de dicts {celda, que, antes, despues, bloqueada}.
    `bloqueada` = la celda tiene fórmula en el Sheet y no se va a escribir."""
    cambios = []
    po = params_orig.set_index('Celda')
    for _, r in params_nuevo.iterrows():
        antes = po.at[r['Celda'], 'Valor']
        if _distinto(antes, r['Valor']):
            cambios.append({
                'celda': r['Celda'], 'que': r['Parámetro'],
                'antes': antes, 'despues': r['Valor'],
                'bloqueada': bool(po.at[r['Celda'], 'formula']),
            })
    pr = prod_orig.set_index('Fila')
    for _, r in prod_nuevo.iterrows():
        fila = r['Fila']
        for letra, nombre_col in ENTRADAS.items():
            antes = pr.at[fila, nombre_col]
            if _distinto(antes, r[nombre_col]):
                cambios.append({
                    'celda': f'{letra}{fila}',
                    'que': f"{r['Producto']} · {r['Cuero']} · {nombre_col}",
                    'antes': antes, 'despues': r[nombre_col],
                    'bloqueada': bool(pr.at[fila, f'_f_{letra}']),
                })
    return cambios


def payload_escritura(cambios):
    """Formato de gspread Worksheet.batch_update. Celdas vacías se envían como ''."""
    datos = []
    for c in cambios:
        if c['bloqueada']:
            continue
        v = c['despues']
        if v is None or (isinstance(v, float) and math.isnan(v)):
            v = ''
        datos.append({'range': c['celda'], 'values': [[v]]})
    return datos


# ── Empaque por producto ──────────────────────────────────────────
# Cada producto (todas sus filas de cuero) usa uno de tres modos en la
# columna E de "Modelo":
#   'default'     → =$B$7 (empaque general de Ajustes)
#   'manual'      → un número escrito a mano
#   'componentes' → =SUMIF(Empaque!A:A,"<producto>",Empaque!C:C), con el detalle
#                   (bolsa, logo, caja…) en la pestaña "Empaque".
# 'otra' = cualquier otra fórmula: no se toca.

HOJA_EMPAQUE = 'Empaque'
CABECERA_EMPAQUE = ['Producto', 'Concepto', 'Valor (USD)']
CONCEPTOS_SUGERIDOS = ['Bolsa', 'Logo', 'Caja']


def formula_default():
    return '=$B$7'


def formula_componentes(producto):
    nombre = producto.replace('"', '""')
    return f'=SUMIF({HOJA_EMPAQUE}!$A:$A,"{nombre}",{HOJA_EMPAQUE}!$C:$C)'


def modo_empaque(formula):
    """formula = texto de la celda E en modo FORMULA ('' si es un número)."""
    if not formula:
        return 'manual'
    f = formula.replace('$', '').replace(' ', '').upper()
    if f == '=B7':
        return 'default'
    if f.startswith('=SUMIF(') and HOJA_EMPAQUE.upper() in f:
        return 'componentes'
    return 'otra'


def parsear_empaque(grid):
    """Pestaña Empaque → {producto: [(concepto, valor), ...]}. Ignora la cabecera."""
    out = {}
    for fila in grid[1:]:
        fila = list(fila) + ['', '', '']
        prod, concepto, valor = str(fila[0]).strip(), str(fila[1]).strip(), a_numero(fila[2])
        if not prod or (not concepto and math.isnan(valor)):
            continue
        out.setdefault(prod, []).append((concepto, 0.0 if math.isnan(valor) else valor))
    return out


def grid_empaque(componentes):
    """{producto: [(concepto, valor)]} → filas para escribir en la pestaña."""
    filas = [CABECERA_EMPAQUE]
    for prod, items in componentes.items():
        for concepto, valor in items:
            filas.append([prod, concepto, float(valor)])
    return filas


def estado_empaque(df_prod, componentes):
    """{producto: {'modo', 'total', 'items'}} a partir de lo leído del Sheet.
    El modo de un producto es el de su primera fila; si sus filas tienen modos
    distintos, se marca 'mixto' y se trata como 'otra' (no editable)."""
    out = {}
    for prod, g in df_prod.groupby('Producto', sort=False):
        modos = {modo_empaque(f) for f in g['_f_E']}
        modo = modos.pop() if len(modos) == 1 else 'mixto'
        total = g['Empaque'].iloc[0]
        if modo == 'manual' and g['Empaque'].nunique(dropna=False) > 1:
            modo = 'mixto'
        out[prod] = {'modo': modo, 'total': total, 'items': list(componentes.get(prod, []))}
    return out


def empaque_efectivo(estado, b7):
    """Valor por unidad que usa la vista previa."""
    if estado['modo'] == 'default':
        return b7
    if estado['modo'] == 'componentes':
        return sum(v for _, v in estado['items'])
    return estado['total']


def valor_celda_empaque(producto, estado):
    """Lo que se escribe en E (USER_ENTERED)."""
    if estado['modo'] == 'default':
        return formula_default()
    if estado['modo'] == 'componentes':
        return formula_componentes(producto)
    return float(estado['total'])


# ── Productos fabricados en el taller ─────────────────────────────
# Un producto es "fabricado" si tiene filas en la pestaña Fabricación.
# Su costo (columna C, por cuero) lo calcula la app y lo escribe como número:
#   (pie² × precio del cuero × (1 + desperdicio) + Σ cantidad × precio material
#    + minutos/60 × valor hora) × (1 + % taller)
# Los precios viven en la pestaña Materiales.

HOJA_MATERIALES = 'Materiales'
CAB_MATERIALES = ['Material', 'Unidad', 'Precio (USD)']
VALOR_HORA = 'Valor hora (mano de obra)'
CUEROS = ['Vaqueta', 'Napa', 'Crazy Horse', 'Hampton']
MATERIALES_BASE = ([(f'Cuero {c}', 'pie²', 0.0) for c in CUEROS]
                   + [(VALOR_HORA, 'hora', 0.0), ('Hilo', 'm', 0.0), ('Herraje', 'und', 0.0),
                      ('Forro', 'pie²', 0.0), ('Pegante', 'und', 0.0), ('Tinta de cantos', 'und', 0.0)])

HOJA_FAB = 'Fabricación'
CAB_FAB = ['Producto', 'Campo', 'Concepto', 'Cantidad']
FAB_CAMPOS = ('pies2', 'desperdicio', 'minutos', 'taller')
FAB_DEFAULT = {'pies2': 0.0, 'desperdicio': 0.20, 'minutos': 0.0, 'taller': 0.05, 'items': []}  # % supuestos


def nombre_cuero(cuero):
    return f'Cuero {cuero}'


def parsear_materiales(grid):
    out = []
    for fila in (grid or [])[1:]:
        fila = list(fila) + ['', '', '']
        nombre = str(fila[0]).strip()
        if not nombre:
            continue
        precio = a_numero(fila[2])
        out.append((nombre, str(fila[1]).strip(), 0.0 if math.isnan(precio) else precio))
    return out


def grid_materiales(materiales):
    return [CAB_MATERIALES] + [[n, u, float(p)] for n, u, p in materiales]


def parsear_fab(grid):
    out = {}
    for fila in (grid or [])[1:]:
        fila = list(fila) + ['', '', '', '']
        prod, campo, concepto = str(fila[0]).strip(), str(fila[1]).strip().lower(), str(fila[2]).strip()
        cant = a_numero(fila[3])
        cant = 0.0 if math.isnan(cant) else cant
        if not prod or not campo:
            continue
        bom = out.setdefault(prod, {**FAB_DEFAULT, 'items': []})
        if campo in FAB_CAMPOS:
            bom[campo] = cant
        elif campo == 'material' and concepto:
            bom['items'].append((concepto, cant))
    return out


def grid_fab(fab):
    filas = [CAB_FAB]
    for prod, bom in fab.items():
        for campo in FAB_CAMPOS:
            filas.append([prod, campo, '', float(bom[campo])])
        for concepto, cant in bom['items']:
            filas.append([prod, 'material', concepto, float(cant)])
    return filas


def costo_fabricado(bom, cuero, precios):
    """precios: {material: precio}. Devuelve dict con el desglose y 'total'."""
    p_cuero = precios.get(nombre_cuero(cuero), 0.0)
    cuero_usd = bom['pies2'] * p_cuero * (1 + bom['desperdicio'])
    mats = [(c, q, precios.get(c, 0.0), q * precios.get(c, 0.0)) for c, q in bom['items']]
    materiales = sum(m[3] for m in mats)
    mano = bom['minutos'] / 60 * precios.get(VALOR_HORA, 0.0)
    base = cuero_usd + materiales + mano
    taller = base * bom['taller']
    return {'cuero': cuero_usd, 'precio_cuero': p_cuero, 'materiales': materiales, 'detalle_mat': mats,
            'mano': mano, 'valor_hora': precios.get(VALOR_HORA, 0.0), 'taller': taller,
            'total': base + taller}
