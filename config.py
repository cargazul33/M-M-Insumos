"""Configuración central de Radar M&M.

Aquí se resuelve UN bug crítico de la V2: el nombre de los secrets no coincidía
entre el workflow de GitHub, config.py y telegram_bot.py. Ahora cada credencial
se lee desde un nombre canónico, pero se aceptan también los alias históricos,
así nada se rompe sin importar cómo estén cargados los secrets.
"""

from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "Radar M&M"
APP_VERSION = "V26.0"


def _env(*names: str, default: str = "") -> str:
    """Devuelve la primera variable de entorno no vacía entre `names`."""
    for name in names:
        val = os.getenv(name)
        if val and val.strip():
            return val.strip()
    return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    val = _env(name).lower()
    if not val:
        return default
    return val in {"1", "true", "yes", "y", "si", "sí", "on"}


# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
CACHE_DIR = DATA_DIR / "cache"
HISTORY_DIR = DATA_DIR / "history"
LOGS_DIR = DATA_DIR / "logs"
REPORTS_DIR = DATA_DIR / "reports"
DB_PATH = DATA_DIR / "radar.sqlite"

for _folder in (DOWNLOADS_DIR, CACHE_DIR, HISTORY_DIR, LOGS_DIR, REPORTS_DIR):
    _folder.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Credenciales (canónico + alias histórico)
# --------------------------------------------------------------------------- #
CODI_USER = _env("CODI_USER")
CODI_PASS = _env("CODI_PASS", "CODI_PASSWORD")  # canónico: CODI_PASS

TELEGRAM_TOKEN = _env("TELEGRAM_TOKEN", "TELEGRAM_BOT_TOKEN")  # canónico: TELEGRAM_TOKEN
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")

GMAIL_USER = _env("GMAIL_USER")
GMAIL_APP_PASSWORD = _env("GMAIL_APP_PASSWORD")
SAFIPRO_EMAIL = _env("SAFIPRO_EMAIL", default="safipro_no_responder@neuquen.gov.ar")

# Brave Search API (GitHub Secret canónico: BRAVE_API_KEY)
BRAVE_API_KEY = _env("BRAVE_API_KEY")
BRAVE_SEARCH_COUNT = _env_int("BRAVE_SEARCH_COUNT", 6)
BRAVE_FETCH_LIMIT = _env_int("BRAVE_FETCH_LIMIT", 2)
BRAVE_ALWAYS_SEARCH = _env_bool("BRAVE_ALWAYS_SEARCH", default=True)
SEARCH_QUERY_VARIANTS = _env_int("SEARCH_QUERY_VARIANTS", 6)


# --------------------------------------------------------------------------- #
# URLs CO.DI.NEU
# --------------------------------------------------------------------------- #
CODI_BASE = "https://codi.neuquen.gob.ar/PortalLicitaciones/servlet/"
CODI_LOGIN_URL = _env(
    "CODI_LOGIN_URL",
    default=CODI_BASE + "com.portallicitaciones.seguridad.login",
)
CODI_LICITACIONES_URL = _env(
    "CODI_LICITACIONES_URL",
    default=CODI_BASE + "com.portallicitaciones.wwlicitacion",
)


# --------------------------------------------------------------------------- #
# Parámetros de ejecución
# --------------------------------------------------------------------------- #
TOP_LIMIT = _env_int("TOP_LIMIT", 3)            # oportunidades a detallar a fondo
SCAN_MAX_FILAS = _env_int("SCAN_MAX_FILAS", 200)
ITEMS_POR_PDF = _env_int("ITEMS_POR_PDF", 3)
PRICE_HUNTER_LIMIT = _env_int("PRICE_HUNTER_LIMIT", 3)
REQUEST_TIMEOUT = _env_int("REQUEST_TIMEOUT", 25)
CACHE_TTL_HOURS = _env_int("CACHE_TTL_HOURS", 12)
HEADLESS = _env_bool("HEADLESS", default=True)

# Si está en True, no se reenvían oportunidades ya notificadas en corridas previas.
DEDUPE = _env_bool("DEDUPE", default=True)


# --------------------------------------------------------------------------- #
# Crawl profundo (modo --full): recorrer TODAS las páginas y bajar TODO
# --------------------------------------------------------------------------- #
CRAWL_MAX_PAGINAS = _env_int("CRAWL_MAX_PAGINAS", 100)   # tope de seguridad
CRAWL_SLEEP_MS = _env_int("CRAWL_SLEEP_MS", 800)         # pausa entre requests (cortesía)
CRAWL_MAX_DOCS_POR_LIC = _env_int("CRAWL_MAX_DOCS_POR_LIC", 20)
DOWNLOAD_ALL_DOCS = _env_bool("DOWNLOAD_ALL_DOCS", default=True)
# Precio acotado en el crawl: cuántos renglones (de las mejores licitaciones) cotizar.
FULL_PRICE_LIMIT = _env_int("FULL_PRICE_LIMIT", 30)
# Selector del control "página siguiente". Si lo seteás, se usa primero.
CODI_NEXT_SELECTOR = _env("CODI_NEXT_SELECTOR")
# Cuántas oportunidades importantes mandar por Telegram en el modo full.
FULL_TELEGRAM_TOP = _env_int("FULL_TELEGRAM_TOP", 10)


# --------------------------------------------------------------------------- #
# Tipos de cambio (override por env; opción de FX en vivo en pricing.currency)
# --------------------------------------------------------------------------- #
USD_TO_ARS = _env_float("USD_TO_ARS", 1550.0)
PYG_TO_ARS = _env_float("PYG_TO_ARS", 0.22)
FX_LIVE = _env_bool("FX_LIVE", default=False)   # intentar cotización en vivo


# --------------------------------------------------------------------------- #
# User-Agent realista para scraping
# --------------------------------------------------------------------------- #
USER_AGENT = _env(
    "USER_AGENT",
    default=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
)


# --------------------------------------------------------------------------- #
# Helpers de estado
# --------------------------------------------------------------------------- #
def is_codi_configured() -> bool:
    return bool(CODI_USER and CODI_PASS)


def is_telegram_configured() -> bool:
    return bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)


def is_gmail_configured() -> bool:
    return bool(GMAIL_USER and GMAIL_APP_PASSWORD)


def is_brave_configured() -> bool:
    return bool(BRAVE_API_KEY)


def status_resumen() -> str:
    """Una línea legible con el estado de configuración (sin filtrar secretos)."""
    def ok(flag: bool) -> str:
        return "OK" if flag else "FALTA"

    return (
        f"CODI={ok(is_codi_configured())} | "
        f"Telegram={ok(is_telegram_configured())} | "
        f"Gmail={ok(is_gmail_configured())} | "
        f"Brave={ok(is_brave_configured())}"
    )
