"""Lógica de la página Feria (sin Streamlit), para poder probarla aparte.

Pestañas en la hoja MORAES_precios_ok:
- "Feria": configuración de la feria actual (filas "Etiqueta | valor": nombre,
  descuento máx, margen mín, envío del lote, empaque de feria, otros gastos) e
  inventario que se lleva (Producto | Cuero | Stock | Empaque feria). Es un
  inventario propio de la feria, separado de la bodega.
- "Ventas feria": una fila por venta. Las ventas anuladas quedan con Estado
  "anulada" y no cuentan.
"""
import math

HOJA_FERIA = 'Feria'
HOJA_VENTAS = 'Ventas feria'
CAB_STOCK = ['Producto', 'Cuero', 'Stock', 'Precio', 'Costo producto', 'Empaque', 'Envío']
CAB_VENTAS = ['Fecha', 'Hora', 'Feria', 'Producto', 'Cuero', 'Cantidad', 'Precio lista',
              'Descuento %', 'Precio final', 'Total', 'Pago', 'Cliente', 'Vendedora', 'Estado']
PAGOS = ['Efectivo', 'Tarjeta', 'Transferencia']

# Supuestos iniciales; se cambian en la página Precios feria
CONFIG_DEFAULT = {'feria': 'Feria', 'desc_max': 0.15, 'margen_min': 0.40, 'otros_gastos': 0.0}
# Filas de configuración (columna A = etiqueta, B = valor), antes de la cabecera del inventario
ETIQUETAS_CFG = [('feria', 'Feria'), ('desc_max', 'Descuento máximo %'), ('margen_min', 'Margen mínimo %'),
                 ('otros_gastos', 'Otros gastos de la feria ($)')]
_PCT = {'desc_max', 'margen_min'}
# Valores por producto/cuero que se pueden ajustar para la feria; vacío = el de la hoja Modelo
CAMPOS = ['precio', 'costo', 'empaque', 'envio']


def _num(v, default=math.nan):
    if v is None or v == '':
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace('$', '').replace(',', '')
    pct = s.endswith('%')
    try:
        n = float(s.rstrip('%'))
    except ValueError:
        return default
    return n / 100 if pct else n


def parsear_feria(grid):
    """→ (config, {(producto, cuero): stock}, {(producto, cuero): {campo: valor propio de feria}}).

    Config: filas "Etiqueta | valor" hasta la cabecera
    "Producto | Cuero | Stock | Precio | Costo producto | Empaque | Envío".
    """
    grid = [list(f) + [''] * 7 for f in (grid or [])]
    cfg = dict(CONFIG_DEFAULT)
    por_etiqueta = {e.lower(): k for k, e in ETIQUETAS_CFG}
    i_cab = next((i for i, f in enumerate(grid) if str(f[0]).strip().lower() == 'producto'), None)
    for i, fila in enumerate(grid[:i_cab] if i_cab is not None else grid[:6]):
        k = por_etiqueta.get(str(fila[0]).strip().lower())
        if k is None and i < 3:                       # formato viejo, posicional
            k = ['feria', 'desc_max', 'margen_min'][i]
        if k is None:
            continue
        if k == 'feria':
            cfg['feria'] = str(fila[1]).strip() or cfg['feria']
            continue
        n = _num(fila[1])
        if math.isnan(n):
            continue
        if k in _PCT:
            n = n / 100 if n > 1 else n              # se aceptan 15 o 0.15
        cfg[k] = n
    stock, ajustes = {}, {}
    for fila in (grid[i_cab + 1:] if i_cab is not None else []):
        prod, cuero = str(fila[0]).strip(), str(fila[1]).strip()
        if not (prod and cuero):
            continue
        q = _num(fila[2])
        stock[(prod, cuero)] = 0 if math.isnan(q) else int(q)
        aj = {c: _num(fila[3 + j]) for j, c in enumerate(CAMPOS)}
        aj = {c: v for c, v in aj.items() if not math.isnan(v)}
        if aj:
            ajustes[(prod, cuero)] = aj
    return cfg, stock, ajustes


def grid_feria(cfg, stock, ajustes=None):
    ajustes = ajustes or {}
    filas = []
    for k, etiqueta in ETIQUETAS_CFG:
        v = cfg.get(k, CONFIG_DEFAULT[k])
        filas.append([etiqueta, v if k == 'feria' else round(v * 100, 2) if k in _PCT else round(float(v), 2)])
    filas += [[], CAB_STOCK]
    for k in list(stock) + [k for k in ajustes if k not in stock]:
        aj = ajustes.get(k, {})
        filas.append([k[0], k[1], int(stock.get(k, 0))]
                     + ['' if aj.get(c) is None else round(float(aj[c]), 2) for c in CAMPOS])
    return filas


def parsear_ventas(grid):
    """Filas de ventas como dicts, con su número de fila en el Sheet."""
    out = []
    if not grid:
        return out
    cab = [str(x).strip() for x in grid[0]]
    for i, fila in enumerate(grid[1:], start=2):
        fila = list(fila) + [''] * len(cab)
        r = dict(zip(cab, fila))
        if not str(r.get('Producto', '')).strip():
            continue
        r['_fila'] = i
        r['Cantidad'] = int(_num(r.get('Cantidad'), 1))
        r['Total'] = _num(r.get('Total'), 0.0)
        out.append(r)
    return out


def vendidos(ventas, feria):
    """{(producto, cuero): unidades} de la feria, sin contar anuladas."""
    out = {}
    for r in ventas:
        if str(r.get('Feria', '')).strip() != feria or str(r.get('Estado', '')).strip().lower() == 'anulada':
            continue
        k = (str(r['Producto']).strip(), str(r['Cuero']).strip())
        out[k] = out.get(k, 0) + r['Cantidad']
    return out


def descuento_tope(precio, costo, desc_max, margen_min):
    """Descuento máximo (entero en %) que respeta el tope y el margen mínimo."""
    if not precio or precio <= 0 or costo is None or math.isnan(costo):
        return 0
    piso = costo / (1 - margen_min)          # precio mínimo para mantener el margen
    por_margen = 1 - piso / precio
    tope = min(desc_max, por_margen)
    return max(0, int(math.floor(tope * 100 + 1e-9)))


def precio_final(precio, desc_pct):
    """Precio con descuento, redondeado a dólar entero hacia arriba (nunca baja del piso)."""
    return float(math.ceil(precio * (1 - desc_pct / 100) - 1e-9))


def defaults_modelo(df, arancel):
    """Valores de la hoja Modelo por producto/cuero (df de precios.calcular; arancel = B9).
    costo = proveedor con ajuste cambiario + arancel; envio = flete normal por unidad."""
    out = {}
    for _, r in df.iterrows():
        precio = float(r['Precio retail'])
        if math.isnan(precio):
            continue
        out[(r['Producto'], r['Cuero'])] = {
            'precio': precio,
            'costo': float(r['Costo + FX']) + (0.0 if math.isnan(arancel) else float(arancel)),
            'empaque': float(r['Empaque']),
            'envio': float(r['Flete/und']) if not math.isnan(r['Flete/und']) else 0.0,
            'unid_caja': float(r['Unid/caja']),
        }
    return out


CUEROS_HOJA = ['Vaqueta', 'Napa', 'Crazy Horse', 'Hampton']


def cuero_hoja(variante):
    """'Vaqueta negra' → 'Vaqueta', 'Napa azul' → 'Napa', 'Crazy horse' → 'Crazy Horse'.
    El inventario de feria va por color; los costos de la hoja, por tipo de cuero."""
    v = str(variante).strip().lower()
    for c in CUEROS_HOJA:
        if v.startswith(c.lower().split()[0]):
            return c
    return str(variante).strip()


def base_de(base, k):
    return base.get(k) or base.get((k[0], cuero_hoja(k[1])), {})


def valores_feria(base, ajustes, k):
    """Precio y costos de un producto/variante en la feria: lo ajustado, o el de la hoja."""
    b, aj = base_de(base, k), ajustes.get(k, {})
    return {c: aj.get(c, b.get(c, math.nan)) for c in CAMPOS}


def repartir_envio(base, stock, total):
    """Reparte el envío total del lote por tamaño: cada unidad pesa 1/unid_caja (un Duffle
    ocupa más caja que un Luggage Tag). Sin unid/caja, la unidad pesa como el promedio.
    → {(p, c): envío por unidad}"""
    llevadas = {k: q for k, q in stock.items() if q > 0}
    uc = {k: base_de(base, k).get('unid_caja', math.nan) for k in llevadas}
    pesos = {k: 1 / u for k, u in uc.items() if u and not math.isnan(u) and u > 0}
    prom = sum(pesos.values()) / len(pesos) if pesos else 1.0
    peso = {k: pesos.get(k, prom) for k in llevadas}
    tot = sum(q * peso[k] for k, q in llevadas.items())
    return {k: total * peso[k] / tot for k in llevadas} if tot else {}


def resultado(v, cfg):
    """Costo total, margen y descuento máximo de una unidad con valores v (de valores_feria)."""
    costo = sum(0 if math.isnan(v[c]) else v[c] for c in ('costo', 'empaque', 'envio'))
    precio = v['precio']
    ok = not math.isnan(precio) and precio > 0
    margen = (precio - costo) / precio if ok else math.nan
    tope = descuento_tope(precio, costo, cfg['desc_max'], cfg['margen_min']) if ok else 0
    return {'costo_total': costo, 'margen': margen, 'desc_tope': tope,
            'precio_min': precio_final(precio, tope) if ok else math.nan}


def resumen_feria(base, stock, ajustes, cfg):
    llevadas = {k: q for k, q in stock.items() if q > 0}
    unidades = sum(llevadas.values())
    venta = costo = 0.0
    for k, q in llevadas.items():
        v = valores_feria(base, ajustes, k)
        if math.isnan(v['precio']):
            continue
        venta += v['precio'] * q
        costo += resultado(v, cfg)['costo_total'] * q
    ganancia = venta - costo
    gan_u = ganancia / unidades if unidades else 0.0
    eq = math.ceil(cfg['otros_gastos'] / gan_u - 1e-9) if gan_u > 0 and cfg['otros_gastos'] > 0 else None
    return {'unidades': unidades, 'venta': venta, 'costo': costo, 'ganancia': ganancia,
            'neto': ganancia - cfg['otros_gastos'], 'equilibrio_und': eq}


def fila_venta(fecha, hora, feria, producto, cuero, cantidad, precio, desc_pct, final, pago, cliente, vendedora):
    return [fecha, hora, feria, producto, cuero, int(cantidad), float(precio), float(desc_pct),
            float(final), float(final * cantidad), pago, cliente, vendedora, 'ok']


# Foto principal de cada producto (carpeta fotos/, sacadas de Drive "*-01-hero").
# Según moraesleather.com: Everyday Glove Case = golf-glove-case (cognac), Golf Glove Case = golf-glove (oscura).
# Supuesto: Valuables Pouch = cognac-golf-pouch-01-hero.
FOTOS = {
    'Golf Glove Case': 'everyday-glove-case.webp',
    'Everyday Glove Case': 'golf-glove-case.webp',
    'Drawstring Pouch': 'drawstring-pouch.webp',
    'Valuables Pouch': 'valuables-pouch.webp',
    'Notebook / Planner Cover': 'planner-cover.webp',
    'Padfolio': 'padfolio.webp',
    'Scorecard Holder': 'scorecard-holder.webp',
    'Wine Deluxe': 'wine-deluxe.webp',
    'Wine Dual': 'wine-dual.webp',
    'Wine Single': 'wine-single.webp',
    'Wine Magnum': 'wine-magnum.webp',   # bajada de moraesleather.com en la Mac
    'Luggage Tag': 'luggage-tag.webp',
    'Duffle': 'duffle.webp',
    'Cylindrical Wine Duo Carrier': 'cylindrical-wine-duo.webp',
    'Money Clip Wallet': 'money-clip-wallet.webp',
    'Shoe Bag': 'shoe-bag.webp',
    'Toiletry Bag': 'toiletry-bag.webp',
    'Toiletry Bag Deluxe': 'toiletry-bag-deluxe.webp',
    'Laptop Sleeve': 'laptop-sleeve.webp',
}


# Inventario inicial de la primera feria (29 nov 2026), de la lista a mano de Nicolás.
# Códigos del proveedor (pestaña Pedidos_Proveedor, pedido OCT-2026-07 "feria - stock"):
# 434 Wine Deluxe, 5252 Wine Dual, 432 Wine Single, 111 Everyday Glove Case (supuesto),
# 417 Toiletry Bag (supuesto), 5231 Golf Glove Case, 4854 Scorecard Holder, 308 Duffle,
# 600 Padfolio, 4807 Luggage Tag, 4710 Money Clip Wallet (supuesto).
# HS = vaqueta hoja seca, Ø = negra. Productos nuevos (aún sin fila en la hoja Modelo; precio y
# costos se ponen en Precios feria): 1032 Leather Notebook Cover Midori, 9898 Luxury Keychain.
# 9897 (A5 cover) no va a la feria.
SEMILLA = {
    ('Wine Deluxe', 'Vaqueta hoja seca'): 5, ('Wine Deluxe', 'Vaqueta café'): 5, ('Wine Deluxe', 'Vaqueta negra'): 5,
    ('Wine Dual', 'Vaqueta hoja seca'): 10, ('Wine Dual', 'Vaqueta café'): 5, ('Wine Dual', 'Vaqueta negra'): 5,
    ('Wine Single', 'Vaqueta hoja seca'): 5, ('Wine Single', 'Vaqueta café'): 5,
    ('Everyday Glove Case', 'Crazy Horse'): 19, ('Everyday Glove Case', 'Vaqueta hoja seca'): 19,
    ('Toiletry Bag', 'Vaqueta hoja seca'): 5, ('Toiletry Bag', 'Crazy Horse'): 4,
    ('Golf Glove Case', 'Crazy Horse'): 45,
    ('Scorecard Holder', 'Crazy Horse'): 10, ('Scorecard Holder', 'Vaqueta hoja seca'): 10,
    ('Scorecard Holder', 'Vaqueta negra'): 5,
    ('Duffle', 'Vaqueta hoja seca'): 3,
    ('Padfolio', 'Vaqueta hoja seca'): 3,
    ('Luggage Tag', 'Napa verde'): 5, ('Luggage Tag', 'Napa azul'): 5, ('Luggage Tag', 'Vaqueta hoja seca'): 10,
    ('Luggage Tag', 'Vaqueta negra'): 10, ('Luggage Tag', 'Vaqueta café'): 10,
    ('Money Clip Wallet', 'Vaqueta negra'): 10, ('Money Clip Wallet', 'Crazy Horse'): 10,
    ('Money Clip Wallet', 'Vaqueta hoja seca'): 10,
    ('Leather Notebook Cover Midori', 'Hampton'): 8, ('Leather Notebook Cover Midori', 'Azul'): 4,
    ('Leather Notebook Cover Midori', 'Café'): 1,
    ('Luxury Keychain', 'Hampton'): 15, ('Luxury Keychain', 'Azul cuadros'): 12,
    ('Luxury Keychain', 'Azul oscuro'): 7,
}
# Código del proveedor de los productos nuevos
CODIGOS_NUEVOS = {'Leather Notebook Cover Midori': '1032', 'Luxury Keychain': '9898'}
