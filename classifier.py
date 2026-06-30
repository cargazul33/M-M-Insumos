"""Clasificación de licitaciones y renglones para M&M.

Unifica los dos clasificadores que vivían en `radar.py` y `scanner.py`/`classifier.py`,
y normaliza tildes para no perder coincidencias por "climatización" vs "climatizacion".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from radar import keywords


# --------------------------------------------------------------------------- #
# Normalización
# --------------------------------------------------------------------------- #
def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, espacios colapsados."""
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _coincidencias(texto_norm: str, lista: list[str]) -> list[str]:
    return [x for x in lista if x in texto_norm]


# --------------------------------------------------------------------------- #
# Clasificación a nivel licitación (texto de la fila / título)
# --------------------------------------------------------------------------- #
@dataclass
class Clasificacion:
    decision: str   # COTIZAR | REVISAR | DESCARTAR
    puntaje: int    # 0-100
    motivo: str

    def emoji(self) -> str:
        return {"COTIZAR": "🟢", "REVISAR": "🟡", "DESCARTAR": "🔴"}.get(
            self.decision, "⚪"
        )


def clasificar_licitacion(texto: str) -> Clasificacion:
    t = normalizar(texto)

    excluidas = _coincidencias(t, keywords.EXCLUIR_DURO)
    if excluidas:
        return Clasificacion("DESCARTAR", 0, "Excluido: " + ", ".join(excluidas[:3]))

    fuertes = _coincidencias(t, keywords.COTIZAR_FUERTE)
    if fuertes:
        return Clasificacion("COTIZAR", 90, "Rubro M&M: " + ", ".join(fuertes[:4]))

    revisar = _coincidencias(t, keywords.REVISAR)
    if revisar:
        return Clasificacion(
            "REVISAR", 60, "Posible según proveedor: " + ", ".join(revisar[:4])
        )

    return Clasificacion("DESCARTAR", 10, "Sin productos claros para M&M.")


# --------------------------------------------------------------------------- #
# Clasificación a nivel renglón (línea concreta del pliego)
# --------------------------------------------------------------------------- #
@dataclass
class ClasificacionRenglon:
    rubro: str
    decision: str
    puntaje: int


_REGLAS_RENGLON: list[tuple[list[str], ClasificacionRenglon]] = [
    (
        ["cartucho", "toner", "ce340a", "ce341a", "ce342a", "ce343a", "cf237a",
         "mp305", "ricoh", "tinta"],
        ClasificacionRenglon("TONER / INSUMOS IMPRESION", "COTIZAR", 95),
    ),
    (
        ["computadora", "notebook", "monitor", "disco rigido", "ssd", "hdd",
         "hdmi", "vga", "teclado", "mouse", "pendrive", "memoria usb"],
        ClasificacionRenglon("HARDWARE", "COTIZAR", 95),
    ),
    (
        ["router", "switch", "access point", "cable utp", "patch cord",
         "starlink", "conectividad"],
        ClasificacionRenglon("CONECTIVIDAD / REDES", "COTIZAR", 92),
    ),
    (
        ["impresora", "multifuncion", "scanner", "escaner"],
        ClasificacionRenglon("IMPRESION", "COTIZAR", 90),
    ),
    (
        ["estabilizador", "ups", "1000 va", "fuente"],
        ClasificacionRenglon("ELECTRICIDAD / UPS", "COTIZAR", 85),
    ),
    (
        ["resma", "papel a4", "libreria", "papeleria", "utiles de oficina"],
        ClasificacionRenglon("LIBRERIA / PAPELERIA", "COTIZAR", 85),
    ),
    (
        ["escritorio", "silla", "mobiliario", "armario", "melamina", "estanteria"],
        ClasificacionRenglon("MUEBLES / OFICINA", "REVISAR", 65),
    ),
]


def clasificar_renglon(texto: str) -> ClasificacionRenglon:
    t = normalizar(texto)

    # Climatización: equipo puede servir, service no.
    if any(x in t for x in ["aire acondicionado", "split", "climatizacion"]):
        if _coincidencias(t, keywords.SERVICIOS):
            return ClasificacionRenglon("CLIMATIZACION / SERVICIO", "DESCARTAR", 30)
        return ClasificacionRenglon("CLIMATIZACION / EQUIPO", "REVISAR", 60)

    for claves, clasif in _REGLAS_RENGLON:
        if any(x in t for x in claves):
            return clasif

    if _coincidencias(t, keywords.SERVICIOS):
        return ClasificacionRenglon("SERVICIO", "DESCARTAR", 30)

    return ClasificacionRenglon("SIN CLASIFICAR", "REVISAR", 50)
