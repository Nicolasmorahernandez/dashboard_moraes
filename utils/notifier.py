"""
utils/notifier.py
=================
Utilidades de notificacion compartidas para todos los scripts de MORAES.

Uso:
    from utils.notifier import send_telegram

    send_telegram("Tu mensaje aqui")
"""

import os
import logging
import requests

log = logging.getLogger(__name__)


def send_telegram(message: str, token: str = None, chat_id: str = None) -> bool:
    """
    Envia mensaje via Telegram Bot API.
    Lee TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID del .env si no se pasan.
    Retorna True si el envio fue exitoso.
    """
    token   = token   or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log.warning(
            "Telegram no configurado. "
            "Agrega TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID al .env"
        )
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            log.info("Notificacion enviada por Telegram.")
            return True
        else:
            log.error(f"Error Telegram ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        log.error(f"Error enviando Telegram: {e}")
        return False
