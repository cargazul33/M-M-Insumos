"""Configuración de logging para Radar M&M."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from radar.config import APP_NAME, APP_VERSION, LOGS_DIR

_LOG_FILE = LOGS_DIR / "radar.log"
_CONFIGURED = False


def setup_logging(verbose: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if verbose else logging.INFO
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger("radar")
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        fileh = RotatingFileHandler(
            _LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        fileh.setFormatter(fmt)
        root.addHandler(fileh)
    except OSError:
        pass  # en CI a veces el FS es efímero; con consola alcanza

    _CONFIGURED = True
    root.debug("Logging inicializado para %s %s", APP_NAME, APP_VERSION)


def get_logger(name: str = "radar") -> logging.Logger:
    if not name.startswith("radar"):
        name = f"radar.{name}"
    return logging.getLogger(name)
