import pandas as pd
import streamlit as st

from auth import autenticar
from constants import (
    SHEET_FINANZAS_ID as _FINANZAS_DEFAULT,
    SHEET_AMAZON_ID as _AMAZON_DEFAULT,
    SKU_MAP,
)

# Sheet IDs: override via st.secrets (keys: sheet_finanzas_id / sheet_amazon_id)
SHEET_FINANZAS_ID = st.secrets.get('sheet_finanzas_id') or _FINANZAS_DEFAULT
SHEET_AMAZON_ID   = st.secrets.get('sheet_amazon_id')   or _AMAZON_DEFAULT


@st.cache_data(ttl=300)
def cargar_gastos_operativos():
    try:
        gc = autenticar()
        sh = gc.open_by_key(SHEET_FINANZAS_ID)
        ws = next(s for s in sh.worksheets() if 'gastos' in s.title.lower() and 'amazon' not in s.title.lower())
        df = pd.DataFrame(ws.get_all_records(head=4))
        df.columns = [c.strip() for c in df.columns]
        df['Monto Total (USD)'] = pd.to_numeric(
            df['Monto Total (USD)'].astype(str).str.replace('[$,]', '', regex=True), errors='coerce'
        ).fillna(0)
        df = df[df['Fecha'].astype(str).str.strip() != '']
        df = df[~df['Fecha'].astype(str).str.strip().str.upper().str.startswith('TOTAL')]
        df = df[~df['Fecha'].astype(str).str.contains('🔴|Fondo rojo|Categorías', na=False)]
        df['Pagado'] = df['¿Pagado?'].astype(str).str.contains('✅|TRUE|true|si|sí', case=False)
        if 'Canal' not in df.columns:
            df['Canal'] = 'Ambos'
        df['Canal'] = df['Canal'].astype(str).str.strip()
        if 'Tipo' not in df.columns:
            df['Tipo'] = 'Directo'
        df['Tipo'] = df['Tipo'].astype(str).str.strip()
        if '¿En inventario?' not in df.columns:
            df['¿En inventario?'] = 'No'
        df['En inventario'] = df['¿En inventario?'].astype(str).str.strip().str.lower().isin(['sí','si','yes','true'])
        return df
    except Exception as e:
        st.error(f"Error Gastos Operativos: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def cargar_ventas():
    try:
        gc = autenticar()
        frames = []
        sh1 = gc.open_by_key(SHEET_FINANZAS_ID)
        ws1 = next((s for s in sh1.worksheets() if 'ventas' in s.title.lower()), None)
        if ws1:
            h = ['Fecha','Producto','SKU','Canal','Unidades','Precio Unit (USD)','Total (USD)','Cuenta','Notas']
            df1 = pd.DataFrame(ws1.get_all_records(head=3, expected_headers=h))
            df1.columns = [c.strip() for c in df1.columns]
            df1 = df1[df1['Fecha'].astype(str).str.strip() != '']
            frames.append(df1)
        sh2 = gc.open_by_key(SHEET_AMAZON_ID)
        ws2 = next((s for s in sh2.worksheets() if s.title.strip() == 'Ventas Amazon'), None)
        if ws2:
            df2 = pd.DataFrame(ws2.get_all_records(head=3))
            df2.columns = [c.strip() for c in df2.columns]
            df2 = df2[df2['Fecha'].astype(str).str.strip() != '']
            df2 = df2.rename(columns={
                'Cantidad': 'Unidades',
                'Precio Unitario (USD)': 'Precio Unit (USD)',
                'Ingreso Total (USD)': 'Total (USD)',
                'Fulfillment': 'Cuenta',
            })
            if 'Canal' not in df2.columns:
                df2['Canal'] = 'Amazon'
            if 'Notas' not in df2.columns:
                df2['Notas'] = ''
            frames.append(df2[['Fecha','Producto','SKU','Canal','Unidades','Precio Unit (USD)','Total (USD)','Cuenta','Notas']])
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if df.empty:
            return df
        df['SKU'] = df['SKU'].astype(str).str.strip().replace(SKU_MAP)
        for col in ['Total (USD)', 'Precio Unit (USD)']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace('[$,]', '', regex=True), errors='coerce').fillna(0)
        df['Unidades'] = pd.to_numeric(df['Unidades'], errors='coerce').fillna(0)
        cuenta = df['Cuenta'].astype(str).str.strip().str.upper()
        df['Cobrado'] = ~(cuenta.str.contains('NO HAN PAGADO|NO PAGADO', na=False) | (cuenta == ''))
        return df
    except Exception as e:
        st.error(f"Error Ventas: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def cargar_margenes():
    try:
        gc = autenticar()
        sh = gc.open_by_key(SHEET_FINANZAS_ID)
        ws = next(s for s in sh.worksheets() if 'rgen' in s.title.lower() or 'argen' in s.title.lower())
        h = ['SKU','Canal','Costo COP','Costo USD','Envío','Empaque','Publicidad','Comisión','Costo Total','Precio Venta','Ganancia','Margen %','ROI %']
        df = pd.DataFrame(ws.get_all_records(head=3, expected_headers=h))
        df.columns = [c.strip() for c in df.columns]
        for col in ['Costo Total', 'Precio Venta', 'Ganancia']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace('[$,%]', '', regex=True), errors='coerce').fillna(0)
        df = df[df['SKU'].astype(str).str.strip() != '']
        df = df[~df['SKU'].astype(str).str.startswith('*')]
        return df
    except Exception as e:
        st.error(f"Error Márgenes: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def cargar_gastos_amazon():
    try:
        gc = autenticar()
        sh = gc.open_by_key(SHEET_AMAZON_ID)
        ws = next(s for s in sh.worksheets() if 'gastos amazon' in s.title.lower() or ('amazon' in s.title.lower() and 'gasto' in s.title.lower()))
        h = ['Transaction ID','Fecha','Order ID','Tipo de Fee','SKU','Monto (USD)','Descripcion']
        df = pd.DataFrame(ws.get_all_records(head=2, expected_headers=h))
        df.columns = [c.strip() for c in df.columns]
        df['Monto (USD)'] = pd.to_numeric(df['Monto (USD)'].astype(str).str.replace('[$,]', '', regex=True), errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Error Gastos Amazon: {e}")
        return pd.DataFrame()


def ajustar_inventario_con_ventas(df_inv, df_ventas):
    """Stock mostrado = 'Comprado' del sheet − unidades vendidas por SKU.
    Los valores derivados (costo y mercado) se recalculan sobre el stock restante.
    Si el sheet no tiene columna 'Comprado', se usa 'Stock (ajustable)' como base."""
    if df_inv.empty or df_ventas.empty or 'Unidades' not in df_ventas.columns:
        return df_inv
    df = df_inv.copy()
    vendidas = (
        df_ventas.assign(SKU=df_ventas['SKU'].astype(str).str.strip())
        .groupby('SKU')['Unidades'].sum()
    )
    sku = df['SKU'].astype(str).str.strip()
    base = df['Comprado'] if 'Comprado' in df.columns else df['Stock (ajustable)']
    df['Stock (ajustable)'] = (base - sku.map(vendidas).fillna(0)).clip(lower=0)
    if 'Costo Unit. (USD)' in df.columns:
        df['Valor en Stock (USD)'] = df['Stock (ajustable)'] * df['Costo Unit. (USD)']
    if 'Precio Mercado (USD)' in df.columns:
        df['Valor a Mercado (USD)'] = df['Stock (ajustable)'] * df['Precio Mercado (USD)']
    return df


@st.cache_data(ttl=300)
def cargar_inventario():
    try:
        gc = autenticar()
        sh = gc.open_by_key(SHEET_FINANZAS_ID)
        ws = next(s for s in sh.worksheets() if 'inventario' in s.title.lower())
        df = pd.DataFrame(ws.get_all_records(head=4))
        df.columns = [c.strip() for c in df.columns]
        for col in ['Comprado', 'Vendido', 'Stock (ajustable)', 'Costo Unit. (USD)', 'Valor en Stock (USD)', 'Precio Mercado (USD)', 'Valor a Mercado (USD)']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace('[$,]', '', regex=True), errors='coerce').fillna(0)
        df = df[df['SKU'].astype(str).str.strip() != '']
        df = df[~df['SKU'].astype(str).str.strip().str.upper().str.startswith('TOTAL')]
        df = df[df['Costo Unit. (USD)'] > 0]
        if 'Canal' not in df.columns:
            df['Canal'] = 'Directo'
        df['Canal'] = df['Canal'].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Error Inventario: {e}")
        return pd.DataFrame()
