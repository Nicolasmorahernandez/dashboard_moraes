# Dashboard MORAES — Financiero

Dashboard financiero en tiempo real para **MORAES Leather Goods**, construido con Streamlit y conectado directamente a Google Sheets via OAuth.

![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-ff4b4b?style=flat-square&logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-5.18+-3f4f75?style=flat-square&logo=plotly&logoColor=white)
![Google Sheets](https://img.shields.io/badge/Google%20Sheets-API-34a853?style=flat-square&logo=google-sheets&logoColor=white)

---

## Características

- **P&L en cascada** — Ingresos → Margen de contribución → Utilidad operativa
- **Dos escenarios** — Toggle "Proyectado" (todo cobrado + gastos pendientes) vs. Caja real
- **Desglose por canal** — Amazon y Directo con rentabilidades reales, toggle "Con inversión pendiente"
- **Inventario en stock** — Capital a costo, valor a mercado, ganancia potencial por canal
- **Contabilidad accrual** — Columnas Canal, Tipo (Directo/Estructura) y ¿En inventario? en la hoja de gastos
- **Gráficos interactivos** — Ventas por canal, gastos por categoría, márgenes por SKU
- **Paleta cuero** — Diseño oscuro coherente con la marca MORAES

---

## Fuentes de datos

| Sheet | Contenido |
|---|---|
| `flujo de cajas` | Gastos Operativos, Ventas, Márgenes, Inventario |
| `Pedidos_Proveedor` | Historial de compras a proveedor (IMPORTRANGE) |
| `Amazon sheet` | Ventas Amazon, Gastos Amazon (fees) |

---

## Estructura del proyecto

```
dashboard/
├── app.py              # Dashboard principal (Streamlit)
├── requirements.txt    # Dependencias Python
├── crear_hoja_costos.py  # Script utilitario — crea hoja auditoría Amazon en Sheets
├── .gitignore
└── README.md
```

> **Credenciales OAuth** (`credentials.json`, `token.pickle`) están en `.gitignore` y nunca se suben al repo.

---

## Instalación

```bash
pip install -r requirements.txt
```

### Configurar credenciales Google OAuth

1. Descargá el `credentials.json` desde Google Cloud Console (OAuth 2.0)
2. Colocalo en la carpeta `dashboard/`
3. Al correr por primera vez, abre el navegador para autorizar

---

## Correr el dashboard

```bash
cd dashboard
streamlit run app.py
```

Abre en `localhost:8501` por defecto.

---

## Columnas clave en Google Sheets (Gastos Operativos)

| Columna | Valores | Propósito |
|---|---|---|
| `¿Pagado?` | ✅ / ⏳ | Caja real vs pendiente |
| `Canal` | Amazon / Directo / Ambos | Atribución por canal |
| `Tipo` | Directo / Estructura | COGS vs overhead empresa |
| `¿En inventario?` | Sí / No | Costo activo cuando se vende |

---

## Licencia

Uso interno MORAES Leather Goods © 2026
