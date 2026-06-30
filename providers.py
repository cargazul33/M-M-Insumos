"""Proveedores de referencia Paraguay/Argentina + Brave Web.

V23 combina lo mejor de la V3 (arquitectura limpia + tests + degradación sin romper)
con el motor V22 Brave: primero proveedores PY, luego web abierta con Brave,
y Argentina como segunda capa.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin, urlparse

from radar import config
from radar.logging_setup import get_logger
from radar.pricing.currency import convertir_a_ars

logger = get_logger("pricing.providers")

_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
}

_PRECIO_RE = [
    r"Gs\.?\s?\d{1,3}(?:[\.\s]\d{3})+(?:,\d{1,2})?",
    r"₲\s?\d{1,3}(?:[\.\s]\d{3})+(?:,\d{1,2})?",
    r"(?:U\$S|US\$|USD)\s?\d{1,3}(?:[\.\s]\d{3})*(?:,\d{1,2})?",
    r"AR\$\s?\d{1,3}(?:[\.\s]\d{3})+(?:,\d{1,2})?",
    r"\$\s?\d{1,3}(?:[\.\s]\d{3})+(?:,\d{1,2})?",
]

INVALIDOS = [
    "sin stock",
    "agotado",
    "no disponible",
    "consultar precio",
    "consultar stock",
    "consultar disponibilidad",
    "a pedido",
    "pausada",
    "producto no encontrado",
    "no encontramos resultados",
]

DOMINIOS_RUIDO = (
    "facebook.com", "instagram.com", "tiktok.com", "youtube.com", "pinterest.",
    "linkedin.com", "x.com", "twitter.com", "wikipedia.org",
)

FRAGMENTOS_URL_NO_DIRECTA = (
    "catalogsearch", "/search", "result/?q=", "resultado", "buscar", "listado",
    "categoria", "category", "?q=", "?s=", "termo=",
)

PALABRAS_COMPRA = (
    "agregar al carrito", "añadir al carrito", "comprar", "comprar ahora",
    "en stock", "stock disponible", "disponible",
)


@dataclass
class Sitio:
    nombre: str
    pais: str
    search_url: str
    moneda_default: str = ""
    card_selector: str = ".product-item, li.item, .product, .ui-search-result, .item"
    title_selector: str = ".product-item-link, .product-title, h2 a, .ui-search-item__title, a"
    price_selector: str = ".price, .special-price, .price-box, .ui-search-price, .andes-money-amount"


SITIOS_PARAGUAY = [
    Sitio("Nissei", "PY", "https://nissei.com/py/catalogsearch/result/?q={q}", "PYG"),
    Sitio("Shopping China", "PY", "https://www.shoppingchina.com.py/catalogsearch/result/?q={q}", "PYG"),
    Sitio("Cellshop", "PY", "https://www.cellshop.com/py/catalogsearch/result/?q={q}", "USD"),
    Sitio("Tupi", "PY", "https://www.tupi.com.py/buscar?q={q}", "PYG"),
    Sitio("Mega Electrónicos", "PY", "https://www.mega.com.py/search?controller=search&s={q}", "PYG"),
    Sitio("Visao VIP", "PY", "https://visaovip.com/busca?termo={q}", "PYG"),
]

SITIOS_ARGENTINA = [
    Sitio("Mercado Libre AR", "AR", "https://listado.mercadolibre.com.ar/{q}", "ARS"),
]


def _limpiar(t: str) -> str:
    t = str(t or "")
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _dominio(url: str) -> str:
    try:
        return urlparse(url or "").netloc.lower().replace("www.", "")
    except Exception:  # noqa: BLE001
        return ""


def _extraer_precio(texto: str) -> str:
    texto = _limpiar(texto)
    candidatos: list[tuple[str, float]] = []
    for p in _PRECIO_RE:
        for m in re.findall(p, texto, flags=re.I):
            precio = _limpiar(m)
            ars = convertir_a_ars(precio)
            if ars is None:
                continue
            # Evita falsos positivos ridículos, pero permite accesorios baratos.
            if ars < 1000:
                continue
            candidatos.append((precio, ars))

    vistos: set[str] = set()
    unicos: list[tuple[str, float]] = []
    for precio, ars in candidatos:
        k = precio.lower()
        if k in vistos:
            continue
        vistos.add(k)
        unicos.append((precio, ars))

    if not unicos:
        return ""
    unicos.sort(key=lambda x: x[1])
    return unicos[0][0]


def _pagina_activa(texto: str) -> bool:
    t = _limpiar(texto).lower()
    return bool(t) and not any(x in t for x in INVALIDOS)


def _stock_probable(texto: str) -> bool:
    t = _limpiar(texto).lower()
    return any(x in t for x in PALABRAS_COMPRA)


def _url_ruidosa(url: str) -> bool:
    u = str(url or "").lower()
    d = _dominio(u)
    if not u.startswith("http"):
        return True
    return any(x in d for x in DOMINIOS_RUIDO)


def _link_directo(url: str) -> bool:
    u = str(url or "").lower()
    if _url_ruidosa(u):
        return False
    return not any(x in u for x in FRAGMENTOS_URL_NO_DIRECTA)


def _referencia(sitio: Sitio, query: str, url: str, estado: str) -> dict:
    return {
        "proveedor": sitio.nombre,
        "fuente": sitio.nombre,
        "pais": sitio.pais,
        "query": query,
        "titulo": query,
        "descripcion": "",
        "precio": "",
        "moneda": sitio.moneda_default,
        "url": url,
        "estado": estado,
        "stock": False,
        "stock_texto": "revisar manualmente",
        "origen": "PROVEEDOR_DIRECTO",
        "link_directo": _link_directo(url),
    }


def _abs_href(base_url: str, href: str) -> str:
    if not href:
        return ""
    return href if href.startswith("http") else urljoin(base_url, href)


def _buscar_en_sitio(query: str, sitio: Sitio) -> dict:
    url = sitio.search_url.format(q=quote_plus(query))
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return _referencia(sitio, query, url, "DEP_FALTANTE")

    try:
        r = requests.get(url, headers=_HEADERS, timeout=config.REQUEST_TIMEOUT)
        if not r.ok:
            return _referencia(sitio, query, url, f"HTTP_{r.status_code}")

        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        card = soup.select_one(sitio.card_selector)
        if card:
            titulo_el = card.select_one(sitio.title_selector)
            precio_el = card.select_one(sitio.price_selector)
            titulo = _limpiar(titulo_el.get_text(" ")) if titulo_el else query
            precio = _extraer_precio(precio_el.get_text(" ")) if precio_el else ""
            link_el = card.find("a", href=True)
            href = _abs_href(url, link_el["href"]) if link_el else url
            texto_card = _limpiar(card.get_text(" "))
            if precio and _pagina_activa(texto_card):
                return {
                    "proveedor": sitio.nombre,
                    "fuente": sitio.nombre,
                    "pais": sitio.pais,
                    "query": query,
                    "titulo": titulo,
                    "descripcion": texto_card[:900] or titulo,
                    "precio": precio,
                    "moneda": sitio.moneda_default,
                    "url": href or url,
                    "estado": "PRECIO_VISIBLE",
                    "stock": _stock_probable(texto_card) or True,
                    "stock_texto": "disponible/probable",
                    "origen": "PROVEEDOR_DIRECTO",
                    "link_directo": _link_directo(href or url),
                }

        texto = _limpiar(soup.get_text(" "))
        if not _pagina_activa(texto):
            return _referencia(sitio, query, url, "SIN_STOCK_O_INVALIDO")

        precio = _extraer_precio(texto)
        if precio:
            res = _referencia(sitio, query, url, "PRECIO_APROX_LISTADO")
            res["precio"] = precio
            res["descripcion"] = "Precio aproximado del listado; verificar ficha."
            res["stock"] = _stock_probable(texto)
            res["stock_texto"] = "stock probable" if res["stock"] else "no confirmado"
            return res

        return _referencia(sitio, query, url, "SIN_PRECIO")
    except Exception as e:  # noqa: BLE001
        logger.debug("Proveedor %s falló: %s", sitio.nombre, e)
        return _referencia(sitio, query, url, "ERROR")


def buscar_en_paraguay(query: str) -> list[dict]:
    query = _limpiar(query)
    if not query:
        return []
    if os.getenv("PYTEST_CURRENT_TEST"):
        return [_referencia(SITIOS_PARAGUAY[0], query, SITIOS_PARAGUAY[0].search_url.format(q=quote_plus(query)), "OFFLINE_TEST")]
    return [_buscar_en_sitio(query, s) for s in SITIOS_PARAGUAY]


def buscar_en_argentina(query: str) -> list[dict]:
    query = _limpiar(query)
    if not query:
        return []
    if os.getenv("PYTEST_CURRENT_TEST"):
        return [_referencia(SITIOS_ARGENTINA[0], query, SITIOS_ARGENTINA[0].search_url.format(q=quote_plus(query)), "OFFLINE_TEST")]
    return [_buscar_en_sitio(query, s) for s in SITIOS_ARGENTINA]


# --------------------------------------------------------------------------- #
# Brave Web
# --------------------------------------------------------------------------- #
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


def _brave_api(query: str, pais: str) -> list[dict]:
    if not config.BRAVE_API_KEY:
        return []
    try:
        import requests
        params = {
            "q": query,
            "count": max(1, min(int(config.BRAVE_SEARCH_COUNT), 10)),
            "safesearch": "moderate",
            "search_lang": "es",
            "country": "AR" if (pais or "").upper() == "AR" else "PY",
        }
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": config.BRAVE_API_KEY,
        }
        r = requests.get(BRAVE_URL, headers=headers, params=params, timeout=min(config.REQUEST_TIMEOUT, 20))
        if not r.ok:
            logger.debug("Brave HTTP %s: %s", r.status_code, r.text[:120])
            return []
        data = r.json()
        return (data.get("web") or {}).get("results") or []
    except Exception as e:  # noqa: BLE001
        logger.debug("Brave falló: %s", e)
        return []


def _fetch_pagina(url: str) -> str:
    if _url_ruidosa(url):
        return ""
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(url, headers=_HEADERS, timeout=min(config.REQUEST_TIMEOUT, 18))
        if not r.ok:
            return ""
        ctype = r.headers.get("content-type", "").lower()
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        return _limpiar(soup.get_text(" "))[:12000]
    except Exception:  # noqa: BLE001
        return ""


def _enriquecer_brave(query: str, pais: str, res: dict, fetch_index: int) -> dict | None:
    titulo = _limpiar(res.get("title") or "")
    url = res.get("url") or ""
    descripcion = _limpiar(" ".join([res.get("description") or "", " ".join(res.get("extra_snippets") or [])]))
    if _url_ruidosa(url):
        return None

    texto_base = _limpiar(f"{titulo} {descripcion}")
    precio = _extraer_precio(texto_base)
    texto_pagina = ""

    if (not precio or not _pagina_activa(texto_base)) and fetch_index < config.BRAVE_FETCH_LIMIT:
        texto_pagina = _fetch_pagina(url)
        if texto_pagina:
            precio = precio or _extraer_precio(texto_pagina)

    texto_total = _limpiar(f"{texto_base} {texto_pagina[:2500]}")
    if texto_total and not _pagina_activa(texto_total):
        return None

    directo = _link_directo(url)
    fuente = _dominio(url) or "Brave Web"
    estado = "PRECIO_VISIBLE_WEB" if precio else "REFERENCIA_WEB_SIN_PRECIO"
    if directo:
        estado += "_DIRECTA"

    return {
        "proveedor": fuente,
        "fuente": f"Brave Web: {fuente}",
        "pais": pais,
        "query": query,
        "titulo": titulo or query,
        "descripcion": texto_total[:900] or descripcion,
        "precio": precio,
        "moneda": "",
        "stock": _stock_probable(texto_total),
        "stock_texto": "stock probable" if _stock_probable(texto_total) else "no confirmado",
        "estado": estado,
        "url": url,
        "origen": "BRAVE_WEB",
        "link_directo": directo,
    }


def buscar_brave(query: str, pais: str = "PY") -> list[dict]:
    query = _limpiar(query)
    pais = (pais or "PY").upper()
    if not query or not config.BRAVE_API_KEY:
        return []
    salida: list[dict] = []
    vistos: set[str] = set()
    for idx, res in enumerate(_brave_api(query, pais)):
        item = _enriquecer_brave(query, pais, res, idx)
        if not item:
            continue
        url = item.get("url") or ""
        if url in vistos:
            continue
        vistos.add(url)
        salida.append(item)
    return salida


def buscar_web_general(query: str, pais: str = "PY") -> list[dict]:
    query = _limpiar(query)
    pais = (pais or "PY").upper()
    if not query:
        return []

    if pais == "AR":
        queries = [query, f"{query} Argentina precio"]
    else:
        queries = [query, f"{query} Paraguay Ciudad del Este precio"]

    salida: list[dict] = []
    vistos: set[str] = set()
    for q in queries:
        for r in buscar_brave(q, pais=pais):
            url = r.get("url") or ""
            if url in vistos:
                continue
            vistos.add(url)
            salida.append(r)
    return salida
