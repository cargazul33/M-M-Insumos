"""Watcher de alertas SAFIPRO por Gmail (IMAP).

Complementa al scan de CO.DI.NEU: a veces la alerta por mail llega antes de que
la licitación aparezca en el listado web.
"""

from __future__ import annotations

import re

from radar import config
from radar.logging_setup import get_logger
from radar.parsing.classifier import clasificar_licitacion

logger = get_logger("sources.gmail")


def _limpiar(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").replace("\r", " ").replace("\n", " ")).strip()


def _extraer(texto: str) -> dict:
    texto = _limpiar(texto)
    titulo = ""
    for p in (
        r"participar en la Licitaci[oó]n:\s*(.*?)(?:\.|,|$)",
        r"(Contrataci[oó]n Directa.*?\d+)",
        r"(Concurso de [Pp]recios.*?\d+)",
        r"(Licitaci[oó]n P[uú]blica.*?\d+)",
    ):
        m = re.search(p, texto, flags=re.I)
        if m:
            titulo = _limpiar(m.group(1))
            break
    numero = ""
    m = re.search(r"(?:Nro\.?|N°|n[uú]mero)?\s*[-:]?\s*(\d{2,5})", titulo, flags=re.I)
    if m:
        numero = m.group(1)
    return {"titulo": titulo or texto[:180], "numero": numero, "texto": texto}


def leer_alertas(max_emails: int = 25) -> list[dict]:
    if not config.is_gmail_configured():
        return []
    try:
        from imap_tools import AND, MailBox  # import diferido
    except ImportError:
        logger.warning("imap-tools no instalado; sin watcher Gmail.")
        return []

    alertas: list[dict] = []
    try:
        with MailBox("imap.gmail.com").login(
            config.GMAIL_USER, config.GMAIL_APP_PASSWORD, "INBOX"
        ) as mailbox:
            for msg in mailbox.fetch(
                AND(from_=config.SAFIPRO_EMAIL),
                reverse=True, limit=max_emails, mark_seen=False,
            ):
                if "Nueva Licitaci" not in (msg.subject or ""):
                    continue
                datos = _extraer(msg.text or msg.html or "")
                clasif = clasificar_licitacion(datos["titulo"])
                alertas.append(
                    {
                        "fecha": msg.date.strftime("%Y-%m-%d %H:%M"),
                        "titulo": datos["titulo"],
                        "numero": datos["numero"],
                        "decision": clasif.decision,
                        "puntaje": clasif.puntaje,
                    }
                )
    except Exception as e:  # noqa: BLE001
        logger.error("Error leyendo Gmail: %s", e)
    return alertas
