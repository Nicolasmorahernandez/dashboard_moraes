# CLAUDE.md

## Qué es

Dashboard financiero de MORAES Leather Goods (venta de artículos de cuero por Amazon y canal directo). Streamlit + Plotly, lee datos en vivo de Google Sheets. Desplegado en Streamlit Cloud: https://dashboardmoraes26.streamlit.app

## Stack

Python / Streamlit / Plotly / gspread / pandas. Sin base de datos: la fuente de verdad son dos Google Sheets (IDs en `constants.py`, con override vía `st.secrets`).

## Estructura

- `app.py` — todo el layout: CSS (tema oscuro "cuero", reglas mobile atadas al DOM de Streamlit), KPIs, P&L en cascada, desglose por canal, inventario, gráficos. Español en UI y nombres de variables.
- `data.py` — funciones `cargar_*` (una por pestaña del Sheet, `@st.cache_data(ttl=300)`) y `ajustar_inventario_con_ventas`.
- `auth.py` — `autenticar()`: service account desde `st.secrets` (Cloud), o token OAuth local (`token.pickle` / `credentials.json`, gitignoreados).
- `constants.py` — IDs de los Sheets y `SKU_MAP` (SKUs de Amazon → SKU interno).
- `crear_hoja_costos.py` — script one-off que crea la hoja "Costos Amazon" de auditoría.

## Fuentes de datos (Google Sheets)

1. **"flujo de cajas"** (`SHEET_FINANZAS_ID`): pestañas Gastos Operativos, Ventas, Márgenes, Inventario. Las cabeceras reales empiezan en filas distintas (`head=2..4` según pestaña) y hay filas de totales/leyendas que se filtran a mano.
2. **Sheet Amazon** (`SHEET_AMAZON_ID`): Ventas Amazon y Gastos Amazon (fees, montos negativos).

## Decisiones clave

- **Stock dinámico** (jul 2026): el stock mostrado es `Comprado` (pestaña Inventario) − unidades vendidas por SKU sumando ambas hojas de Ventas; las columnas `Vendido` y `Stock (ajustable)` del Sheet son solo referencia manual del dueño. Motivo: el stock manual quedaba desactualizado. Implica que toda venta debe registrarse en las hojas de Ventas.
- **Doble escenario**: toggle "Proyectado" (asume todo cobrado/pagado) vs caja real (`Cobrado` en ventas, `Pagado` en gastos).
- **Atribución de canal**: gastos con Canal "Ambos" se reparten proporcional al ingreso de cada canal.
- Los montos llegan como texto con `$`/`,` y se limpian con regex en cada `cargar_*`.

## Comandos

- Correr local: `streamlit run app.py` (necesita `credentials.json` OAuth; no hay credenciales en el repo).
- No hay tests ni linter configurados. Deploy = push a `main` (Streamlit Cloud redespliega solo).

## Convenciones

- Commits estilo conventional (`feat:`, `style(mobile):`, …), mensajes en español o inglés indistinto.
- Variables con prefijo `_` para cálculos intermedios de una sección.
- El CSS mobile depende de clases internas del DOM de Streamlit (frágil ante upgrades de Streamlit).
