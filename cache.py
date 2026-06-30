"""Caché simple en disco con TTL (para búsquedas de precios repetidas)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from radar.config import CACHE_DIR, CACHE_TTL_HOURS
from radar.logging_setup import get_logger

logger = get_logger("store.cache")


def _path(key: str):
    h = hashlib.sha256(str(key).strip().lower().encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{h}.json"


def get(key: str):
    path = _path(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if datetime.now() > datetime.fromisoformat(payload["expires_at"]):
            path.unlink(missing_ok=True)
            return None
        return payload.get("value")
    except Exception as e:  # noqa: BLE001
        logger.debug("Cache inválida %s: %s", key, e)
        return None


def set(key: str, value) -> bool:  # noqa: A001
    payload = {
        "key": key,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=CACHE_TTL_HOURS)).isoformat(),
        "value": value,
    }
    try:
        _path(key).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug("No se pudo cachear %s: %s", key, e)
        return False
