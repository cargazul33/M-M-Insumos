"""Motor de decisión — Prompt Maestro M&M como reglas de código.

Convierte la auditoría de `ranking.evaluar_renglon` en una decisión final que
respeta al pie el "PROMPT MAESTRO DEFINITIVO":

  - PARAGUAY PRIMERO REAL: Argentina solo gana si Paraguay no entregó una
    publicación activa útil (con precio publicado).
  - JERARQUÍA DEL GANADOR: EXACTO limpio PY más barato -> CERCANO DEFENDIBLE PY
    -> (paquete completo si el renglón es mixto) -> Argentina -> referencia.
  - SOLO PRECIO PUBLICADO + LINK ÚTIL + PUBLICACIÓN ACTIVA.
  - FUSIBLES/ADVERTENCIAS con el texto exacto del prompt.
  - SALIDA en pesos argentinos.

No hace red: opera sobre los resultados que ya trajo el ranking. Por eso es
100% determinístico y testeable offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from radar.pricing.currency import convertir_a_ars, precio_legible
from radar.pricing.validator import contiene_precio, link_directo, publicacion_activa, validar_resultado

# Vocabulario textual EXACTO del Prompt Maestro (no editar a la ligera).
ADV_ADMISIBILIDAD = (
    "PRECIO BASE VERIFICADO. VALIDAR ADMISIBILIDAD DOCUMENTAL, COMERCIAL Y "
    "TÉCNICA ANTES DE OFERTAR."
)
ADV_STOCK = "PRECIO PUBLICADO VERIFICADO. VALIDAR STOCK ANTES DE OFERTAR."
ADV_BIEN_SERVICIO = (
    "PRECIO BASE DEL BIEN. EL PLIEGO INCLUYE COMPONENTE DE SERVICIO O PRESTACIÓN "
    "ASOCIADA. NO TOMAR COMO COSTO TOTAL DEL RENGLÓN."
)
SIN_MATCH_LIMPIO = "SIN MATCH EXACTO LIMPIO — ENLACE MÁS CERCANO"
SIN_HALLAZGO = "SIN HALLAZGO VERIFICABLE CON PRECIO PUBLICADO"
SIN_PUBLICACION = "SIN PUBLICACIÓN ACTIVA ÚTIL"

_ORDEN_MATCH = {"EXACTO": 0, "CERCANO DEFENDIBLE": 1, "PARCIAL": 2, "NO MATCH": 3}


@dataclass
class Decision:
    """Resultado final para un renglón, listo para producción o auditoría."""
    producto: str
    estado: str                      # GANADOR | SIN_MATCH_LIMPIO | SIN_HALLAZGO | SIN_PUBLICACION
    precio_ars: int | None = None
    precio_original: str = ""
    enlace: str = ""
    pais: str = ""
    fuente: str = ""
    match: str = ""
    semaforo: str = ""
    advertencias: list[str] = field(default_factory=list)
    descartadas: list[dict] = field(default_factory=list)  # para modo auditoría
    es_mixto: bool = False

    # -- Salidas formateadas ------------------------------------------------ #
    def linea_produccion(self, idx: int) -> str:
        """Formato MODO PRODUCCIÓN del prompt: 'Ítem N: $PRECIO — ENLACE'."""
        if self.estado == "GANADOR":
            precio = f"${self.precio_ars:,.0f}".replace(",", ".") if self.precio_ars else "—"
            linea = f"Ítem {idx}: {precio} — {self.enlace or '(sin enlace)'}"
        elif self.estado == "SIN_MATCH_LIMPIO":
            linea = f"Ítem {idx}: {SIN_MATCH_LIMPIO if not self.enlace else 'SIN MATCH EXACTO LIMPIO — ' + self.enlace}"
        elif self.estado == "SIN_PUBLICACION":
            linea = f"Ítem {idx}: {SIN_PUBLICACION}"
        else:
            linea = f"Ítem {idx}: {SIN_HALLAZGO}"
        for adv in self.advertencias:
            linea += f"\nADVERTENCIA: {adv}"
        return linea

    def to_dict(self) -> dict:
        return {
            "producto": self.producto, "estado": self.estado,
            "precio_ars": self.precio_ars, "precio_original": self.precio_original,
            "enlace": self.enlace, "pais": self.pais, "fuente": self.fuente,
            "match": self.match, "semaforo": self.semaforo,
            "advertencias": self.advertencias, "es_mixto": self.es_mixto,
        }


def _es_limpio(r: dict) -> bool:
    """Publicación con precio + link directo + activa + stock sólido."""
    return validar_resultado(r)[0]


def _utilizable(r: dict) -> bool:
    """Tiene precio publicado + enlace directo útil + publicación activa.

    Permite stock ambiguo como FUSIBLE, pero nunca acepta homepage, categoría,
    búsqueda interna, publicación caída ni link sin precio.
    """
    if not contiene_precio(r) or not r.get("url"):
        return False
    if not (link_directo(r) or r.get("link_directo") is True):
        return False
    if not publicacion_activa(r):
        return False
    if r.get("match") == "NO MATCH":
        return False
    return True


def _clave_orden(r: dict) -> tuple:
    """Orden Prompt Maestro: primero EXACTO, luego limpio, luego más barato."""
    match = _ORDEN_MATCH.get(r.get("match", "NO MATCH"), 3)
    limpio = 0 if _es_limpio(r) else 1
    precio = convertir_a_ars(r.get("precio")) or 10**12
    return (match, limpio, precio)


def _elegir(referencias: list[dict]) -> dict | None:
    candidatas = [r for r in referencias if _utilizable(r)]
    if not candidatas:
        return None
    return sorted(candidatas, key=_clave_orden)[0]


def decidir(auditoria: dict) -> Decision:
    """Aplica el Prompt Maestro sobre la auditoría de un renglón."""
    item = auditoria.get("item", {}) or {}
    producto = item.get("producto") or item.get("texto_original") or "ítem"
    es_mixto = bool(item.get("renglon_mixto") or item.get("requiere_servicio"))

    paraguay = auditoria.get("paraguay", []) or []
    argentina = auditoria.get("argentina", []) or []

    # 1) PARAGUAY PRIMERO REAL: ¿hay publicación activa útil en PY?
    ganador = _elegir(paraguay)
    pais_ganador = "PY"

    # 2) Solo si Paraguay no dio nada utilizable, pasar a Argentina.
    if ganador is None:
        ganador = _elegir(argentina)
        pais_ganador = "AR"

    # Fuentes descartadas (para auditoría): con precio pero que no ganaron.
    descartadas = [
        {
            "fuente": r.get("fuente"), "pais": r.get("pais"),
            "precio": r.get("precio"), "url": r.get("url"),
            "motivo": "; ".join(r.get("errores_validacion", [])[:2]) or "no fue la mejor",
        }
        for r in (paraguay + argentina)
        if r is not ganador and (r.get("url") or r.get("precio"))
    ][:3]

    # 3) Sin nada utilizable -> distinguir "sin publicación activa" de "sin hallazgo".
    if ganador is None:
        hubo_links = any(r.get("url") for r in paraguay + argentina)
        # ¿Aparecieron resultados pero todos caídos/sin stock?
        hubo_inactivos = any(
            not r.get("valido", False) and r.get("url") for r in paraguay + argentina
        )
        if hubo_inactivos and not _hay_precio(paraguay + argentina):
            estado = "SIN_PUBLICACION"
        elif hubo_links:
            # Hay enlace cercano pero sin precio publicado limpio/directo.
            cercano = next((r for r in paraguay + argentina if r.get("url")), {})
            return Decision(
                producto=producto, estado="SIN_MATCH_LIMPIO",
                enlace=cercano.get("url", ""), pais=cercano.get("pais", ""),
                fuente=cercano.get("fuente", ""), descartadas=descartadas,
                es_mixto=es_mixto,
            )
        else:
            estado = "SIN_HALLAZGO"
        return Decision(producto=producto, estado=estado,
                        descartadas=descartadas, es_mixto=es_mixto)

    # 4) Hay ganador. Construir decisión + fusibles.
    precio_ars = convertir_a_ars(ganador.get("precio"))
    decision = Decision(
        producto=producto,
        estado="GANADOR",
        precio_ars=precio_ars,
        precio_original=ganador.get("precio", ""),
        enlace=ganador.get("url", ""),
        pais=ganador.get("pais", pais_ganador),
        fuente=ganador.get("fuente") or ganador.get("proveedor", ""),
        match=ganador.get("match", ""),
        semaforo=ganador.get("semaforo", ""),
        descartadas=descartadas,
        es_mixto=es_mixto,
    )

    # FUSIBLES (en orden de severidad).
    if es_mixto:
        decision.advertencias.append(ADV_BIEN_SERVICIO)
    if not _es_limpio(ganador):
        # Tiene precio pero el stock/disponibilidad no es 100% limpio.
        decision.advertencias.append(ADV_STOCK)
    else:
        # Limpio, pero igual recordamos validar admisibilidad documental.
        decision.advertencias.append(ADV_ADMISIBILIDAD)

    return decision


def _hay_precio(resultados: list[dict]) -> bool:
    return any(contiene_precio(r) for r in resultados or [])


def decidir_lote(evaluaciones: list[dict]) -> list[Decision]:
    return [decidir(ev) for ev in evaluaciones or []]


# --------------------------------------------------------------------------- #
# Render de auditoría (MODO AUDITORÍA del prompt)
# --------------------------------------------------------------------------- #
def bloque_auditoria(decision: Decision) -> str:
    estado_comercial = {
        "LIMPIO": "DISPONIBLE", "OBSERVABLE": "AMBIGUO", "NO_RECOMENDADO": "NO DISPONIBLE",
    }.get(decision.semaforo, "PROBABLE")

    lineas = [
        f"   match: {decision.match or '—'}",
        f"   país ganador: {decision.pais or '—'}",
        f"   estado comercial: {estado_comercial}",
        f"   renglón: {'MIXTO (bien+servicio)' if decision.es_mixto else 'BIEN PURO'}",
        f"   semáforo: {decision.semaforo or '—'}",
    ]
    if decision.descartadas:
        lineas.append("   fuentes descartadas:")
        for d in decision.descartadas:
            lineas.append(
                f"     - {d.get('fuente', '?')} ({d.get('pais', '?')}): "
                f"{d.get('motivo', 'descartada')}"
            )
    return "\n".join(lineas)
