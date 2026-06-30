"""Deduplicación de oportunidades entre corridas (evita spam en Telegram).

En la V2 este módulo existía pero nunca se llamaba, así que cada corrida
reenviaba todo. Acá se integra al pipeline.
"""

from __future__ import annotations

import hashlib
import json

from radar.config import HISTORY_DIR

_SEEN_FILE = HISTORY_DIR / "seen.json"


def _id(op: dict) -> str:
    base = f"{op.get('texto', '')[:200]}|{op.get('visualizar_url', '')}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def cargar_vistos() -> set[str]:
    if not _SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(_SEEN_FILE.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return set()


def guardar_vistos(vistos: set[str]) -> None:
    _SEEN_FILE.write_text(
        json.dumps(sorted(vistos), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def filtrar_nuevas(oportunidades: list[dict]) -> list[dict]:
    """Devuelve solo las oportunidades no vistas y actualiza el registro."""
    vistos = cargar_vistos()
    nuevas = []
    for op in oportunidades:
        oid = _id(op)
        if oid in vistos:
            continue
        nuevas.append(op)
        vistos.add(oid)
    guardar_vistos(vistos)
    return nuevas
