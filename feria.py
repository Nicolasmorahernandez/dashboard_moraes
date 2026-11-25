"""Lógica de la página Feria (sin Streamlit), para poder probarla aparte.

Pestañas en la hoja MORAES_precios_ok:
- "Feria": configuración de la feria actual (A1:B3) e inventario que se lleva
  (desde la fila 5: Producto | Cuero | Stock). Es un inventario propio de la
  feria, separado de la bodega.
- "Ventas feria": una fila por venta. Las ventas anuladas quedan con Estado
  "anulada" y no cuentan.
"""
import math

HOJA_FERIA = 'Feria'
HOJA_VENTAS = 'Ventas feria'
CAB_STOCK = ['Producto', 'Cuero', 'Stock']
CAB_VENTAS = ['Fecha', 'Hora', 'Feria', 'Producto', 'Cuero', 'Cantidad', 'Precio lista',
              'Descuento %', 'Precio final', 'Total', 'Pago', 'Cliente', 'Vendedora', 'Estado']
PAGOS = ['Efectivo', 'Tarjeta', 'Transferencia']

# Supuestos iniciales; se cambian en "Preparar feria"
CONFIG_DEFAULT = {'feria': 'Feria', 'desc_max': 0.15, 'margen_min': 0.40}


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
    """→ (config, {(producto, cuero): stock})."""
    grid = [list(f) + ['', '', ''] for f in (grid or [])]
    cfg = dict(CONFIG_DEFAULT)
    if len(grid) >= 3:
        nombre = str(grid[0][1]).strip()
        cfg['feria'] = nombre or cfg['feria']
        d = _num(grid[1][1])
        m = _num(grid[2][1])
        # Se aceptan 15 o 0.15
        if not math.isnan(d):
            cfg['desc_max'] = d / 100 if d > 1 else d
        if not math.isnan(m):
            cfg['margen_min'] = m / 100 if m > 1 else m
    stock = {}
    for fila in grid[5:]:
        prod, cuero = str(fila[0]).strip(), str(fila[1]).strip()
        if prod and cuero:
            q = _num(fila[2])
            stock[(prod, cuero)] = 0 if math.isnan(q) else int(q)
    return cfg, stock


def grid_feria(cfg, stock):
    filas = [['Feria', cfg['feria']],
             ['Descuento máximo %', round(cfg['desc_max'] * 100, 2)],
             ['Margen mínimo %', round(cfg['margen_min'] * 100, 2)],
             [],
             CAB_STOCK]
    filas += [[p, c, int(q)] for (p, c), q in stock.items()]
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


def fila_venta(fecha, hora, feria, producto, cuero, cantidad, precio, desc_pct, final, pago, cliente, vendedora):
    return [fecha, hora, feria, producto, cuero, int(cantidad), float(precio), float(desc_pct),
            float(final), float(final * cantidad), pago, cliente, vendedora, 'ok']


# Foto principal de cada producto (carpeta fotos/, sacadas de Drive "*-01-hero").
# Supuesto: Everyday Glove Case = golf-glove-01-hero y Valuables Pouch = cognac-golf-pouch-01-hero.
FOTOS = {
    'Golf Glove Case': 'golf-glove-case.webp',
    'Everyday Glove Case': 'everyday-glove-case.webp',
    'Drawstring Pouch': 'drawstring-pouch.webp',
    'Valuables Pouch': 'valuables-pouch.webp',
    'Notebook / Planner Cover': 'planner-cover.webp',
    'Padfolio': 'padfolio.webp',
    'Scorecard Holder': 'scorecard-holder.webp',
    'Wine Deluxe': 'wine-deluxe.webp',
    'Wine Dual': 'wine-dual.webp',
    'Wine Single': 'wine-single.webp',
}
