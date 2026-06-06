import gspread, pickle, pandas as pd

with open('token.pickle','rb') as f:
    creds = pickle.load(f)
gc = gspread.authorize(creds)
fin = gc.open_by_key('1ODzs4-V__I5uN5mcbwJrUwIKrDrK6nn-wlii-eKNEhg')

try:
    fin.del_worksheet(fin.worksheet('Costos Amazon'))
except:
    pass
ws = fin.add_worksheet(title='Costos Amazon', rows=80, cols=8)

AMBER_BG  = {'red':0.58,'green':0.28,'blue':0.14}
HEADER_BG = {'red':0.15,'green':0.09,'blue':0.07}
HEADER_TXT = {'red':0.96,'green':0.93,'blue':0.91}
MUTED_TXT  = {'red':0.63,'green':0.50,'blue':0.44}
GREEN_TXT  = {'red':0.20,'green':0.68,'blue':0.32}
RED_TXT    = {'red':0.97,'green':0.44,'blue':0.44}
BLUE_TXT   = {'red':0.38,'green':0.64,'blue':0.98}

def hdr(rng):
    ws.format(rng, {'textFormat':{'bold':True,'foregroundColor':HEADER_TXT}, 'backgroundColor':HEADER_BG})

def sec(rng):
    ws.format(rng, {'textFormat':{'bold':True,'foregroundColor':AMBER_BG,'fontSize':11}})

def bold(rng, color=None):
    f = {'textFormat':{'bold':True}}
    if color: f['textFormat']['foregroundColor'] = color
    ws.format(rng, f)

# TITULO
ws.update(range_name='A1', values=[['MORAES — AUDITORIA DE COSTOS CANAL AMAZON']])
ws.update(range_name='A2', values=[['Todos los costos imputados a Amazon para verificar rentabilidad']])
ws.merge_cells('A1:H1'); ws.merge_cells('A2:H2')
ws.format('A1', {'textFormat':{'bold':True,'fontSize':13,'foregroundColor':HEADER_TXT},'horizontalAlignment':'CENTER'})
ws.format('A2', {'textFormat':{'italic':True,'foregroundColor':MUTED_TXT},'horizontalAlignment':'CENTER'})

# 1. INGRESOS
ws.update(range_name='A4', values=[['1. INGRESOS AMAZON']]); sec('A4')
ws.update(range_name='A5:C5', values=[['Concepto','Detalle','Monto (USD)']]); hdr('A5:C5')
ws.update(range_name='A6:C9', values=[
    ['Ventas FBA (25 unidades)','BT-CX89-PS3K @ $59.40','$1,485.00'],
    ['Ventas FBM (14 unidades)','BT-CX89-PS3K @ $57.49','$804.86'],
    ['Devolucion','1 unidad @ -$54.90','-$54.90'],
    ['TOTAL INGRESOS','','$2,298.60'],
])
bold('A9:C9', color=BLUE_TXT)

# 2. FEES AMAZON
ws.update(range_name='A11', values=[['2. FEES COBRADOS POR AMAZON']]); sec('A11')
ws.update(range_name='A12:C12', values=[['Tipo de Fee','','Monto (USD)']]); hdr('A12:C12')
ws.update(range_name='A13:C24', values=[
    ['Commission (15% aprox)','Por cada venta','-$413.66'],
    ['FBA Fulfillment Fee','Empaque y envio desde bodega Amazon','-$137.71'],
    ['Advertising Fee','Ads / PPC campanas','-$162.22'],
    ['Subscription Fee','Membresia vendedor profesional','-$142.77'],
    ['Postage / Shipping','Envio pedidos','-$117.27'],
    ['FBA Inbound Transportation','Envio a bodega FBA','-$23.20'],
    ['Coupon Fees','Descuentos con cupones','-$17.85'],
    ['Storage & Processing','Almacenamiento FBA','-$7.92'],
    ['Otros','Closing fee, ajustes, etc.','-$0.45'],
    ['Reversal comision devolucion','Amazon regresa comision','+$25.11'],
    ['','',''],
    ['TOTAL FEES AMAZON','','-$1,023.05'],
])
bold('A24:C24', color=RED_TXT)

# 3. GASTOS OPERATIVOS PROPIOS AMAZON
ws.update(range_name='A26', values=[['3. GASTOS OPERATIVOS PROPIOS (Canal = Amazon)']]); sec('A26')
ws.update(range_name='A27:C27', values=[['Fecha','Descripcion','Monto (USD)']]); hdr('A27:C27')
ws.update(range_name='A28:C33', values=[
    ['may 2026','Box for 5231 (500 cajas de producto @ $0.84)','-$420.00'],
    ['may 2026','Inventario MAY-2026-001-AMZ (50 uds) [pendiente]','-$606.00'],
    ['may 2026','Envio Colombia a EE.UU. MAY-2026-001 ($332 / 50 uds)','-$332.00'],
    ['jun 2026','Inventario JUN-2026-02-AMZ (50 uds) [pendiente]','-$606.00'],
    ['','Envio JUN-2026-02-AMZ (50 uds a $150)  [pendiente]','-$150.00'],
    ['TOTAL GASTOS PROPIOS AMAZON','','-$2,114.00'],
])
bold('A33:C33', color=RED_TXT)

# 4. GASTOS AMBOS PRORRATEO
ws.update(range_name='A35', values=[['4. GASTOS COMPARTIDOS - PARTE AMAZON (57.6% del total)']]); sec('A35')
ws.update(range_name='A36:D36', values=[['Fecha','Descripcion','Total gasto','Parte Amazon']]); hdr('A36:D36')
ws.update(range_name='A37:D50', values=[
    ['oct 2025','Jungle Scout','$100.00','$57.56'],
    ['nov 2025','Empaque inicial','$42.00','$24.17'],
    ['nov 2025','Diseno de logos','$43.00','$24.75'],
    ['nov 2025','Marketing / Moraes Care','$35.00','$20.14'],
    ['ene 2026','Bolsas de envio','$18.84','$10.84'],
    ['feb 2026','Empaque (stickers, cajas, bolsas, papel, hoja)','$105.15','$60.52'],
    ['feb 2026','Equipos (luces, tripode, impresora)','$90.81','$52.27'],
    ['feb 2026','Diseno logos cajas y bolsas','$48.57','$27.95'],
    ['mar 2026','Inventario EN-2026-001 (5252+5231 mixto)','$454.05','$261.34'],
    ['mar 2026','Envio EN-2026-001 Colombia a EE.UU.','$190.00','$109.36'],
    ['abr 2026','Dominios moraesleather.com + correo','$17.00','$9.79'],
    ['jun 2026','Tarjetas de presentacion','$54.55','$31.40'],
    ['','','',''],
    ['TOTAL PARTE AMAZON (57.6%)','$1,198.97','','$690.09'],
])
bold('A50:D50', color=RED_TXT)

# 5. RESUMEN
ws.update(range_name='A52', values=[['5. RESUMEN DE RENTABILIDAD']]); sec('A52')
ws.update(range_name='A53:C53', values=[['Concepto','Escenario','Monto (USD)']]); hdr('A53:C53')
ws.update(range_name='A54:C64', values=[
    ['INGRESOS','','+$2,298.60'],
    ['- Fees Amazon','','-$1,023.05'],
    ['- Gastos propios pagados (cajas + envio MAY)','','-$752.00'],
    ['- Parte Ambos pagada (57.6%)','','-$531.65'],
    ['= NETO CAJA REAL (sin pendientes)','','$-8.10'],
    ['','',''],
    ['- Gastos propios pendientes (inv MAY+JUN + envio JUN)','','-$1,362.00'],
    ['- Parte Ambos pendiente (57.6%)','','-$96.06'],
    ['= NETO PROYECTADO (todo pagado)','','-$1,466.16'],
    ['','',''],
    ['CONCLUSION: rentabilidad negativa hasta vender el inventario pendiente (MAY+JUN 100 uds)','',''],
])
bold('A57:C57', color=GREEN_TXT)
bold('A62:C62', color=RED_TXT)
ws.format('A64:C64', {'textFormat':{'italic':True,'foregroundColor':MUTED_TXT}})

# Anchos de columna
fin.batch_update({'requests':[
    {'updateDimensionProperties':{'range':{'sheetId':ws.id,'dimension':'COLUMNS','startIndex':0,'endIndex':1},'properties':{'pixelSize':120},'fields':'pixelSize'}},
    {'updateDimensionProperties':{'range':{'sheetId':ws.id,'dimension':'COLUMNS','startIndex':1,'endIndex':2},'properties':{'pixelSize':340},'fields':'pixelSize'}},
    {'updateDimensionProperties':{'range':{'sheetId':ws.id,'dimension':'COLUMNS','startIndex':2,'endIndex':3},'properties':{'pixelSize':130},'fields':'pixelSize'}},
    {'updateDimensionProperties':{'range':{'sheetId':ws.id,'dimension':'COLUMNS','startIndex':3,'endIndex':4},'properties':{'pixelSize':150},'fields':'pixelSize'}},
]})

print('HOJA CREADA OK')
