# 📊 Dashboard MORAES

Dashboard interactivo de analítica financiera para **MORAES**, construido con Streamlit, conectado en tiempo real a Google Sheets y visualizado con Plotly.

![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-ff4b4b?style=flat-square&logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-5.0+-3f4f75?style=flat-square&logo=plotly&logoColor=white)
![Google Sheets](https://img.shields.io/badge/Google%20Sheets-API-34a853?style=flat-square&logo=google-sheets&logoColor=white)

---

## 🚀 Características

- **Conexión en tiempo real** con Google Sheets (actualización cada 60 segundos)
- **6 pestañas de análisis** con visualizaciones interactivas
- **Diseño profesional** con tema oscuro personalizado y paleta de colores coherente
- **Filtros dinámicos** por producto, canal de venta, estado y más
- **Gráficos interactivos** con Plotly (barras, pastel, scatter, timeline)
- **Exportación CSV** de datos filtrados
- **Detección inteligente** de headers offset y formatos monetarios/porcentuales
- **Responsive** y optimizado para pantallas amplias

## 📋 Pestañas del Dashboard

| Pestaña | Descripción |
|---------|-------------|
| **📈 Panel General** | KPIs principales (ventas, gastos, ganancia neta, ticket promedio), gráfico de ventas vs gastos, top 3 productos, distribución de gastos |
| **💰 Rentabilidad** | ROI y MARGIN por producto/canal, scatter ROI vs MARGIN, tabla detallada, mejor/peor ROI |
| **🔀 Canales de Venta** | Comparativa FBA vs FBM vs Directo, métricas por canal, ganancia vs costo, distribución de productos e ingresos |
| **📦 Pedidos e Inventario** | Estado de pedidos, inversión por producto, timeline de llegadas, unidades por producto |
| **🏷️ Costos por Producto** | Estructura de costos, distribución por canal, desglose individual, tabla exportable |
| **🤝 Proveedores** | Directorio de proveedores, clasificación por tipo, ranking de uso en pedidos, fichas detalladas |

## 🛠️ Tecnologías

- **[Streamlit](https://streamlit.io/)** — Framework de dashboards en Python
- **[Plotly Express](https://plotly.com/python/plotly-express/)** — Gráficos interactivos
- **[gspread](https://gspread.readthedocs.io/)** — Cliente de Google Sheets para Python
- **[Pandas](https://pandas.pydata.org/)** — Manipulación y análisis de datos
- **[Google Auth](https://google-auth.readthedocs.io/)** — Autenticación con Service Account

## 📦 Instalación

### Requisitos previos

- Python 3.10 o superior
- Credenciales de Google Cloud (Service Account con acceso a Google Sheets API)

### Pasos

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/Nicolasmorahernandez/dashboard_moraes.git
   cd dashboard_moraes
   ```

2. **Crear entorno virtual (recomendado):**
   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux/Mac
   venv\Scripts\activate           # Windows
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar credenciales:**
   - Crear un proyecto en [Google Cloud Console](https://console.cloud.google.com/)
   - Habilitar las APIs de Google Sheets y Google Drive
   - Crear una Service Account y descargar el archivo JSON
   - Renombrar el archivo a `service_account.json` y colocarlo en la raíz del proyecto
   - Compartir el Google Sheet "Finanzas MORAES" con el email de la Service Account

5. **Ejecutar el dashboard:**
   ```bash
   streamlit run dashboard_moraes.py
   ```

## ☁️ Deploy en Streamlit Cloud

1. Subir el código a GitHub (sin `service_account.json`)
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

## 📁 Estructura del Proyecto

```
dashboard_moraes/
├── .streamlit/
│   └── config.toml          # Configuración del tema Streamlit
├── dashboard_moraes.py       # Código principal del dashboard
├── requirements.txt          # Dependencias de Python
├── service_account.json      # Credenciales (NO incluido en git)
├── .gitignore                # Archivos excluidos del repositorio
└── README.md                 # Este archivo
```

## 📊 Estructura del Google Sheet

El dashboard espera un Google Sheet llamado **"Finanzas MORAES"** con las siguientes hojas:

### Vendidos
Contiene **dos tablas lado a lado**:
- **Tabla de Ventas** (columnas B-I): Producto, Categoría, Fecha de Venta, Cantidad Vendida, Precio Unitario (USD), Ingreso Total (USD), Método de Pago, ¿En Stock?
- **Tabla de Gastos** (columnas N-U): Descripción del Costo, Categoría del Gasto, Fecha de Pago, Monto (USD), Método de Pago, Producto Asociado/Referencia, ¿Pagado?, Proveedor

> **Nota:** Los headers reales están en la **fila 3**, no en la fila 1.

### Modelo Unitario de Rentabilidad
Producto, Método de venta, Precio de compra (COP/USD), Envío, Empaque, Publicidad, Comisión, Costo Total, Precio de venta (USD), Ganancias (USD), MARGIN, ROI

### Pedidos
Referencia del Pedido, Producto, Proveedor, Cantidad Solicitada, Costo Unitario (COP), Costo Unitario Estimado (USD), Costo Total Estimado (USD), Fecha Estimada de Llegada, ¿Pedido Confirmado?

> **Nota:** Los headers reales están en la **fila 3**.

### proveedores
Proveedor, Tipo de proveedor, Contacto, Telefono, Sitio web, Confiabilidad, Notas

## 🎨 Paleta de Colores

| Color | Hex | Uso |
|-------|-----|-----|
| 🔵 Primario | `#1e3a8a` | Headers, elementos principales |
| 🔵 Primario Claro | `#3b82f6` | Gráficos, acentos interactivos |
| 🟢 Secundario | `#10b981` | Valores positivos, ventas |
| 🟡 Acento | `#f59e0b` | Destacados, warnings |
| 🔴 Negativo | `#ef4444` | Gastos, pérdidas |
| ⬛ Fondo | `#0f172a` | Background principal |
| ⬛ Cards | `#1e293b` | Tarjetas y contenedores |

## 🔒 Seguridad

- Las credenciales de Google (`service_account.json`) **nunca** se suben al repositorio
- El archivo `.gitignore` excluye automáticamente archivos sensibles
- En Streamlit Cloud, se usan [Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management) para manejar credenciales

## 📝 Licencia

Este proyecto es de uso privado para MORAES.

---

Desarrollado con 💙 por [Nicolas Mora](https://github.com/Nicolasmorahernandez)
