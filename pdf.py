"""Lectura de PDFs de pliegos y detección de renglones.

`pypdf` se importa de forma diferida para que el resto del paquete funcione
(self-test, tests unitarios) aunque la dependencia no esté instalada.
"""

from __future__ import annotations

import re
from pathlib import Path

from radar.logging_setup import get_logger

logger = get_logger("parsing.pdf")


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").replace("\n", " ")).strip()


def leer_pdf(path: str | Path) -> str:
    try:
        from pypdf import PdfReader  # import diferido
    except ImportError:
        logger.warning("pypdf no instalado; no se puede leer %s", path)
        return ""
    try:
        reader = PdfReader(str(path))
        return _limpiar(" ".join((p.extract_text() or "") for p in reader.pages))
    except Exception as e:  # noqa: BLE001
        logger.error("Error leyendo PDF %s: %s", path, e)
        return ""


def _normalizar_item(t: str) -> str:
    t = _limpiar(t)
    for b in (
        r"^VER ANEXO\s+", r"^HP ORIGINAL\s+", r"^ORIGINAL\s+",
        r"^0\s*-\s*plazo\s*:\s*0\s*", r"^Cant Sol\s*",
    ):
        t = re.sub(b, "", t, flags=re.I)
    cortes = [
        "tracto sucesivo", "fch. ini", "prorrogable", "actuacion contable",
        "expediente electronico", "item cant ofr", "precio unitario",
        "precio total", "mantenimiento de oferta", "lugar de entrega",
    ]
    low = t.lower()
    posiciones = [low.find(c) for c in cortes if low.find(c) != -1]
    if posiciones:
        t = t[: min(posiciones)]
    t = re.sub(r"\s*-\s*Especificaci[oó]n Adicional:\s*$", "", t, flags=re.I)
    return _limpiar(t)


def _clave_item(t: str) -> str:
    t = re.sub(r"[^a-z0-9áéíóúñ]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()[:180]


def detectar_renglones(texto: str, maximo: int = 40) -> list[str]:
    texto = _limpiar(texto)
    encontrados: list[str] = []
    vistos: set[str] = set()

    patron = (
        r"([A-ZÁÉÍÓÚÑ0-9 /().-]{4,80};\s*.{20,520}?)"
        r"(?=\s+[A-ZÁÉÍÓÚÑ0-9 /().-]{4,80};|\s+Mantenimiento de oferta"
        r"|\s+Lugar de entrega|$)"
    )

    descartar = (
        "pliego de bases", "articulo", "decreto", "reglamento", "garantia",
        "presentacion de ofertas", "firma digital",
    )

    for m in re.findall(patron, texto, flags=re.S):
        item = _normalizar_item(m)
        if len(item) < 20:
            continue
        low = item.lower()
        if any(x in low for x in descartar):
            continue
        k = _clave_item(item)
        if k in vistos:
            continue
        vistos.add(k)
        encontrados.append(item)

    return encontrados[:maximo]


def leer_pdfs_de_carpeta(carpeta: str | Path) -> list[dict]:
    carpeta = Path(carpeta)
    if not carpeta.exists():
        return []
    salida = []
    for path in carpeta.glob("*.pdf"):
        texto = leer_pdf(path)
        salida.append(
            {"archivo": str(path), "texto": texto, "renglones": detectar_renglones(texto)}
        )
    return salida
