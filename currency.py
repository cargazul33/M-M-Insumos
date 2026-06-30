"""Conversión de moneda a ARS.

Soporta override por env (USD_TO_ARS / PYG_TO_ARS) y, si FX_LIVE=1, intenta
una cotización en vivo del dólar con caché y fallback al valor configurado.
"""

from __future__ import annotations

import re

from radar import config
from radar.logging_setup import get_logger

logger = get_logger("pricing.currency")

_fx_cache: dict[str, float] = {}


def usd_to_ars() -> float:
    if not config.FX_LIVE:
        return config.USD_TO_ARS
    if "usd" in _fx_cache:
        return _fx_cache["usd"]
    try:
        import requests  # import diferido

        r = requests.get(
            "https://dolarapi.com/v1/dolares/blue", timeout=config.REQUEST_TIMEOUT
        )
        if r.ok:
            valor = float(r.json().get("venta") or 0)
            if valor > 0:
                _fx_cache["usd"] = valor
                logger.info("FX en vivo USD->ARS: %.2f", valor)
                return valor
    except Exception as e:  # noqa: BLE001
        logger.warning("FX en vivo falló (%s); uso valor fijo %.2f", e, config.USD_TO_ARS)
    return config.USD_TO_ARS


def limpiar_numero(valor) -> float | None:
    valor = re.sub(r"[^\d,\.]", "", str(valor or ""))
    valor = valor.strip(".,")  # quita puntos/comas sueltos de los bordes (ej. "Gs.")
    if not valor:
        return None
    if "." in valor and "," in valor:
        # Formato AR/PY: punto miles, coma decimal -> 1.250.000,50
        valor = valor.replace(".", "").replace(",", ".")
    elif "," in valor:
        valor = valor.replace(",", ".")
    elif "." in valor:
        # Punto(s): si los grupos tras el primero son de 3 dígitos, son miles
        # (400.000 -> 400000 ; 1.250.000 -> 1250000). Si no, es decimal (400.50).
        partes = valor.split(".")
        if all(len(p) == 3 for p in partes[1:]):
            valor = valor.replace(".", "")
    try:
        return float(valor)
    except ValueError:
        return None


def detectar_moneda(texto) -> str:
    t = str(texto or "").upper()
    if any(x in t for x in ("GS", "PYG", "GUARANI", "GUARANÍ", "₲")):
        return "PYG"
    if any(x in t for x in ("USD", "U$S", "US$")):
        return "USD"
    return "ARS"


def convertir_a_ars(precio) -> int | None:
    numero = limpiar_numero(precio)
    if numero is None:
        return None
    moneda = detectar_moneda(precio)
    if moneda == "PYG":
        return round(numero * config.PYG_TO_ARS)
    if moneda == "USD":
        return round(numero * usd_to_ars())
    return round(numero)


def precio_legible(precio) -> str:
    ars = convertir_a_ars(precio)
    if ars is None:
        return "-"
    return f"${ars:,.0f}".replace(",", ".")
