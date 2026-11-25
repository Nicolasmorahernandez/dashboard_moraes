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

# Precios por volumen: nombre -> (columna del Sheet, celda del % de Ajustes).
# Normalmente son fórmula (=ROUND(J×%)). Si el Sheet tiene un número escrito a mano en la celda,
# ese número es un precio fijo del producto (override) y manda sobre el %.
NIVELES = {
    'WS 6–24': ('L', 'B10'), 'WS 25–49': ('N', 'B11'), 'WS 50–99': ('P', 'B12'),
    'Corp 12–30': ('S', 'B13'), 'Corp 31–60': ('T', 'B14'), 'Corp 61–99': ('U', 'B15'),
    'Corp 100–200': ('V', 'E15'),
}
NIVEL_POR_LETRA = {l: n for n, (l, _) in NIVELES.items()}


def col_o(nombre):
    """Columna del df con el precio fijo (NaN = sigue la fórmula)."""
    return f'_o_{nombre}'


def formula_nivel(nombre, fila):
    letra, celda = NIVELES[nombre]
    return f'=ROUND(J{fila}*${celda[0]}${celda[1:]})'


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
        for nombre, (letra, _) in NIVELES.items():
            c = col_idx(letra)
            crudo = _get(formulas, fila, c)
            reg[col_o(nombre)] = math.nan if es_formula(crudo) else a_numero(_get(valores, fila, c))
            reg[f'_g_{nombre}'] = crudo if es_formula(crudo) else ''
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
    for nombre, (_, celda) in NIVELES.items():
        df[nombre] = (precio * p[celda]).map(redondear)
        if col_o(nombre) in df:
            df[nombre] = df[col_o(nombre)].where(df[col_o(nombre)].notna(), df[nombre])
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
                # El precio retail se puede escribir aunque tenga fórmula: la reemplaza por el número.
                reemplaza = letra == 'J' and bool(pr.at[fila, '_f_J'])
                cambios.append({
                    'celda': f'{letra}{fila}',
                    'que': f"{r['Producto']} · {r['Cuero']} · {nombre_col}",
                    'antes': antes, 'despues': r[nombre_col],
                    'bloqueada': bool(pr.at[fila, f'_f_{letra}']) and not reemplaza,
                    **({'reemplaza': True, 'f_antes': pr.at[fila, '_f_J']} if reemplaza else {}),
                })
        for nombre, (letra, _) in NIVELES.items():
            if col_o(nombre) not in pr.columns:
                continue
            antes, despues = pr.at[fila, col_o(nombre)], r[col_o(nombre)]
            if _distinto(antes, despues):
                cambios.append({
                    'celda': f'{letra}{fila}',
                    'que': f"{r['Producto']} · {r['Cuero']} · {nombre}",
                    'antes': antes, 'despues': despues, 'bloqueada': False, 'volumen': nombre,
                    'f_antes': pr.at[fila, f'_g_{nombre}'],
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
            v = formula_nivel(c['volumen'], int(c['celda'][1:])) if c.get('volumen') else ''
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
#   (dm² × precio del cuero × (1 + desperdicio) + Σ cantidad × precio material
#    + minutos/60 × valor hora) × (1 + % taller)
# Los precios viven en la pestaña Materiales, en COP (cuero por dm², mano de obra por hora). El costo en USD
# se saca con la tasa BASE (B4), igual que el costo proveedor: el Sheet suma el ajuste cambiario encima.
DM2_POR_PIE2 = 9.2903

HOJA_MATERIALES = 'Materiales'
CAB_MATERIALES = ['Material', 'Unidad', 'Precio (COP)']
UNIDADES = ['und', 'm', 'dm²', 'hora']
VALOR_HORA = 'Valor hora (mano de obra)'
CUEROS = ['Vaqueta', 'Napa', 'Crazy Horse', 'Hampton']
MATERIALES_BASE = ([(f'Cuero {c}', 'dm²', 0.0) for c in CUEROS]
                   + [(VALOR_HORA, 'hora', 0.0), ('Hilo', 'm', 0.0), ('Herraje', 'und', 0.0),
                      ('Ojales', 'und', 0.0), ('Cordón elástico', 'm', 0.0),
                      ('Forro', 'dm²', 0.0), ('Pegante', 'und', 0.0), ('Tinta de cantos', 'und', 0.0)])

HOJA_FAB = 'Fabricación'
CAB_FAB = ['Producto', 'Campo', 'Concepto', 'Cantidad']
FAB_CAMPOS = ('dm2', 'desperdicio', 'minutos', 'taller')
FAB_DEFAULT = {'dm2': 0.0, 'desperdicio': 0.20, 'minutos': 0.0, 'taller': 0.05, 'items': []}  # % supuestos


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
        elif campo == 'pies2':          # versión anterior: pie² → dm²
            bom['dm2'] = cant * DM2_POR_PIE2
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


def costo_fabricado(bom, cuero, precios, tasa_base):
    """precios: {material: precio en COP}. Devuelve el desglose en USD a la tasa base ('total' incluido);
    'precio_cuero' y 'valor_hora' quedan en COP y cada material trae su precio COP."""
    k = 1 / tasa_base if tasa_base else math.nan
    p_cuero = precios.get(nombre_cuero(cuero), 0.0)
    cuero_usd = bom['dm2'] * p_cuero * (1 + bom['desperdicio']) * k
    mats = [(c, q, precios.get(c, 0.0), q * precios.get(c, 0.0) * k) for c, q in bom['items']]
    materiales = sum(m[3] for m in mats)
    mano = bom['minutos'] / 60 * precios.get(VALOR_HORA, 0.0) * k
    base = cuero_usd + materiales + mano
    taller = base * bom['taller']
    return {'cuero': cuero_usd, 'precio_cuero': p_cuero, 'materiales': materiales, 'detalle_mat': mats,
            'mano': mano, 'valor_hora': precios.get(VALOR_HORA, 0.0), 'taller': taller,
            'total': base + taller}


# ── Productos nuevos ──────────────────────────────────────────────
# Se agregan como filas nuevas al final de la tabla, una por cuero, con las
# mismas fórmulas que las filas existentes. El nombre va solo en la primera.

MULT_CUERO = {'Vaqueta': 'E5', 'Napa': 'E6', 'Crazy Horse': 'E7', 'Hampton': 'E8'}


def ultima_fila_ocupada(valores):
    """Última fila (1-indexed) con algo escrito en A:X, desde la cabecera."""
    ultima = FILA_CABECERA
    for i in range(FILA_CABECERA, len(valores)):
        if any(str(x).strip() for x in valores[i][:len(LETRAS)]):
            ultima = i + 1
    return ultima


def formula_precio_por_multiplicador(fila_base, cuero):
    """Precio = precio del primer cuero × multiplicador del cuero (como Wine Deluxe)."""
    return f'=J{fila_base}*{MULT_CUERO[cuero]}'


def filas_producto_nuevo(nombre, unid_caja, cueros, fila0):
    """cueros: [(cuero, costo, precio)] con precio NaN = usar multiplicador.
    Devuelve una lista de filas A..X listas para escribir (USER_ENTERED)."""
    filas = []
    for k, (cuero, costo, precio) in enumerate(cueros):
        r = fila0 + k
        if isinstance(precio, float) and math.isnan(precio):
            j = formula_precio_por_multiplicador(fila0, cuero) if k > 0 else ''
        else:
            j = float(precio)
        filas.append([
            nombre if k == 0 else '', cuero, float(costo),
            f'=C{r}*($B$4/$B$5)', formula_default(), float(unid_caja), f'=$B$8/F{r}',
            f'=D{r}+E{r}+G{r}+$B$9', f'=${MULT_CUERO[cuero][0]}${MULT_CUERO[cuero][1:]}', j,
            f'=(J{r}-H{r})/J{r}', f'=ROUND(J{r}*$B$10)', f'=(L{r}-H{r})/L{r}',
            f'=ROUND(J{r}*$B$11)', f'=(N{r}-H{r})/N{r}', f'=ROUND(J{r}*$B$12)', f'=(P{r}-H{r})/P{r}',
            f'=(J{r}-L{r})/J{r}', f'=ROUND(J{r}*$B$13)', f'=ROUND(J{r}*$B$14)', f'=ROUND(J{r}*$B$15)',
            f'=ROUND(J{r}*$E$15)', f'=ROUND(H{r}*4)', f'=IF((L{r}-H{r})>0,$B$16/(L{r}-H{r}),"")',
        ])
    return filas


def df_producto_nuevo(nombre, unid_caja, cueros, fila0, b7):
    """Filas en el formato de parsear() para la vista previa."""
    regs = []
    for k, fila in enumerate(filas_producto_nuevo(nombre, unid_caja, cueros, fila0)):
        j = fila[9]
        regs.append({'Fila': fila0 + k, 'Producto': nombre, 'Cuero': fila[1],
                     'Costo proveedor': fila[2], '_f_C': '', 'Empaque': b7, '_f_E': formula_default(),
                     'Unid/caja': fila[5], '_f_F': '',
                     'Precio retail': j if isinstance(j, float) else math.nan,
                     '_f_J': j if isinstance(j, str) else ''})
    return pd.DataFrame(regs)
