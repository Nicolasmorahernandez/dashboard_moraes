"""
Dashboard MORAES — Streamlit + Google Sheets + Plotly
Conecta con el Google Sheet "Finanzas MORAES" y presenta 6 pestañas de análisis.

ESTRUCTURA REAL DEL SHEET:
- Vendidos: headers en fila 3, datos desde fila 4 (cols B-I)
- Modelo Unitario de Rentabilidad: headers en fila 1, datos normales
- Pedidos: headers en fila 3, datos desde fila 4
- proveedores: headers en fila 1, datos normales

Los valores monetarios vienen con formato "$1,234.56" y los porcentajes como "22.42%".
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import pathlib, re

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard MORAES",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Estilos CSS personalizados ───────────────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stMetric"] {
        background: rgba(30,30,40,0.6);
        border: 1px solid rgba(100,100,120,0.3);
        border-radius: 10px;
        padding: 12px 16px;
    }
    [data-testid="stMetric"] label { font-size: 0.85rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 20px;
        border-radius: 8px 8px 0 0;
    }
</style>
""", unsafe_allow_html=True)

# ── Constantes ───────────────────────────────────────────────────────────────
SPREADSHEET_NAME = "Finanzas MORAES"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
SA_FILE = pathlib.Path(__file__).parent / "service_account.json"

# Columnas esperadas por hoja (para detectar la fila de headers automáticamente)
EXPECTED_HEADERS = {
    "Vendidos": "Producto",
    "Pedidos": "Producto",
    "Modelo Unitario de Rentabilidad": "Producto",
    "proveedores": "Proveedor",
}


# ── Conexión a Google Sheets ─────────────────────────────────────────────────
def get_gspread_client():
    """Autenticación con Service Account."""
    if not SA_FILE.exists():
        st.error(
            f"No se encontró **{SA_FILE.name}**. "
            "Coloca el archivo de credenciales de Service Account en la misma carpeta."
        )
        st.stop()
    creds = Credentials.from_service_account_file(str(SA_FILE), scopes=SCOPES)
    return gspread.authorize(creds)


def _find_header_row(all_values: list[list[str]], marker: str) -> int:
    """Busca la fila que contiene el marcador en cualquier celda (header real).

    Algunas hojas (Vendidos, Pedidos) tienen filas vacías o de título antes
    de la fila real de encabezados. Esta función escanea hasta encontrar
    una fila que contenga la palabra clave 'marker' (ej: 'Producto').
    """
    for idx, row in enumerate(all_values):
        # Buscar en todas las celdas de la fila
        for cell in row:
            if marker.lower() in str(cell).lower():
                return idx
    return 0  # fallback: primera fila


def _clean_currency(val: str) -> float:
    """Limpia valores monetarios: '$40,000.00' → 40000.0, '$14.91' → 14.91."""
    if pd.isna(val) or val is None:
        return 0.0
    s = str(val).strip()
    # Remover símbolo de moneda y espacios
    s = re.sub(r'[$ ]', '', s)
    # Remover comas de miles
    s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _clean_pct(val: str) -> float:
    """Limpia porcentajes: '22.42%' → 0.2242, '0.35' → 0.35."""
    if pd.isna(val) or val is None:
        return 0.0
    s = str(val).strip().replace('%', '')
    try:
        v = float(s)
        # Si el valor es >5, asumimos que es porcentaje (ej: 22.42 → 0.2242)
        if abs(v) > 5:
            return v / 100
        return v
    except ValueError:
        return 0.0


@st.cache_data(ttl=60)
def load_sheet(sheet_name: str) -> pd.DataFrame:
    """Carga una hoja del spreadsheet y devuelve un DataFrame limpio.

    Detecta automáticamente la fila de encabezados buscando una columna
    clave (ej: 'Producto'). Esto maneja hojas donde los headers no están
    en la fila 1.
    """
    try:
        gc = get_gspread_client()
        spreadsheet = gc.open(SPREADSHEET_NAME)
        worksheet = spreadsheet.worksheet(sheet_name)

        all_values = worksheet.get_all_values()
        if not all_values:
            return pd.DataFrame()

        # Detectar fila de headers buscando la palabra clave
        marker = EXPECTED_HEADERS.get(sheet_name, "Producto")
        header_idx = _find_header_row(all_values, marker)

        headers = all_values[header_idx]
        data = all_values[header_idx + 1:]

        if not data:
            return pd.DataFrame()

        # Crear DataFrame
        df = pd.DataFrame(data, columns=headers)

        # Eliminar columnas con nombre vacío
        df = df.loc[:, df.columns.str.strip() != ""]

        # Renombrar duplicados con sufijo
        cols = df.columns.tolist()
        seen = {}
        new_cols = []
        for c in cols:
            c_clean = c.strip()
            if c_clean in seen:
                seen[c_clean] += 1
                new_cols.append(f"{c_clean}_{seen[c_clean]}")
            else:
                seen[c_clean] = 0
                new_cols.append(c_clean)
        df.columns = new_cols

        # Limpiar celdas vacías y filas vacías
        df = df.replace("", None)
        df = df.dropna(how="all")

        return df

    except gspread.exceptions.WorksheetNotFound:
        st.warning(f"Hoja **'{sheet_name}'** no encontrada en el spreadsheet.")
        return pd.DataFrame()
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"No se encontró el spreadsheet **'{SPREADSHEET_NAME}'**.")
        st.stop()
    except Exception as e:
        st.error(f"Error al cargar la hoja **'{sheet_name}'**: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_vendidos_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carga la hoja 'Vendidos' y la separa en dos DataFrames independientes.

    La hoja 'Vendidos' contiene DOS tablas lado a lado:
    - Izquierda (cols 1-8): Tabla de VENTAS (Producto, Categoría, Fecha, etc.)
    - Derecha (cols 13-20): Tabla de GASTOS/COSTOS (Descripción, Categoría del Gasto, Monto, etc.)

    Retorna (df_ventas, df_gastos).
    """
    try:
        gc = get_gspread_client()
        spreadsheet = gc.open(SPREADSHEET_NAME)
        worksheet = spreadsheet.worksheet("Vendidos")
        all_values = worksheet.get_all_values()

        if not all_values:
            return pd.DataFrame(), pd.DataFrame()

        # Detectar fila de headers (buscar "Producto" en la fila)
        header_idx = _find_header_row(all_values, "Producto")
        headers = all_values[header_idx]
        data = all_values[header_idx + 1:]

        if not data:
            return pd.DataFrame(), pd.DataFrame()

        # ── TABLA DE VENTAS (columnas 1-8: Producto … ¿En Stock?) ────────
        ventas_cols_idx = list(range(1, 9))  # índices 1,2,3,4,5,6,7,8
        ventas_headers = [headers[i].strip() for i in ventas_cols_idx if i < len(headers)]
        ventas_data = []
        for row in data:
            vals = [row[i] if i < len(row) else "" for i in ventas_cols_idx]
            ventas_data.append(vals)

        df_ventas = pd.DataFrame(ventas_data, columns=ventas_headers)
        df_ventas = df_ventas.replace("", None)

        # Filtrar: solo filas con Producto no vacío y no es la fila "Total"
        first_col = df_ventas.columns[0] if len(df_ventas.columns) > 0 else None
        if first_col:
            df_ventas = df_ventas.dropna(subset=[first_col])
            df_ventas = df_ventas[~df_ventas[first_col].str.strip().str.lower().isin(["total", ""])]

        # ── TABLA DE GASTOS (columnas 13-20: Descripción … Proveedor) ────
        gastos_cols_idx = list(range(13, 21))  # índices 13,14,15,16,17,18,19,20
        gastos_headers = [headers[i].strip() for i in gastos_cols_idx if i < len(headers)]
        gastos_data = []
        for row in data:
            vals = [row[i] if i < len(row) else "" for i in gastos_cols_idx]
            gastos_data.append(vals)

        df_gastos = pd.DataFrame(gastos_data, columns=gastos_headers)
        df_gastos = df_gastos.replace("", None)

        # Filtrar: solo filas que tengan descripción del costo
        first_gasto_col = df_gastos.columns[0] if len(df_gastos.columns) > 0 else None
        if first_gasto_col:
            df_gastos = df_gastos.dropna(subset=[first_gasto_col])
            df_gastos = df_gastos[df_gastos[first_gasto_col].str.strip() != ""]

        # Renombrar duplicados en gastos si los hay
        for df in [df_ventas, df_gastos]:
            cols = df.columns.tolist()
            seen = {}
            new_cols = []
            for c in cols:
                if c in seen:
                    seen[c] += 1
                    new_cols.append(f"{c}_{seen[c]}")
                else:
                    seen[c] = 0
                    new_cols.append(c)
            df.columns = new_cols

        return df_ventas, df_gastos

    except Exception as e:
        st.error(f"Error al cargar la hoja **'Vendidos'**: {e}")
        return pd.DataFrame(), pd.DataFrame()


# ── Funciones auxiliares ─────────────────────────────────────────────────────
def safe_numeric(df: pd.DataFrame, col: str) -> pd.Series:
    """Convierte columna a numérico, limpiando $ y comas primero."""
    if col not in df.columns:
        return pd.Series(dtype=float)
    return df[col].apply(_clean_currency)


def safe_pct(df: pd.DataFrame, col: str) -> pd.Series:
    """Convierte columna de porcentaje a decimal."""
    if col not in df.columns:
        return pd.Series(dtype=float)
    return df[col].apply(_clean_pct)


def fmt_usd(val: float) -> str:
    return f"${val:,.2f}"


def fmt_pct(val: float) -> str:
    """Formatea decimal como porcentaje (0.35 → 35.0%)."""
    return f"{val * 100:.1f}%"


def empty_warning(name: str):
    st.info(f"No hay datos disponibles en la hoja **{name}**.")


def col_exists(df: pd.DataFrame, col: str) -> str | None:
    """Busca una columna con coincidencia parcial (case-insensitive).
    Útil porque los nombres pueden variar ligeramente con paréntesis, tildes, etc.
    Retorna el nombre exacto de la columna o None.
    """
    col_lower = col.lower()
    for c in df.columns:
        if col_lower in c.lower():
            return c
    return None


# ── Carga de datos ───────────────────────────────────────────────────────────
st.title("📊 Dashboard MORAES")
st.caption("Datos en tiempo real desde Google Sheets • Actualización cada 60 s")

with st.spinner("Cargando datos de Google Sheets…"):
    # Vendidos: se separa en tabla de ventas y tabla de gastos (están lado a lado)
    df_vendidos, df_gastos_vendidos = load_vendidos_tables()
    df_rentabilidad = load_sheet("Modelo Unitario de Rentabilidad")
    df_pedidos = load_sheet("Pedidos")
    df_proveedores = load_sheet("proveedores")

if st.button("🔄 Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

st.markdown("---")

# ── Preprocesamiento — VENDIDOS ──────────────────────────────────────────────
# Columnas reales: Producto, Categoría, Fecha de Venta, Cantidad Vendida,
#   Precio Unitario (USD), Ingreso Total (USD), Método de Pago, ¿En Stock?
COL_V_PRODUCTO = "Producto"
COL_V_CATEGORIA = col_exists(df_vendidos, "Categor") or "Categoría"
COL_V_FECHA = col_exists(df_vendidos, "Fecha de Venta") or "Fecha de Venta"
COL_V_CANTIDAD = col_exists(df_vendidos, "Cantidad Vendida") or "Cantidad Vendida"
COL_V_PRECIO = col_exists(df_vendidos, "Precio Unitario") or "Precio Unitario (USD)"
COL_V_INGRESO = col_exists(df_vendidos, "Ingreso Total") or "Ingreso Total (USD)"
COL_V_METODO_PAGO = col_exists(df_vendidos, "todo de Pago") or "Método de Pago"

if not df_vendidos.empty:
    if COL_V_CANTIDAD in df_vendidos.columns:
        df_vendidos[COL_V_CANTIDAD] = safe_numeric(df_vendidos, COL_V_CANTIDAD)
    if COL_V_PRECIO in df_vendidos.columns:
        df_vendidos[COL_V_PRECIO] = safe_numeric(df_vendidos, COL_V_PRECIO)
    if COL_V_INGRESO in df_vendidos.columns:
        df_vendidos[COL_V_INGRESO] = safe_numeric(df_vendidos, COL_V_INGRESO)
    if COL_V_FECHA in df_vendidos.columns:
        df_vendidos[COL_V_FECHA] = pd.to_datetime(
            df_vendidos[COL_V_FECHA], errors="coerce", dayfirst=True
        )
        df_vendidos["Mes"] = df_vendidos[COL_V_FECHA].dt.to_period("M").astype(str)

# ── Preprocesamiento — GASTOS (tabla derecha de la hoja Vendidos) ────────────
# Columnas reales: Descripción del Costo, Categoría del Gasto, Fecha de Pago,
#   Monto (USD), Método de Pago, Producto Asociado/Referencia, ¿Pagado?, Proveedor
COL_G_DESCRIPCION = col_exists(df_gastos_vendidos, "Descripci") or "Descripción del Costo"
COL_G_CATEGORIA = col_exists(df_gastos_vendidos, "Categor") or "Categoría del Gasto"
COL_G_FECHA = col_exists(df_gastos_vendidos, "Fecha de Pago") or "Fecha de Pago"
COL_G_MONTO = col_exists(df_gastos_vendidos, "Monto") or "Monto (USD)"
COL_G_PAGADO = col_exists(df_gastos_vendidos, "Pagado") or "¿Pagado?"
COL_G_PROVEEDOR = col_exists(df_gastos_vendidos, "Proveedor") or "Proveedor"

if not df_gastos_vendidos.empty:
    if COL_G_MONTO in df_gastos_vendidos.columns:
        df_gastos_vendidos[COL_G_MONTO] = safe_numeric(df_gastos_vendidos, COL_G_MONTO)
    if COL_G_FECHA in df_gastos_vendidos.columns:
        df_gastos_vendidos[COL_G_FECHA] = pd.to_datetime(
            df_gastos_vendidos[COL_G_FECHA], errors="coerce", dayfirst=True
        )

# ── Preprocesamiento — RENTABILIDAD ──────────────────────────────────────────
# Columnas reales: Producto, Método de venta, Precio de compra del producto (COP),
#   Precio de compra del producto (USD), Envio de colombia a EE.UU, Empaque,
#   Publicidad, Comisión, Costo Total, Precio de venta (USD), Ganancias (USD),
#   MARGIN, ROI
COL_R_PRODUCTO = "Producto"
COL_R_METODO = col_exists(df_rentabilidad, "todo de venta") or "Método de venta"
COL_R_COMPRA_USD = col_exists(df_rentabilidad, "compra del producto (USD)") or "Precio de compra del producto (USD)"
COL_R_COSTO = col_exists(df_rentabilidad, "Costo Total") or "Costo Total"
COL_R_VENTA = col_exists(df_rentabilidad, "Precio de venta") or "Precio de venta (USD)"
COL_R_GANANCIA = col_exists(df_rentabilidad, "Ganancias") or "Ganancias (USD)"
COL_R_MARGIN = "MARGIN"
COL_R_ROI = "ROI"

if not df_rentabilidad.empty:
    for c in [COL_R_COMPRA_USD, COL_R_COSTO, COL_R_VENTA, COL_R_GANANCIA]:
        if c in df_rentabilidad.columns:
            df_rentabilidad[c] = safe_numeric(df_rentabilidad, c)
    for c in [COL_R_MARGIN, COL_R_ROI]:
        if c in df_rentabilidad.columns:
            df_rentabilidad[c] = safe_pct(df_rentabilidad, c)
    # Limpiar filas con producto vacío (filas basura)
    df_rentabilidad = df_rentabilidad.dropna(subset=[COL_R_PRODUCTO])
    df_rentabilidad = df_rentabilidad[df_rentabilidad[COL_R_PRODUCTO].str.strip() != ""]

# ── Preprocesamiento — PEDIDOS ───────────────────────────────────────────────
# Columnas reales: Referencia del Pedido, Producto, Proveedor, Cantidad Solicitada,
#   Costo Unitario (COP), Costo Unitario Estimado (USD), Costo Total Estimado (USD),
#   Fecha Estimada de Llegada, ¿Pedido Confirmado?
COL_P_REF = col_exists(df_pedidos, "Referencia") or "Referencia del Pedido"
COL_P_PRODUCTO = "Producto"
COL_P_PROVEEDOR = "Proveedor"
COL_P_CANTIDAD = col_exists(df_pedidos, "Cantidad Solicitada") or "Cantidad Solicitada"
COL_P_COSTO_TOTAL = col_exists(df_pedidos, "Costo Total Estimado") or "Costo Total Estimado (USD)"
COL_P_FECHA = col_exists(df_pedidos, "Fecha Estimada") or "Fecha Estimada de Llegada"
COL_P_CONFIRMADO = col_exists(df_pedidos, "Pedido Confirmado") or "¿Pedido Confirmado?"

if not df_pedidos.empty:
    if COL_P_CANTIDAD in df_pedidos.columns:
        df_pedidos[COL_P_CANTIDAD] = safe_numeric(df_pedidos, COL_P_CANTIDAD)
    if COL_P_COSTO_TOTAL in df_pedidos.columns:
        df_pedidos[COL_P_COSTO_TOTAL] = safe_numeric(df_pedidos, COL_P_COSTO_TOTAL)
    if COL_P_FECHA in df_pedidos.columns:
        df_pedidos[COL_P_FECHA] = pd.to_datetime(
            df_pedidos[COL_P_FECHA], errors="coerce", dayfirst=True
        )
    # Limpiar filas sin producto
    df_pedidos = df_pedidos.dropna(subset=[COL_P_PRODUCTO])
    df_pedidos = df_pedidos[df_pedidos[COL_P_PRODUCTO].str.strip() != ""]


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑAS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📈 Panel General",
    "💰 Rentabilidad",
    "🔀 Comparación de Canales",
    "📦 Pedidos e Inventario",
    "🏷️ Costos por Producto",
    "🤝 Proveedores",
])

# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — Panel General
# ──────────────────────────────────────────────────────────────────────────────
with tab1:
    st.header("📈 Panel General")

    if df_vendidos.empty:
        empty_warning("Vendidos")
    else:
        ventas_totales = df_vendidos[COL_V_INGRESO].sum() if COL_V_INGRESO in df_vendidos.columns else 0
        # Gastos reales desde la tabla de costos de la hoja Vendidos
        gastos_totales = df_gastos_vendidos[COL_G_MONTO].sum() if not df_gastos_vendidos.empty and COL_G_MONTO in df_gastos_vendidos.columns else 0
        ganancia_neta = ventas_totales - gastos_totales
        cant_ventas = df_vendidos[COL_V_CANTIDAD].sum() if COL_V_CANTIDAD in df_vendidos.columns else 0
        ticket_promedio = ventas_totales / cant_ventas if cant_ventas > 0 else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("💵 Ventas Totales", fmt_usd(ventas_totales))
        k2.metric("📤 Gastos Totales", fmt_usd(gastos_totales))
        k3.metric(
            "📊 Ganancia Neta",
            fmt_usd(ganancia_neta),
            delta=fmt_usd(ganancia_neta),
            delta_color="normal",
        )
        k4.metric("🎫 Ticket Promedio", fmt_usd(ticket_promedio))

        st.markdown("---")

        col_chart, col_top = st.columns([2, 1])

        with col_chart:
            st.subheader("Ventas vs Gastos por Mes")
            if "Mes" in df_vendidos.columns and COL_V_INGRESO in df_vendidos.columns:
                ventas_mes = (
                    df_vendidos.groupby("Mes")[COL_V_INGRESO]
                    .sum()
                    .reset_index()
                    .rename(columns={COL_V_INGRESO: "Ventas"})
                )
                ventas_mes["Gastos"] = gastos_totales / len(ventas_mes) if len(ventas_mes) > 0 else 0

                fig_vg = px.bar(
                    ventas_mes, x="Mes", y=["Ventas", "Gastos"],
                    barmode="group", text_auto="$.2f",
                    color_discrete_sequence=["#00cc96", "#ef553b"],
                    labels={"value": "USD", "variable": ""},
                )
                fig_vg.update_layout(
                    template="plotly_dark",
                    legend=dict(orientation="h", y=-0.15),
                    margin=dict(t=20),
                )
                st.plotly_chart(fig_vg, use_container_width=True)
            else:
                st.info("No hay datos de fecha para graficar por mes.")

        with col_top:
            st.subheader("🏆 Top 3 Productos")
            if COL_V_CANTIDAD in df_vendidos.columns:
                top3 = (
                    df_vendidos.groupby(COL_V_PRODUCTO)[COL_V_CANTIDAD]
                    .sum()
                    .sort_values(ascending=False)
                    .head(3)
                    .reset_index()
                )
                for i, row in top3.iterrows():
                    medal = ["🥇", "🥈", "🥉"][i] if i < 3 else ""
                    st.markdown(f"**{medal} {row[COL_V_PRODUCTO]}** — {int(row[COL_V_CANTIDAD])} uds")

        st.markdown("---")

        # Gráfico de pastel: distribución de gastos por categoría (datos reales de costos)
        st.subheader("🥧 Distribución de Gastos por Categoría")
        if not df_gastos_vendidos.empty and COL_G_CATEGORIA in df_gastos_vendidos.columns and COL_G_MONTO in df_gastos_vendidos.columns:
            gastos_cat = (
                df_gastos_vendidos.dropna(subset=[COL_G_CATEGORIA])
                .groupby(COL_G_CATEGORIA)[COL_G_MONTO]
                .sum()
                .reset_index()
            )
            if not gastos_cat.empty:
                fig_pie = px.pie(
                    gastos_cat, names=COL_G_CATEGORIA, values=COL_G_MONTO,
                    hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig_pie.update_layout(template="plotly_dark", margin=dict(t=20))
                fig_pie.update_traces(textinfo="percent+label")
                st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No hay datos de gastos disponibles para el gráfico.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — Rentabilidad
# ──────────────────────────────────────────────────────────────────────────────
with tab2:
    st.header("💰 Rentabilidad")

    if df_rentabilidad.empty:
        empty_warning("Modelo Unitario de Rentabilidad")
    else:
        f1, f2 = st.columns(2)
        productos_list = df_rentabilidad[COL_R_PRODUCTO].dropna().unique().tolist()
        metodos_list = (
            df_rentabilidad[COL_R_METODO].dropna().unique().tolist()
            if COL_R_METODO in df_rentabilidad.columns else []
        )

        with f1:
            sel_prod = st.multiselect(
                "Filtrar por Producto", options=productos_list,
                default=productos_list, key="rent_prod",
            )
        with f2:
            sel_met = st.multiselect(
                "Filtrar por Método de Venta", options=metodos_list,
                default=metodos_list, key="rent_met",
            )

        df_r = df_rentabilidad.copy()
        if sel_prod:
            df_r = df_r[df_r[COL_R_PRODUCTO].isin(sel_prod)]
        if sel_met and COL_R_METODO in df_r.columns:
            df_r = df_r[df_r[COL_R_METODO].isin(sel_met)]

        if df_r.empty:
            st.warning("No hay datos con los filtros seleccionados.")
        else:
            roi_prom = df_r[COL_R_ROI].mean() if COL_R_ROI in df_r.columns else 0
            margin_prom = df_r[COL_R_MARGIN].mean() if COL_R_MARGIN in df_r.columns else 0
            ganancia_prom = df_r[COL_R_GANANCIA].mean() if COL_R_GANANCIA in df_r.columns else 0
            precio_venta_prom = df_r[COL_R_VENTA].mean() if COL_R_VENTA in df_r.columns else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📈 ROI Promedio", fmt_pct(roi_prom))
            m2.metric("📊 MARGIN Promedio", fmt_pct(margin_prom))
            m3.metric("💵 Ganancia Unitaria Prom.", fmt_usd(ganancia_prom))
            m4.metric("🏷️ Precio Venta Prom.", fmt_usd(precio_venta_prom))

            st.markdown("---")

            gc1, gc2 = st.columns(2)

            with gc1:
                st.subheader("ROI por Producto y Método")
                fig_roi = px.bar(
                    df_r, x=COL_R_PRODUCTO, y=COL_R_ROI,
                    color=COL_R_METODO if COL_R_METODO in df_r.columns else None,
                    barmode="group",
                    text=df_r[COL_R_ROI].apply(lambda v: f"{v*100:.1f}%"),
                    color_discrete_sequence=px.colors.qualitative.Vivid,
                    hover_data=[COL_R_GANANCIA, COL_R_VENTA] if COL_R_GANANCIA in df_r.columns else None,
                )
                fig_roi.update_layout(template="plotly_dark", margin=dict(t=20))
                fig_roi.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_roi, use_container_width=True)

            with gc2:
                st.subheader("MARGIN por Producto y Método")
                fig_mar = px.bar(
                    df_r, x=COL_R_PRODUCTO, y=COL_R_MARGIN,
                    color=COL_R_METODO if COL_R_METODO in df_r.columns else None,
                    barmode="group",
                    text=df_r[COL_R_MARGIN].apply(lambda v: f"{v*100:.1f}%"),
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                    hover_data=[COL_R_GANANCIA, COL_R_COSTO] if COL_R_GANANCIA in df_r.columns else None,
                )
                fig_mar.update_layout(template="plotly_dark", margin=dict(t=20))
                fig_mar.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_mar, use_container_width=True)

            st.markdown("---")

            # Tabla detallada
            st.subheader("📋 Tabla Detallada")
            df_display = df_r.copy()
            if COL_R_ROI in df_display.columns:
                df_display[COL_R_ROI] = df_display[COL_R_ROI].apply(fmt_pct)
            if COL_R_MARGIN in df_display.columns:
                df_display[COL_R_MARGIN] = df_display[COL_R_MARGIN].apply(fmt_pct)
            for c in [COL_R_COMPRA_USD, COL_R_VENTA, COL_R_COSTO, COL_R_GANANCIA]:
                if c in df_display.columns:
                    df_display[c] = df_display[c].apply(fmt_usd)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            st.markdown("---")

            # Mejor y peor ROI
            if COL_R_ROI in df_r.columns:
                best = df_r.loc[df_r[COL_R_ROI].idxmax()]
                worst = df_r.loc[df_r[COL_R_ROI].idxmin()]
                b1, b2 = st.columns(2)
                with b1:
                    st.success(
                        f"🏆 **Mejor ROI:** {best[COL_R_PRODUCTO]} "
                        f"({best.get(COL_R_METODO, 'N/A')}) — {fmt_pct(best[COL_R_ROI])}"
                    )
                with b2:
                    st.error(
                        f"⚠️ **Peor ROI:** {worst[COL_R_PRODUCTO]} "
                        f"({worst.get(COL_R_METODO, 'N/A')}) — {fmt_pct(worst[COL_R_ROI])}"
                    )


# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — Comparación de Canales
# ──────────────────────────────────────────────────────────────────────────────
with tab3:
    st.header("🔀 Comparación de Canales de Venta")

    if df_rentabilidad.empty or COL_R_METODO not in df_rentabilidad.columns:
        empty_warning("Modelo Unitario de Rentabilidad")
    else:
        canales = df_rentabilidad[COL_R_METODO].dropna().unique().tolist()

        if not canales:
            st.info("No se encontraron canales de venta.")
        else:
            cols = st.columns(len(canales))
            for i, canal in enumerate(canales):
                sub = df_rentabilidad[df_rentabilidad[COL_R_METODO] == canal]
                with cols[i]:
                    st.markdown(f"### {canal}")
                    st.metric("ROI Prom.", fmt_pct(sub[COL_R_ROI].mean()))
                    st.metric("MARGIN Prom.", fmt_pct(sub[COL_R_MARGIN].mean()))
                    st.metric("Ganancia Prom.", fmt_usd(sub[COL_R_GANANCIA].mean()))
                    st.metric("Productos", len(sub))

            st.markdown("---")

            agg = (
                df_rentabilidad.groupby(COL_R_METODO)
                .agg({COL_R_ROI: "mean", COL_R_MARGIN: "mean",
                      COL_R_GANANCIA: "sum", COL_R_COSTO: "sum"})
                .reset_index()
            )

            c1, c2 = st.columns(2)
            with c1:
                st.subheader("ROI Promedio por Canal")
                fig = px.bar(
                    agg, x=COL_R_METODO, y=COL_R_ROI,
                    text=agg[COL_R_ROI].apply(lambda v: f"{v*100:.1f}%"),
                    color=COL_R_METODO,
                    color_discrete_sequence=["#636efa", "#00cc96", "#ef553b"],
                )
                fig.update_layout(template="plotly_dark", showlegend=False, margin=dict(t=20))
                st.plotly_chart(fig, use_container_width=True)

            with c2:
                st.subheader("MARGIN Promedio por Canal")
                fig = px.bar(
                    agg, x=COL_R_METODO, y=COL_R_MARGIN,
                    text=agg[COL_R_MARGIN].apply(lambda v: f"{v*100:.1f}%"),
                    color=COL_R_METODO,
                    color_discrete_sequence=["#636efa", "#00cc96", "#ef553b"],
                )
                fig.update_layout(template="plotly_dark", showlegend=False, margin=dict(t=20))
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            st.subheader("Ganancia vs Costo por Canal")
            fig_gc = px.bar(
                agg, x=COL_R_METODO,
                y=[COL_R_GANANCIA, COL_R_COSTO],
                barmode="group", text_auto="$.2f",
                color_discrete_sequence=["#00cc96", "#ef553b"],
                labels={"value": "USD", "variable": ""},
            )
            fig_gc.update_layout(
                template="plotly_dark",
                legend=dict(orientation="h", y=-0.15),
                margin=dict(t=20),
            )
            st.plotly_chart(fig_gc, use_container_width=True)

            st.markdown("---")

            p1, p2 = st.columns(2)
            canal_counts = df_rentabilidad.groupby(COL_R_METODO).size().reset_index(name="Unidades")
            with p1:
                st.subheader("📦 Productos por Canal")
                fig = px.pie(canal_counts, names=COL_R_METODO, values="Unidades", hole=0.4)
                fig.update_layout(template="plotly_dark", margin=dict(t=20))
                fig.update_traces(textinfo="percent+label")
                st.plotly_chart(fig, use_container_width=True)

            ingresos_canal = (
                df_rentabilidad.groupby(COL_R_METODO)[COL_R_VENTA]
                .sum().reset_index().rename(columns={COL_R_VENTA: "Ingresos"})
            )
            with p2:
                st.subheader("💵 Ingresos por Canal")
                fig = px.pie(ingresos_canal, names=COL_R_METODO, values="Ingresos", hole=0.4)
                fig.update_layout(template="plotly_dark", margin=dict(t=20))
                fig.update_traces(textinfo="percent+label")
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            mejor_canal = agg.loc[agg[COL_R_ROI].idxmax(), COL_R_METODO]
            mejor_roi = agg.loc[agg[COL_R_ROI].idxmax(), COL_R_ROI]
            st.success(
                f"🎯 **Canal recomendado:** **{mejor_canal}** con el mejor ROI promedio de "
                f"**{fmt_pct(mejor_roi)}**"
            )


# ──────────────────────────────────────────────────────────────────────────────
# TAB 4 — Pedidos e Inventario
# ──────────────────────────────────────────────────────────────────────────────
with tab4:
    st.header("📦 Pedidos e Inventario")

    if df_pedidos.empty:
        empty_warning("Pedidos")
    else:
        # Estado de confirmación
        if COL_P_CONFIRMADO in df_pedidos.columns:
            df_pedidos["_confirmado"] = (
                df_pedidos[COL_P_CONFIRMADO]
                .astype(str).str.strip().str.upper()
                .isin(["SI", "SÍ", "YES", "TRUE", "VERDADERO", "1"])
            )
        else:
            df_pedidos["_confirmado"] = False

        total_pedidos = len(df_pedidos)
        confirmados = df_pedidos["_confirmado"].sum()
        pendientes = total_pedidos - confirmados
        inversion_total = df_pedidos[COL_P_COSTO_TOTAL].sum() if COL_P_COSTO_TOTAL in df_pedidos.columns else 0
        inversion_conf = (
            df_pedidos.loc[df_pedidos["_confirmado"], COL_P_COSTO_TOTAL].sum()
            if COL_P_COSTO_TOTAL in df_pedidos.columns else 0
        )

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("📋 Total Pedidos", total_pedidos)
        k2.metric("⏳ Pendientes", int(pendientes))
        k3.metric("💰 Inversión Total", fmt_usd(inversion_total))
        k4.metric("✅ Inversión Confirmada", fmt_usd(inversion_conf))

        st.markdown("---")

        f1, f2 = st.columns(2)
        with f1:
            estado_filtro = st.selectbox(
                "Estado", ["Todos", "Confirmados", "Pendientes"], key="ped_estado"
            )
        with f2:
            prod_ped = df_pedidos[COL_P_PRODUCTO].dropna().unique().tolist()
            sel_prod_ped = st.multiselect(
                "Producto", prod_ped, default=prod_ped, key="ped_prod"
            )

        df_p = df_pedidos.copy()
        if estado_filtro == "Confirmados":
            df_p = df_p[df_p["_confirmado"]]
        elif estado_filtro == "Pendientes":
            df_p = df_p[~df_p["_confirmado"]]
        if sel_prod_ped:
            df_p = df_p[df_p[COL_P_PRODUCTO].isin(sel_prod_ped)]

        if df_p.empty:
            st.warning("No hay pedidos con los filtros seleccionados.")
        else:
            # Inversión por producto
            if COL_P_COSTO_TOTAL in df_p.columns:
                st.subheader("💰 Inversión por Producto")
                inv_prod = (
                    df_p.groupby(COL_P_PRODUCTO)[COL_P_COSTO_TOTAL]
                    .sum().sort_values(ascending=False).reset_index()
                )
                fig = px.bar(
                    inv_prod, x=COL_P_PRODUCTO, y=COL_P_COSTO_TOTAL,
                    text_auto="$.2f", color_discrete_sequence=["#636efa"],
                )
                fig.update_layout(template="plotly_dark", margin=dict(t=20))
                fig.update_xaxes(tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # Tabla
            st.subheader("📋 Detalle de Pedidos")
            df_tabla = df_p.copy()
            df_tabla["Estado"] = df_tabla["_confirmado"].map(
                {True: "✅ Confirmado", False: "⏳ Pendiente"}
            )
            cols_show = [c for c in df_tabla.columns if not c.startswith("_")]
            st.dataframe(df_tabla[cols_show], use_container_width=True, hide_index=True)

            st.markdown("---")

            # Timeline
            if COL_P_FECHA in df_p.columns:
                df_timeline = df_p.dropna(subset=[COL_P_FECHA])
                if not df_timeline.empty and COL_P_CANTIDAD in df_timeline.columns:
                    st.subheader("📅 Timeline de Llegadas Estimadas")
                    fig_tl = px.scatter(
                        df_timeline,
                        x=COL_P_FECHA, y=COL_P_PRODUCTO,
                        size=COL_P_CANTIDAD, color=COL_P_PRODUCTO,
                        hover_data=[COL_P_PROVEEDOR, COL_P_COSTO_TOTAL] if COL_P_PROVEEDOR in df_timeline.columns else None,
                        size_max=40,
                    )
                    fig_tl.update_layout(
                        template="plotly_dark", showlegend=False, margin=dict(t=20),
                        yaxis=dict(categoryorder="total ascending"),
                    )
                    st.plotly_chart(fig_tl, use_container_width=True)

            st.markdown("---")

            c1, c2 = st.columns(2)
            with c1:
                if COL_P_CANTIDAD in df_p.columns:
                    st.subheader("📦 Unidades por Producto")
                    uds = df_p.groupby(COL_P_PRODUCTO)[COL_P_CANTIDAD].sum().reset_index()
                    fig = px.pie(uds, names=COL_P_PRODUCTO, values=COL_P_CANTIDAD, hole=0.4)
                    fig.update_layout(template="plotly_dark", margin=dict(t=20))
                    fig.update_traces(textinfo="percent+label")
                    st.plotly_chart(fig, use_container_width=True)

            with c2:
                st.subheader("📊 Resumen")
                if COL_P_CANTIDAD in df_p.columns:
                    st.metric("Total Unidades", int(df_p[COL_P_CANTIDAD].sum()))
                if COL_P_COSTO_TOTAL in df_p.columns:
                    st.metric("Costo Promedio/Pedido", fmt_usd(df_p[COL_P_COSTO_TOTAL].mean()))
                if COL_P_PROVEEDOR in df_p.columns:
                    st.metric("Proveedores", df_p[COL_P_PROVEEDOR].nunique())


# ──────────────────────────────────────────────────────────────────────────────
# TAB 5 — Costos por Producto
# ──────────────────────────────────────────────────────────────────────────────
with tab5:
    st.header("🏷️ Costos por Producto")

    if df_rentabilidad.empty:
        empty_warning("Modelo Unitario de Rentabilidad")
    else:
        f1, f2 = st.columns(2)
        prods_r = df_rentabilidad[COL_R_PRODUCTO].dropna().unique().tolist()
        canales_r = (
            df_rentabilidad[COL_R_METODO].dropna().unique().tolist()
            if COL_R_METODO in df_rentabilidad.columns else []
        )

        with f1:
            sel_prod_c = st.multiselect(
                "Producto", prods_r, default=prods_r, key="cost_prod"
            )
        with f2:
            sel_canal_c = st.multiselect(
                "Canal / Método", canales_r, default=canales_r, key="cost_canal"
            )

        df_c = df_rentabilidad.copy()
        if sel_prod_c:
            df_c = df_c[df_c[COL_R_PRODUCTO].isin(sel_prod_c)]
        if sel_canal_c and COL_R_METODO in df_c.columns:
            df_c = df_c[df_c[COL_R_METODO].isin(sel_canal_c)]

        if df_c.empty:
            st.warning("No hay datos con los filtros seleccionados.")
        else:
            costo_total = df_c[COL_R_COSTO].sum() if COL_R_COSTO in df_c.columns else 0
            productos_unicos = df_c[COL_R_PRODUCTO].nunique()
            items_costo = len(df_c)
            costo_promedio = df_c[COL_R_COSTO].mean() if COL_R_COSTO in df_c.columns else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("💰 Costo Total", fmt_usd(costo_total))
            m2.metric("📦 Productos Únicos", productos_unicos)
            m3.metric("📋 Ítems de Costo", items_costo)
            m4.metric("📊 Costo Promedio", fmt_usd(costo_promedio))

            st.markdown("---")

            c1, c2 = st.columns(2)
            with c1:
                if COL_R_METODO in df_c.columns:
                    st.subheader("Distribución por Canal")
                    dist_canal = df_c.groupby(COL_R_METODO)[COL_R_COSTO].sum().reset_index()
                    fig = px.pie(dist_canal, names=COL_R_METODO, values=COL_R_COSTO, hole=0.4)
                    fig.update_layout(template="plotly_dark", margin=dict(t=20))
                    fig.update_traces(textinfo="percent+label")
                    st.plotly_chart(fig, use_container_width=True)

            with c2:
                st.subheader("Costos por Producto")
                cost_prod = (
                    df_c.groupby(COL_R_PRODUCTO)[COL_R_COSTO]
                    .sum().sort_values(ascending=False).reset_index()
                )
                fig = px.bar(
                    cost_prod, x=COL_R_PRODUCTO, y=COL_R_COSTO,
                    text_auto="$.2f", color_discrete_sequence=["#ef553b"],
                )
                fig.update_layout(template="plotly_dark", margin=dict(t=20))
                fig.update_xaxes(tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # Desglose por canal (solo si un producto seleccionado)
            if len(sel_prod_c) == 1 and COL_R_METODO in df_c.columns:
                st.subheader(f"📊 Desglose por Canal — {sel_prod_c[0]}")
                canales_prod = df_c[COL_R_METODO].dropna().unique().tolist()
                if canales_prod:
                    tabs_canal = st.tabs(canales_prod)
                    for tab_c, canal in zip(tabs_canal, canales_prod):
                        with tab_c:
                            sub = df_c[df_c[COL_R_METODO] == canal]
                            sc1, sc2, sc3, sc4 = st.columns(4)
                            sc1.metric("Costo Total", fmt_usd(sub[COL_R_COSTO].sum()))
                            sc2.metric("Ganancia", fmt_usd(sub[COL_R_GANANCIA].sum()))
                            sc3.metric("ROI", fmt_pct(sub[COL_R_ROI].mean()))
                            sc4.metric("MARGIN", fmt_pct(sub[COL_R_MARGIN].mean()))
                st.markdown("---")

            # Tabla completa
            st.subheader("📋 Tabla Completa")
            df_cost_display = df_c.copy()
            for c in [COL_R_COMPRA_USD, COL_R_VENTA, COL_R_COSTO, COL_R_GANANCIA]:
                if c in df_cost_display.columns:
                    df_cost_display[c] = df_cost_display[c].apply(fmt_usd)
            for c in [COL_R_ROI, COL_R_MARGIN]:
                if c in df_cost_display.columns:
                    df_cost_display[c] = df_c[c].apply(fmt_pct)
            st.dataframe(df_cost_display, use_container_width=True, hide_index=True)

            csv = df_c.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Descargar CSV", csv, "costos_moraes.csv", "text/csv", key="dl_costos",
            )


# ──────────────────────────────────────────────────────────────────────────────
# TAB 6 — Proveedores
# ──────────────────────────────────────────────────────────────────────────────
with tab6:
    st.header("🤝 Proveedores")

    if df_proveedores.empty:
        empty_warning("proveedores")
    else:
        total_prov = len(df_proveedores)
        con_tel = (
            df_proveedores["Telefono"].dropna().astype(str).str.strip().ne("").sum()
            if "Telefono" in df_proveedores.columns else 0
        )
        tipo_principal = (
            df_proveedores["Tipo de proveedor"].mode().iloc[0]
            if "Tipo de proveedor" in df_proveedores.columns
            and not df_proveedores["Tipo de proveedor"].dropna().empty
            else "N/A"
        )

        m1, m2, m3 = st.columns(3)
        m1.metric("👥 Total Proveedores", total_prov)
        m2.metric("📞 Con Teléfono", int(con_tel))
        m3.metric("🏷️ Tipo Principal", tipo_principal)

        st.markdown("---")

        f1, f2 = st.columns(2)
        with f1:
            busqueda = st.text_input("🔍 Buscar proveedor", key="prov_search")
        with f2:
            tipos = (
                df_proveedores["Tipo de proveedor"].dropna().unique().tolist()
                if "Tipo de proveedor" in df_proveedores.columns else []
            )
            sel_tipo = st.multiselect("Filtrar por Tipo", tipos, default=tipos, key="prov_tipo")

        df_pv = df_proveedores.copy()
        if busqueda:
            mask = df_pv.apply(
                lambda row: busqueda.lower() in " ".join(row.astype(str)).lower(), axis=1
            )
            df_pv = df_pv[mask]
        if sel_tipo and "Tipo de proveedor" in df_pv.columns:
            df_pv = df_pv[df_pv["Tipo de proveedor"].isin(sel_tipo)]

        if df_pv.empty:
            st.warning("No se encontraron proveedores.")
        else:
            c1, c2 = st.columns([2, 1])
            with c1:
                if "Tipo de proveedor" in df_pv.columns:
                    st.subheader("Proveedores por Tipo")
                    tipo_count = df_pv.groupby("Tipo de proveedor").size().reset_index(name="Cantidad")
                    fig = px.pie(
                        tipo_count, names="Tipo de proveedor", values="Cantidad", hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Set3,
                    )
                    fig.update_layout(template="plotly_dark", margin=dict(t=20))
                    fig.update_traces(textinfo="percent+label")
                    st.plotly_chart(fig, use_container_width=True)

            with c2:
                st.subheader("🏆 Más Usados en Pedidos")
                if not df_pedidos.empty and COL_P_PROVEEDOR in df_pedidos.columns:
                    top_prov = (
                        df_pedidos[COL_P_PROVEEDOR].value_counts().head(5).reset_index()
                    )
                    top_prov.columns = ["Proveedor", "Pedidos"]
                    for _, row in top_prov.iterrows():
                        st.markdown(f"**{row['Proveedor']}** — {row['Pedidos']} pedidos")
                else:
                    st.info("No hay datos de pedidos para cruzar.")

            st.markdown("---")

            st.subheader("📇 Detalle por Proveedor")
            for _, prov in df_pv.iterrows():
                nombre = prov.get("Proveedor", "Sin nombre")
                with st.expander(f"🏢 {nombre}"):
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        st.markdown(f"**Tipo:** {prov.get('Tipo de proveedor', 'N/A')}")
                        st.markdown(f"**Contacto:** {prov.get('Contacto', 'N/A')}")
                        st.markdown(f"**Teléfono:** {prov.get('Telefono', 'N/A')}")
                    with ec2:
                        st.markdown(f"**Sitio Web:** {prov.get('Sitio web', 'N/A')}")
                        st.markdown(f"**Confiabilidad:** {prov.get('Confiabilidad', 'N/A')}")
                        st.markdown(f"**Notas:** {prov.get('Notas', 'N/A')}")

            st.markdown("---")

            st.subheader("📋 Vista de Tabla")
            st.dataframe(
                df_pv, use_container_width=True, hide_index=True,
                column_config={
                    "Sitio web": st.column_config.LinkColumn("Sitio Web"),
                    "Confiabilidad": st.column_config.TextColumn("Confiabilidad"),
                },
            )

            csv = df_pv.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Descargar CSV", csv, "proveedores_moraes.csv", "text/csv", key="dl_prov",
            )


# ── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption("Dashboard MORAES • Datos actualizados desde Google Sheets cada 60 segundos")
