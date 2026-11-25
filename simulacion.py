"""Simulaciones de feria: lógica pura (sin Streamlit).

Entrada: lista de ítems {producto, cuero, stock, precio, costo} (costo = producto + empaque + envío por unidad).
Escenario: % vendido, descuento, gastos fijos, comisión de tarjeta y combos.
"""
import math


def _f(x, d=0.0):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return d
    return d if math.isnan(x) else x


def simular(items, vendido=1.0, desc=0.0, gastos_fijos=0.0, pct_tarjeta=0.0, comision=0.0,
            otros_pct=0.0, combos=(), vendido_por=None, costear_todo=True):
    """→ dict con ingresos, costo vendido, gastos, neto y detalle por producto y por combo.

    vendido / desc son fracciones (0.6 = 60 %). Los combos [{nombre, partes:[(clave, cant)], desc, cantidad}]
    consumen stock primero (limitado por lo que haya); el resto del stock se vende individualmente
    al % vendido. vendido_por permite un % distinto por clave (producto, cuero).
    """
    vendido_por = vendido_por or {}
    disp = {(i['producto'], i['cuero']): int(_f(i['stock'])) for i in items}
    info = {(i['producto'], i['cuero']): i for i in items}
    ing = cogs = 0.0
    det_combos = []
    for cb in combos:
        n = max(0, int(cb.get('cantidad', 0)))
        partes = [(tuple(k), int(q)) for k, q in cb.get('partes', []) if tuple(k) in info and q > 0]
        if not partes or n == 0:
            det_combos.append({'nombre': cb.get('nombre', 'Combo'), 'vendidos': 0, 'ingreso': 0.0,
                               'ganancia': 0.0, 'precio_lista': 0.0, 'precio': 0.0, 'margen': math.nan})
            continue
        posible = min(disp[k] // q for k, q in partes)
        n = min(n, posible)
        lista = sum(_f(info[k]['precio']) * q for k, q in partes)
        costo = sum(_f(info[k]['costo']) * q for k, q in partes)
        precio = lista * (1 - _f(cb.get('desc', 0)))
        for k, q in partes:
            disp[k] -= q * n
        ing += precio * n
        cogs += costo * n
        det_combos.append({'nombre': cb.get('nombre', 'Combo'), 'vendidos': n, 'piezas': n * sum(q for _, q in partes), 'ingreso': precio * n,
                           'ganancia': (precio - costo) * n, 'precio_lista': lista, 'precio': precio,
                           'margen': (precio - costo) / precio if precio else math.nan})
    det = []
    for k, i in info.items():
        pv = _f(vendido_por.get(k, vendido))
        q = int(round(disp[k] * min(max(pv, 0), 1)))
        precio = _f(i['precio']) * (1 - desc)
        costo = _f(i['costo'])
        ing += precio * q
        cogs += costo * q
        det.append({'producto': k[0], 'cuero': k[1], 'stock': int(_f(i['stock'])), 'vendidas': q,
                    'precio': precio, 'costo': costo, 'ingreso': precio * q,
                    'ganancia': (precio - costo) * q,
                    'margen': (precio - costo) / precio if precio else math.nan})
    comis = ing * min(max(pct_tarjeta, 0), 1) * comision
    otros = ing * otros_pct
    gastos = gastos_fijos + comis + otros
    inventario_sin_vender = sum(_f(info[k]['costo']) * (disp[k] - int(round(disp[k] * min(max(_f(vendido_por.get(k, vendido)), 0), 1))))
                                for k in info)
    cogs_vendido = cogs
    if costear_todo:        # todo se produjo/compró para la feria: se paga lo vendido o no
        cogs = sum(_f(i['costo']) * int(_f(i['stock'])) for i in items)
    return {'cogs_vendido': cogs_vendido, 'costo_stock': sum(_f(i['costo']) * int(_f(i['stock'])) for i in items),
            'ingresos': ing, 'cogs': cogs, 'bruta': ing - cogs, 'gastos': gastos, 'comisiones': comis,
            'neto': ing - cogs - gastos, 'productos': det, 'combos': det_combos,
            'sin_vender': inventario_sin_vender,
            'unidades': sum(d['vendidas'] for d in det) + sum(c.get('piezas', 0) for c in det_combos)}


def punto_equilibrio(items, desc=0.0, **kw):
    """Menor % vendido (entero) con neto ≥ 0, o None si ni vendiendo todo se cubre."""
    for p in range(0, 101):
        if simular(items, p / 100, desc, **kw)['neto'] >= 0:
            return p
    return None


def mapa_sensibilidad(items, vendidos, descuentos, **kw):
    """Matriz [desc][vendido] de ganancia neta."""
    return [[simular(items, v, d, **kw)['neto'] for v in vendidos] for d in descuentos]
