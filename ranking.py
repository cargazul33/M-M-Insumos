"""Ranking de precios y referencias según Prompt Maestro M&M.

V25 aplica el candado de ejecución:
- saturar Paraguay primero (proveedores PY + Brave PY + variantes de búsqueda);
- Argentina se consulta solo si Paraguay no entrega publicación activa útil;
- ganador final solo puede tener precio publicado + enlace directo útil + publicación activa;
- si no hay ganador limpio, se devuelve referencia cercana/diagnóstico sin inventar.
"""

from __future__ import annotations

import re

from radar import config
from radar.pricing.currency import convertir_a_ars
from radar.pricing.matcher import calcular_match, marcar_match
from radar.pricing.providers import buscar_en_argentina, buscar_en_paraguay, buscar_web_general
from radar.pricing.validator import (
    contiene_precio,
    link_directo,
    marcar_validacion,
    publicacion_activa,
    validar_resultado,
)

_FUENTE_RANK = {
    "shopping china": 13,
    "nissei": 13,
    "cellshop": 12,
    "tupi": 10,
    "mega electrónicos": 9,
    "mega electronicos": 9,
    "visao vip": 8,
    "mercado libre ar": 7,
}


def _limpiar(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip()


def _precio_ars(r: dict) -> int | None:
    ars = convertir_a_ars(r.get("precio"))
    return int(ars) if ars else None


def _fuente_rank(r: dict) -> int:
    f = str(r.get("fuente") or r.get("proveedor") or "").lower()
    for clave, score in _FUENTE_RANK.items():
        if clave in f:
            return score
    if r.get("origen") == "BRAVE_WEB":
        return 6
    return 4


def publicacion_util(r: dict) -> bool:
    """Fuente válida o al menos defendible: precio + link directo + activa.

    La disponibilidad puede quedar como advertencia, pero no aceptamos homepages,
    categorías, búsquedas internas, publicaciones caídas ni links sin precio.
    """
    if not contiene_precio(r):
        return False
    if not r.get("url"):
        return False
    if not (link_directo(r) or r.get("link_directo") is True):
        return False
    if not publicacion_activa(r):
        return False
    if r.get("match") == "NO MATCH":
        return False
    return True


def _score(item: dict, r: dict, minimo: int) -> int:
    total = 0
    precio_ars = _precio_ars(r)
    r["precio_ars"] = precio_ars

    if contiene_precio(r):
        total += 35
    if precio_ars and minimo > 0:
        total += min(35, round((minimo / precio_ars) * 35))
    elif precio_ars:
        total += 18

    match, pct = calcular_match(item, r)
    r["match"] = match
    r["match_score"] = pct
    total += {"EXACTO": 34, "CERCANO DEFENDIBLE": 25, "PARCIAL": 12, "NO MATCH": 0}.get(match, 0)

    if r.get("pais") == "PY":
        total += 10
    if r.get("stock") is True or "disponible" in str(r.get("stock_texto", "")).lower():
        total += 6
    if link_directo(r) or r.get("link_directo") is True:
        total += 16
    if validar_resultado(r)[0]:
        total += 16
    elif publicacion_util(r):
        total += 8
    if r.get("origen") == "BRAVE_WEB":
        total += 4

    total += _fuente_rank(r)
    r["score_total"] = total
    return total


def _normalizar(item: dict, resultados: list[dict], origen: str) -> list[dict]:
    salida: list[dict] = []
    for r in resultados or []:
        if not isinstance(r, dict):
            continue
        r = dict(r)
        r.setdefault("titulo", r.get("query") or item.get("producto") or "")
        r.setdefault("descripcion", r.get("titulo") or "")
        r.setdefault("precio", "")
        r.setdefault("stock", False)
        r.setdefault("stock_texto", "revisar manualmente")
        r.setdefault("estado", "REFERENCIA_REVISAR")
        r.setdefault("origen", origen)
        marcar_match(item, r)
        marcar_validacion(r)
        salida.append(r)
    return salida


def _ordenar(item: dict, resultados: list[dict]) -> list[dict]:
    precios = [_precio_ars(r) for r in resultados]
    precios = [p for p in precios if p]
    minimo = min(precios) if precios else 0
    for r in resultados:
        _score(item, r, minimo)
    return sorted(resultados, key=lambda r: r.get("score_total", 0), reverse=True)


def _limpiar_geo(q: str) -> str:
    q = re.sub(r"\b(Paraguay|Ciudad del Este|CDE|Argentina|precio|comprar)\b", " ", q or "", flags=re.I)
    return _limpiar(q)


def _query_variants(item: dict, pais: str) -> list[str]:
    """Familias obligatorias: exacto, marca+modelo, part number, atributos, idiomas/geografía."""
    producto = _limpiar(item.get("producto") or "")
    codigo = _limpiar(item.get("codigo") or "")
    marca = _limpiar(item.get("marca_sugerida") or "")
    texto = _limpiar(item.get("texto_original") or "")
    specs = item.get("especificaciones") or {}
    base = _limpiar(item.get("buscar_py") if pais == "PY" else item.get("buscar_ar"))
    base = _limpiar_geo(base)

    attrs = " ".join(str(v) for v in specs.values() if v)[:120]
    candidatos = [
        codigo,
        f"{marca} {codigo}" if marca and codigo else "",
        f"{producto} {codigo}" if producto and codigo else "",
        f"{producto} {attrs}" if attrs else "",
        base,
        producto,
        texto[:140],
    ]

    geo = ["Paraguay Ciudad del Este", "CDE Paraguay", "precio Paraguay"] if pais == "PY" else ["Argentina precio", "comprar Argentina"]
    salida: list[str] = []
    vistos: set[str] = set()
    for c in candidatos:
        c = _limpiar(c)
        if len(c) < 3:
            continue
        for g in ([""] + geo[:2]):
            q = _limpiar(f"{c} {g}") if g else c
            k = q.lower()
            if k in vistos:
                continue
            vistos.add(k)
            salida.append(q)
            if len(salida) >= max(1, int(config.SEARCH_QUERY_VARIANTS)):
                return salida
    return salida[: max(1, int(config.SEARCH_QUERY_VARIANTS))]


def _dedupe(resultados: list[dict]) -> list[dict]:
    salida: list[dict] = []
    vistos: set[str] = set()
    for r in resultados or []:
        key = (r.get("url") or "") + "|" + (r.get("precio") or "")
        if key in vistos:
            continue
        vistos.add(key)
        salida.append(r)
    return salida


def _buscar_paraguay(item: dict) -> list[dict]:
    resultados: list[dict] = []
    for q in _query_variants(item, "PY"):
        q_directo = _limpiar_geo(q)
        resultados.extend(_normalizar(item, buscar_en_paraguay(q_directo), "PROVEEDOR_PY"))
        resultados.extend(_normalizar(item, buscar_web_general(q, pais="PY"), "BRAVE_WEB"))
    return _dedupe(resultados)


def _buscar_argentina(item: dict) -> list[dict]:
    resultados: list[dict] = []
    for q in _query_variants(item, "AR"):
        q_directo = _limpiar_geo(q)
        resultados.extend(_normalizar(item, buscar_en_argentina(q_directo), "PROVEEDOR_AR"))
        resultados.extend(_normalizar(item, buscar_web_general(q, pais="AR"), "BRAVE_WEB"))
    return _dedupe(resultados)


def evaluar_renglon(item: dict, incluir_argentina: bool = True) -> dict:
    auditoria = {
        "item": item,
        "paraguay": [],
        "argentina": [],
        "web": [],
        "resultados": [],
        "referencias": [],
        "ganador": None,
        "estado": "SIN_REFERENCIAS",
        "motivo": "",
    }

    if not (item.get("buscar_py") or item.get("producto") or item.get("texto_original")):
        auditoria["estado"] = "SIN_QUERY"
        auditoria["motivo"] = "El renglón no generó una búsqueda útil."
        return auditoria

    # CANDADO: Paraguay primero real, con variantes y Brave PY.
    py_refs = _buscar_paraguay(item)
    auditoria["paraguay"] = py_refs
    auditoria["web"].extend([r for r in py_refs if r.get("origen") == "BRAVE_WEB"])

    hay_py_util = any(publicacion_util(r) for r in py_refs)

    # Argentina solo si Paraguay no entregó publicación activa útil.
    ar_refs: list[dict] = []
    if incluir_argentina and not hay_py_util:
        ar_refs = _buscar_argentina(item)
        auditoria["argentina"] = ar_refs
        auditoria["web"].extend([r for r in ar_refs if r.get("origen") == "BRAVE_WEB"])
    elif hay_py_util:
        auditoria["motivo"] = "Paraguay entregó publicación activa útil; Argentina no se consultó por candado."

    referencias = [r for r in py_refs + ar_refs if r.get("url")]
    referencias = _ordenar(item, referencias)
    auditoria["resultados"] = referencias[:10]
    auditoria["referencias"] = referencias[:10]

    util_con_precio = [r for r in referencias if publicacion_util(r)]
    if util_con_precio:
        auditoria["ganador"] = util_con_precio[0]
        auditoria["estado"] = "CON_PRECIO_UTIL"
        auditoria["motivo"] = auditoria["motivo"] or "Precio publicado con enlace directo útil. Validar admisibilidad antes de ofertar."
    elif referencias:
        # Enlace cercano para excepción SIN_MATCH, pero no ganador limpio.
        auditoria["ganador"] = next((r for r in referencias if r.get("url")), referencias[0])
        auditoria["estado"] = "SOLO_REFERENCIA"
        auditoria["motivo"] = "No apareció precio limpio con enlace directo útil; se deja enlace cercano para revisión manual."
    else:
        auditoria["estado"] = "SIN_REFERENCIAS"
        auditoria["motivo"] = "Sin referencias útiles en proveedores/Brave."

    return auditoria


def evaluar_renglones(items: list[dict], limite: int = 3) -> list[dict]:
    salida: list[dict] = []
    for item in (items or [])[:limite]:
        try:
            salida.append(evaluar_renglon(item))
        except Exception as e:  # noqa: BLE001
            salida.append({
                "item": item,
                "paraguay": [],
                "argentina": [],
                "web": [],
                "resultados": [],
                "referencias": [],
                "ganador": None,
                "estado": "ERROR",
                "motivo": str(e)[:180],
            })
    return salida
