# Dashboard MORAES

Dashboard interactivo de analítica financiera para **MORAES**, construido con Streamlit, conectado en tiempo real a Google Sheets y visualizado con Plotly. Incluye un sistema de automatizaciones que sincroniza datos desde Amazon SP-API y genera reportes automáticos.

![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-ff4b4b?style=flat-square&logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-5.0+-3f4f75?style=flat-square&logo=plotly&logoColor=white)
![Google Sheets](https://img.shields.io/badge/Google%20Sheets-API-34a853?style=flat-square&logo=google-sheets&logoColor=white)
![Amazon SP-API](https://img.shields.io/badge/Amazon%20SP--API-FF9900?style=flat-square&logo=amazon&logoColor=white)

---

## Características

- **Conexión en tiempo real** con Google Sheets (actualización cada 60 segundos)
- **7 pestañas de análisis** con visualizaciones interactivas
- **Sistema de automatizaciones** con 7 scripts programados via Windows Task Scheduler
- **Sincronización Amazon SP-API** — ventas, gastos, inventario y estado de órdenes
- **Reportes automáticos** — semanal y mensual P&L enviados por Email (PDF) + Telegram
- **Diseño profesional** con tema oscuro personalizado y paleta de colores coherente
- **Filtros dinámicos** por producto, canal de venta, estado, mes y más
- **Exportación CSV** de datos filtrados

---

## Pestañas del Dashboard

| Pestaña | Descripción |
|---------|-------------|
| **📈 Panel General** | KPIs principales (ventas, gastos, ganancia neta, ticket promedio), gráfico ventas vs gastos, top 3 productos, distribución de gastos |
| **💰 Rentabilidad** | ROI y MARGIN por producto/canal, scatter ROI vs MARGIN, tabla detallada |
| **🔀 Canales de Venta** | Comparativa FBA vs FBM vs Directo, métricas por canal, ganancia vs costo |
| **📦 Pedidos e Inventario** | Estado de pedidos al proveedor, inversión, timeline de llegadas |
| **🏷️ Costos por Producto** | Estructura de costos, distribución por canal, desglose individual |
| **🤝 Proveedores** | Directorio de proveedores, contactos, ranking de uso y confiabilidad |
| **📦 Órdenes Amazon** | Estado en tiempo real de órdenes Amazon (Enviado/Entregado/Pendiente/Cancelado), gráficos por estado y semana |

---

## Automatizaciones

Scripts en `automations/` ejecutados por Windows Task Scheduler:

| Script | Trigger | Descripción |
|--------|---------|-------------|
| `sync_amazon_sheets.py` | Diario 7 AM | Sincroniza ventas Amazon → hoja "Ventas Amazon" |
| `sync_gastos_amazon.py` | Diario 7 AM | Sincroniza fees Amazon → hoja "Gastos Amazon" |
| `sync_pedidos.py` | Diario 7 AM | Sincroniza estado de órdenes → hoja "Ordenes Amazon" (actualiza estado en tiempo real) |
| `inventory_alerts.py` | Diario 8 AM | Alerta por email + Telegram cuando stock FBA cae bajo umbral |
| `update_modelo_rentabilidad.py` | Lunes 10 AM | Actualiza rentabilidad real por SKU desde datos Amazon |
| `weekly_report.py` | Lunes 7 AM | Reporte semanal P&L — PDF por email + resumen Telegram |
| `monthly_report.py` | Día 1 de cada mes, 8 AM | Reporte mensual P&L — comparativa vs mes anterior, YTD, rentabilidad por SKU, inventario crítico |

---

## Tecnologías

- **[Streamlit](https://streamlit.io/)** — Framework de dashboards en Python
- **[Plotly Express](https://plotly.com/python/plotly-express/)** — Gráficos interactivos
- **[gspread](https://gspread.readthedocs.io/)** — Cliente de Google Sheets para Python
- **[Pandas](https://pandas.pydata.org/)** — Manipulación y análisis de datos
- **[python-amazon-sp-api](https://github.com/saleweaver/python-amazon-sp-api)** — Cliente Amazon SP-API
- **[fpdf2](https://pyfpdf.github.io/fpdf2/)** — Generación de PDFs
- **[Google Auth](https://google-auth.readthedocs.io/)** — Autenticación con Service Account

---

## Instalación

### Requisitos previos

- Python 3.10 o superior
- Credenciales de Google Cloud (Service Account con acceso a Sheets + Drive)
- Credenciales de Amazon SP-API (para las automatizaciones)

### Pasos

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/Nicolasmorahernandez/dashboard_moraes.git
   cd dashboard_moraes
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurar credenciales Google:**
   - Crear un proyecto en [Google Cloud Console](https://console.cloud.google.com/)
   - Habilitar las APIs de Google Sheets y Google Drive
   - Crear una Service Account y descargar el JSON → renombrar a `service_account.json`
   - Compartir el Google Sheet "Finanzas MORAES" con el email de la Service Account

4. **Configurar variables de entorno (`.env`):**
   ```env
   # Amazon SP-API
   SP_API_REFRESH_TOKEN=...
   LWA_APP_ID=...
   LWA_CLIENT_SECRET=...
   SP_API_SELLER_ID=...

   # Notificaciones
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   GMAIL_USER=...
   GMAIL_APP_PASSWORD=...
   ```

5. **Primer uso de automatizaciones:**
   ```bash
   # Crear hojas en Google Sheets
   python automations/setup_amazon_sheet.py
   python automations/sync_pedidos.py --setup
   python automations/update_modelo_rentabilidad.py --setup

   # Poblar con histórico
   python automations/sync_amazon_sheets.py --days 90
   python automations/sync_gastos_amazon.py --days 90
   python automations/sync_pedidos.py --days 90
   ```

6. **Ejecutar el dashboard:**
   ```bash
   streamlit run dashboard_moraes.py
   ```

---

## Deploy en Streamlit Cloud

1. Subir el código a GitHub (sin `service_account.json` ni `.env`)
2. Ir a [share.streamlit.io](https://share.streamlit.io/) y conectar el repositorio
3. En **Settings > Secrets**, agregar las credenciales:
   ```toml
   [gcp_service_account]
   type = "service_account"
   project_id = "tu-proyecto"
   private_key_id = "..."
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "tu-service-account@tu-proyecto.iam.gserviceaccount.com"
   client_id = "..."
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
   ```

---

## Estructura del Proyecto

```
dashboard_moraes/
├── automations/
│   ├── setup_amazon_sheet.py          # Setup inicial de hojas Amazon
│   ├── sync_amazon_sheets.py          # Sync ventas diario (SP-API -> Sheets)
│   ├── sync_gastos_amazon.py          # Sync fees diario (SP-API -> Sheets)
│   ├── sync_pedidos.py                # Sync estado de ordenes (SP-API -> Sheets)
│   ├── inventory_alerts.py            # Alertas stock FBA bajo umbral
│   ├── update_modelo_rentabilidad.py  # Actualiza rentabilidad real por SKU
│   ├── weekly_report.py               # Reporte semanal PDF + Telegram
│   └── monthly_report.py              # Reporte mensual P&L PDF + Telegram
├── utils/
│   ├── amazon_client.py               # Credenciales y cliente SP-API
│   ├── sheets_client.py               # Cliente reutilizable Google Sheets
│   └── notifier.py                    # Notificaciones Telegram compartidas
├── dashboard_moraes.py                # Dashboard principal Streamlit
├── requirements.txt                   # Dependencias Python
├── service_account.json               # Credenciales Google (NO en git)
├── .env                               # Variables de entorno (NO en git)
└── README.md
```

---

## Estructura del Google Sheet ("Finanzas MORAES")

| Hoja | Descripción | Headers en |
|------|-------------|-----------|
| **Vendidos** | Dos tablas lado a lado: ventas (B-I) y gastos/costos (N-U) | Fila 3 |
| **Modelo Unitario de Rentabilidad** | Costos teóricos por producto y canal | Fila 1 |
| **Modelo Unitario Rentabilidad - Amazon** | Rentabilidad real calculada desde SP-API | Fila 2 |
| **Ventas Amazon** | Órdenes sincronizadas desde SP-API (append-only) | Fila 3 |
| **Gastos Amazon** | Fees Amazon sincronizados desde SP-API | Fila 2 |
| **Ordenes Amazon** | Estado en tiempo real de órdenes (actualización diaria) | Fila 3 |
| **Pedidos** | Pedidos al proveedor (manual) | Fila 3 |
| **Inventario** | Stock FBA actualizado por inventory_alerts.py | Fila 1 |
| **proveedores** | Directorio de proveedores (manual) | Fila 1 |

---

## Seguridad

- `service_account.json` y `.env` **nunca** se suben al repositorio (.gitignore)
- En Streamlit Cloud se usan [Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- Las automatizaciones leen credenciales exclusivamente desde `.env`

---

## Licencia

Este proyecto es de uso privado para MORAES.

---

Desarrollado por [Nicolas Mora](https://github.com/Nicolasmorahernandez)
