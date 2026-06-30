"""Envío de mensajes a Telegram con chunking y reintentos.

Arregla dos problemas de la V2:
  - app.py armaba un único mensaje gigante que superaba el límite de 4096
    caracteres de Telegram y fallaba.
  - telegram_bot.py no troceaba ni reintentaba.
"""

from __future__ import annotations

import time

from radar import config
from radar.logging_setup import get_logger

logger = get_logger("notify.telegram")

_LIMITE = 3900  # margen bajo el límite real de 4096


def _trozos(texto: str) -> list[str]:
    """Divide respetando saltos de línea cuando se puede."""
    partes: list[str] = []
    actual = ""
    for linea in (texto or "").split("\n"):
        if len(actual) + len(linea) + 1 > _LIMITE:
            if actual:
                partes.append(actual)
            # línea individual demasiado larga -> cortar duro
            while len(linea) > _LIMITE:
                partes.append(linea[:_LIMITE])
                linea = linea[_LIMITE:]
            actual = linea
        else:
            actual = f"{actual}\n{linea}" if actual else linea
    if actual:
        partes.append(actual)
    return partes or [""]


def enviar(texto: str, parse_mode: str = "HTML") -> bool:
    if not config.is_telegram_configured():
        logger.warning("Telegram no configurado; mensaje no enviado.")
        return False

    try:
        import requests  # import diferido
    except ImportError:
        logger.error("requests no instalado; no se puede enviar a Telegram.")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    ok_total = True

    for parte in _trozos(texto):
        enviado = False
        for intento in range(1, 4):
            try:
                r = requests.post(
                    url,
                    json={
                        "chat_id": config.TELEGRAM_CHAT_ID,
                        "text": parte,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True,
                    },
                    timeout=30,
                )
                if r.ok:
                    enviado = True
                    break
                logger.warning("Telegram %s: %s", r.status_code, r.text[:200])
            except Exception as e:  # noqa: BLE001
                logger.warning("Telegram intento %s falló: %s", intento, e)
            time.sleep(2 * intento)
        ok_total = ok_total and enviado

    return ok_total
