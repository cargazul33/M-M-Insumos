"""Coincidencia entre un renglón solicitado y un resultado de proveedor."""

from __future__ import annotations

from radar.parsing.classifier import normalizar


def _tokens(texto: str) -> set[str]:
    return set(normalizar(texto).split())


def _contiene_codigo(item: dict, resultado: dict) -> bool:
    codigo = item.get("codigo") or item.get("part_number") or ""
    if not codigo:
        return False
    objetivo = normalizar(
        f"{resultado.get('titulo', '')} {resultado.get('descripcion', '')}"
    )
    return normalizar(codigo) in objetivo


def calcular_match(item: dict, resultado: dict) -> tuple[str, int]:
    specs = item.get("especificaciones") or {}
    texto_item = " ".join(
        [
            str(item.get("producto", "")),
            str(item.get("buscar_py") or item.get("buscar_ar") or ""),
            " ".join(str(v) for v in specs.values()),
        ]
    )
    texto_res = " ".join(
        [
            str(resultado.get("titulo", "")),
            str(resultado.get("descripcion", "")),
            str(resultado.get("fuente", "")),
        ]
    )

    ti, tr = _tokens(texto_item), _tokens(texto_res)
    if not ti or not tr:
        return "NO MATCH", 0

    if _contiene_codigo(item, resultado):
        return "EXACTO", 100

    ratio = len(ti & tr) / max(len(ti), 1)
    pct = round(ratio * 100)
    if ratio >= 0.55:
        return "CERCANO DEFENDIBLE", pct
    if ratio >= 0.25:
        return "PARCIAL", pct
    return "NO MATCH", pct


def marcar_match(item: dict, resultado: dict) -> dict:
    match, score = calcular_match(item, resultado)
    resultado["match"] = match
    resultado["match_score"] = score
    return resultado
