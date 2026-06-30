"""Validación de resultados de proveedores: precio, link directo, stock, etc."""

from __future__ import annotations

INVALID_PRODUCT_WORDS = [
    "sin stock", "agotado", "no disponible", "consultar precio",
    "consultar stock", "consultar disponibilidad", "a pedido", "pausada",
    "publicacion finalizada", "producto no encontrado", "no encontramos resultados",
]

_PRECIOS_INVALIDOS = {
    "", "-", "sin precio", "consultar", "consultar precio",
    "sin hallazgo verificable con precio publicado",
}

_LINKS_NO_DIRECTOS = (
    "catalogsearch", "/search", "buscar", "listado", "categoria",
    "category", "?q=", "?s=", "termo=",
)


def contiene_precio(r: dict) -> bool:
    precio = (str(r.get("precio") or "")).strip().lower()
    return precio not in _PRECIOS_INVALIDOS


def link_directo(r: dict) -> bool:
    url = (str(r.get("url") or "")).strip().lower()
    if not url:
        return False
    return not any(x in url for x in _LINKS_NO_DIRECTOS)


def publicacion_activa(r: dict) -> bool:
    texto = " ".join(
        str(r.get(k, "")) for k in ("titulo", "descripcion", "estado", "stock_texto")
    ).lower()
    return not any(p in texto for p in INVALID_PRODUCT_WORDS)


def disponibilidad_solida(r: dict) -> bool:
    if r.get("stock") is True:
        return True
    texto = " ".join(
        str(r.get(k, "")) for k in ("estado", "stock_texto", "descripcion")
    ).lower()
    return any(
        x in texto
        for x in ("disponible", "en stock", "agregar al carrito", "comprar")
    )


def validar_resultado(r: dict) -> tuple[bool, list[str]]:
    if not isinstance(r, dict):
        return False, ["resultado inválido"]
    errores: list[str] = []
    if not contiene_precio(r):
        errores.append("sin precio publicado")
    if not r.get("titulo"):
        errores.append("sin producto identificable")
    if not r.get("url"):
        errores.append("sin enlace")
    elif not link_directo(r):
        errores.append("link no directo")
    if not publicacion_activa(r):
        errores.append("publicación no activa")
    if not disponibilidad_solida(r):
        errores.append("stock no confirmado")
    return len(errores) == 0, errores


def semaforo(r: dict) -> str:
    valido, _ = validar_resultado(r)
    if valido:
        return "LIMPIO"
    if contiene_precio(r) and r.get("url"):
        return "OBSERVABLE"
    return "NO_RECOMENDADO"


def marcar_validacion(r: dict) -> dict:
    valido, errores = validar_resultado(r)
    r["valido"] = valido
    r["errores_validacion"] = errores
    r["semaforo"] = semaforo(r)
    return r
