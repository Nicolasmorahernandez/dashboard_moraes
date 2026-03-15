"""
utils/amazon_client.py
======================
Cliente reutilizable de Amazon SP-API para todos los scripts de MORAES.
Importar desde cualquier script con:
    from utils.amazon_client import get_orders_api, get_finances_api, CREDENTIALS
"""

import os
from dotenv import load_dotenv
from sp_api.base import Marketplaces

load_dotenv()

# ─── Credenciales desde .env ──────────────────────────────────────────────────

CREDENTIALS = {
    "refresh_token": os.getenv("AMAZON_REFRESH_TOKEN"),
    "lwa_app_id": os.getenv("AMAZON_CLIENT_ID"),
    "lwa_client_secret": os.getenv("AMAZON_CLIENT_SECRET"),
}

SELLER_ID = os.getenv("AMAZON_SELLER_ID")
MARKETPLACE = Marketplaces.US  # Solo USA según configuración de Moraes Leather


# ─── Validación ───────────────────────────────────────────────────────────────

def validate_credentials() -> bool:
    """
    Verifica que todas las credenciales estén configuradas.
    Devuelve True si todo está bien, lanza ValueError si falta algo.
    """
    missing = []
    for key, val in CREDENTIALS.items():
        if not val:
            missing.append(key)
    if not SELLER_ID:
        missing.append("AMAZON_SELLER_ID")

    if missing:
        raise ValueError(
            f"Faltan credenciales en .env: {', '.join(missing)}\n"
            "Revisa el archivo .env en la carpeta del proyecto."
        )
    return True


# ─── Factories de APIs ────────────────────────────────────────────────────────

def get_orders_api():
    """Devuelve una instancia de la API de Orders."""
    from sp_api.api import Orders
    return Orders(credentials=CREDENTIALS, marketplace=MARKETPLACE)


def get_finances_api():
    """Devuelve una instancia de la API de Finances."""
    from sp_api.api import Finances
    return Finances(credentials=CREDENTIALS, marketplace=MARKETPLACE)


def get_reports_api():
    """Devuelve una instancia de la API de Reports."""
    from sp_api.api import Reports
    return Reports(credentials=CREDENTIALS, marketplace=MARKETPLACE)


def get_catalog_api():
    """Devuelve una instancia de la API de Catalog Items."""
    from sp_api.api import CatalogItems
    return CatalogItems(credentials=CREDENTIALS, marketplace=MARKETPLACE)


def get_pricing_api():
    """Devuelve una instancia de la API de Product Pricing."""
    from sp_api.api import ProductPricing
    return ProductPricing(credentials=CREDENTIALS, marketplace=MARKETPLACE)
