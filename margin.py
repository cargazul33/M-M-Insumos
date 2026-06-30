"""Cálculo de margen posible del arbitraje Paraguay → Argentina.

El "margen posible" de M&M no es solo el precio más barato: es la diferencia entre
lo que cuesta conseguir el bien (Paraguay) y la referencia de venta/competencia
(Argentina o el precio oficial del pliego si está publicado).

Se calculan dos márgenes, ambos en ARS:
  - margen_arbitraje = mejor precio Argentina − mejor costo Paraguay
  - margen_vs_oficial = precio oficial del pliego − mejor costo Paraguay  (si hay)

OJO: es margen BRUTO de referencia. No incluye nacionalización, flete ni
impuestos (igual que el Prompt Maestro, que separa precio base de costo final).
Sirve para priorizar, no para ofertar.
"""

from __future__ import annotations

from radar.pricing.currency import convertir_a_ars
from radar.pricing.validator import contiene_precio


def _mejor_precio_ars(resultados: list[dict]) -> tuple[int | None, dict | None]:
    """Menor precio en ARS entre resultados con precio publicado."""
    mejor_ars: int | None = None
    mejor_res: dict | None = None
    for r in resultados or []:
        if not contiene_precio(r):
            continue
        ars = convertir_a_ars(r.get("precio"))
        if ars is None:
            continue
        if mejor_ars is None or ars < mejor_ars:
            mejor_ars, mejor_res = ars, r
    return mejor_ars, mejor_res


def calcular_margen(evaluacion: dict, item: dict | None = None) -> dict:
    item = item or evaluacion.get("item", {}) or {}
    cantidad = item.get("cantidad") or 1
    try:
        cantidad = int(cantidad)
    except (TypeError, ValueError):
        cantidad = 1

    py_ars, py_res = _mejor_precio_ars(evaluacion.get("paraguay", []))
    ar_ars, ar_res = _mejor_precio_ars(evaluacion.get("argentina", []))
    oficial_ars = convertir_a_ars(item.get("precio_oficial")) if item.get("precio_oficial") else None

    margen: dict = {
        "costo_py_ars": py_ars,
        "ref_ar_ars": ar_ars,
        "precio_oficial_ars": oficial_ars,
        "cantidad": cantidad,
        "margen_unit_ars": None,
        "margen_pct": None,
        "margen_total_ars": None,
        "base": "",
        "fuente_costo": (py_res or {}).get("fuente") if py_res else None,
        "fuente_ref": (ar_res or {}).get("fuente") if ar_res else None,
    }

    # Preferimos margen vs precio oficial; si no hay, arbitraje AR−PY.
    referencia = None
    if oficial_ars and py_ars:
        referencia, margen["base"] = oficial_ars, "vs_oficial"
    elif ar_ars and py_ars:
        referencia, margen["base"] = ar_ars, "arbitraje_ar_py"

    if referencia and py_ars:
        unit = referencia - py_ars
        margen["margen_unit_ars"] = unit
        margen["margen_pct"] = round(unit / referencia * 100, 1) if referencia else None
        margen["margen_total_ars"] = unit * cantidad

    return margen


def margen_legible(margen: dict) -> str:
    """Una línea para Telegram."""
    if margen.get("margen_unit_ars") is None:
        if margen.get("costo_py_ars") and not margen.get("ref_ar_ars"):
            return "sin referencia AR/oficial para calcular margen"
        return "sin datos suficientes para margen"

    def fmt(n):
        return f"${n:,.0f}".replace(",", ".") if n is not None else "—"

    base = "vs oficial" if margen["base"] == "vs_oficial" else "AR − PY"
    pct = f" ({margen['margen_pct']}%)" if margen.get("margen_pct") is not None else ""
    total = ""
    if margen.get("cantidad", 1) > 1 and margen.get("margen_total_ars") is not None:
        total = f" | x{margen['cantidad']} = {fmt(margen['margen_total_ars'])}"
    return f"{fmt(margen['margen_unit_ars'])}{pct} [{base}]{total}"
