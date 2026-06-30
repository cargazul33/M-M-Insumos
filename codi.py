"""Acceso a CO.DI.NEU con Playwright: login, scan, detalle y descarga de pliegos.

Consolida login.py + scanner.py + detail.py + downloader.py de la V2 en un único
módulo coherente, con manejo de errores y reintentos de login.

Playwright se importa de forma diferida: el resto del paquete (self-test, tests)
funciona aunque Playwright no esté instalado.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urljoin

from radar import config
from radar.logging_setup import get_logger
from radar.parsing.classifier import clasificar_licitacion

logger = get_logger("sources.codi")


def _limpiar(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip()


def _abs_url(url: str) -> str:
    if not url:
        return ""
    return url if url.startswith("http") else urljoin(config.CODI_BASE, url)


# --------------------------------------------------------------------------- #
# Sesión
# --------------------------------------------------------------------------- #
@contextmanager
def sesion():
    """Context manager que abre Playwright, hace login y cede la página."""
    from playwright.sync_api import sync_playwright  # import diferido

    if not config.is_codi_configured():
        raise RuntimeError("Faltan CODI_USER / CODI_PASS.")

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=config.HEADLESS)
    context = browser.new_context(
        accept_downloads=True, user_agent=config.USER_AGENT
    )
    page = context.new_page()
    try:
        _login(page)
        yield context, page
    finally:
        try:
            browser.close()
        finally:
            p.stop()


def _login(page) -> None:
    ultimo_error = None
    for intento in range(1, 4):
        try:
            page.goto(config.CODI_LOGIN_URL, wait_until="commit", timeout=60000)
            page.wait_for_selector("#vUSUARIOUSERNAME", timeout=60000)
            page.fill("#vUSUARIOUSERNAME", config.CODI_USER)
            page.fill("#vUSUARIOPASSWORD", config.CODI_PASS)
            page.click("#LOGIN")
            page.wait_for_timeout(5000)

            texto = page.locator("body").inner_text(timeout=30000)
            if "Error de usuario o contraseña" in texto or "Invitado" in texto:
                raise RuntimeError("Credenciales rechazadas por CO.DI.NEU.")
            logger.info("Login CO.DI.NEU OK (intento %s).", intento)
            return
        except Exception as e:  # noqa: BLE001
            ultimo_error = e
            logger.warning("Login intento %s falló: %s", intento, e)
            page.wait_for_timeout(4000)
    raise RuntimeError(f"No se pudo iniciar sesión tras 3 intentos: {ultimo_error}")


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #
def _aplicar_filtros(page) -> None:
    try:
        page.select_option("select[name='vLCTESTA']", label="Publicado")
        page.wait_for_timeout(1000)
    except Exception:
        pass
    try:
        selects = page.locator("select")
        for i in range(selects.count()):
            try:
                selects.nth(i).select_option(label="100 registros por página")
                page.wait_for_timeout(1000)
                break
            except Exception:
                continue
    except Exception:
        pass
    page.wait_for_timeout(2000)


def scan(page) -> list[dict]:
    """Recorre el listado y devuelve oportunidades COTIZAR/REVISAR."""
    page.goto(config.CODI_LICITACIONES_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    _aplicar_filtros(page)

    filas = page.locator("tr")
    total = min(filas.count(), config.SCAN_MAX_FILAS)
    oportunidades: list[dict] = []
    descartadas = 0

    for i in range(total):
        try:
            fila = filas.nth(i)
            texto = _limpiar(fila.inner_text(timeout=3000))
            if len(texto) < 40:
                continue

            clasif = clasificar_licitacion(texto)
            if clasif.decision == "DESCARTAR":
                descartadas += 1
                continue

            visualizar_url = ""
            enlaces = fila.locator("a")
            for j in range(enlaces.count()):
                try:
                    a = enlaces.nth(j)
                    combinado = " ".join(
                        [
                            _limpiar(a.inner_text(timeout=1000)),
                            a.get_attribute("href") or "",
                            a.get_attribute("onclick") or "",
                        ]
                    )
                    if "Visualizar" in combinado or "wpverdetalleprove" in combinado:
                        visualizar_url = _abs_url(a.get_attribute("href") or "")
                        break
                except Exception:
                    continue

            oportunidades.append(
                {
                    "decision": clasif.decision,
                    "puntaje": clasif.puntaje,
                    "motivo": clasif.motivo,
                    "texto": texto[:1000],
                    "visualizar_url": visualizar_url,
                    "renglones": [],
                }
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("Error fila %s: %s", i, e)

    logger.info("Scan: %s oportunidades, %s descartadas.", len(oportunidades), descartadas)
    return oportunidades


# --------------------------------------------------------------------------- #
# Detalle + descarga
# --------------------------------------------------------------------------- #
def leer_detalle(page, url: str) -> dict:
    url = _abs_url(url)
    if not url:
        return {"url": "", "texto": "", "descargas": []}

    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)
    texto = page.locator("body").inner_text(timeout=30000)
    html = page.content()

    descargas, vistos = [], set()
    links = re.findall(r'com\.portallicitaciones\.adescargaradj\?[^"\\<>\s]+', html)
    nombres = re.findall(r'[^"\\<>]+?\.(?:pdf|xls|xlsx|doc|docx|zip)', html, flags=re.I)
    for i, link in enumerate(links):
        if link in vistos:
            continue
        vistos.add(link)
        descargas.append(
            {
                "nombre": _limpiar(nombres[i]) if i < len(nombres) else "pliego",
                "href": _abs_url(link),
            }
        )

    return {"url": url, "texto": texto, "descargas": descargas}


def _nombre_seguro(nombre: str) -> str:
    nombre = re.sub(r'[\\/*?:"<>|]', "_", nombre or "archivo")
    nombre = re.sub(r"\s+", " ", nombre).strip()
    if "." not in nombre:
        nombre += ".pdf"
    return nombre


def descargar(page, descargas: list[dict], maximo: int = 1) -> list[str]:
    """Descarga los primeros `maximo` adjuntos haciendo click en el enlace real."""
    Path(config.DOWNLOADS_DIR).mkdir(parents=True, exist_ok=True)
    bajados: list[str] = []
    for d in (descargas or [])[:maximo]:
        href = d.get("href", "")
        if "adescargaradj" not in href:
            continue
        nombre = _nombre_seguro(d.get("nombre", "pliego.pdf"))
        try:
            with page.expect_download(timeout=60000) as info:
                page.evaluate("(u) => window.location.assign(u)", href)
            download = info.value
            destino = str(Path(config.DOWNLOADS_DIR) / nombre)
            download.save_as(destino)
            bajados.append(destino)
            logger.info("Pliego descargado: %s", nombre)
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo descargar %s: %s", nombre, e)
    return bajados


# --------------------------------------------------------------------------- #
# CRAWL PROFUNDO (modo --full): TODAS las páginas, TODAS las licitaciones
# --------------------------------------------------------------------------- #
import hashlib as _hashlib  # noqa: E402

from radar import config as _cfg  # noqa: E402


def _id_lic(texto: str, url: str) -> str:
    base = f"{(texto or '')[:200]}|{url or ''}"
    return _hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def leer_filas_pagina(page) -> list[dict]:
    """Lee TODAS las filas de datos de la página actual (sin filtrar por rubro)."""
    filas = page.locator("tr")
    total = min(filas.count(), _cfg.SCAN_MAX_FILAS)
    salida: list[dict] = []
    for i in range(total):
        try:
            fila = filas.nth(i)
            texto = _limpiar(fila.inner_text(timeout=3000))
            if len(texto) < 40:
                continue
            visualizar_url = ""
            enlaces = fila.locator("a")
            for j in range(enlaces.count()):
                try:
                    a = enlaces.nth(j)
                    combinado = " ".join([
                        _limpiar(a.inner_text(timeout=1000)),
                        a.get_attribute("href") or "",
                        a.get_attribute("onclick") or "",
                    ])
                    if "Visualizar" in combinado or "wpverdetalleprove" in combinado:
                        visualizar_url = _abs_url(a.get_attribute("href") or "")
                        break
                except Exception:
                    continue
            salida.append({
                "id": _id_lic(texto, visualizar_url),
                "texto": texto[:1000],
                "visualizar_url": visualizar_url,
            })
        except Exception as e:  # noqa: BLE001
            logger.debug("Error fila %s: %s", i, e)
    return salida


def _firma_pagina(filas: list[dict]) -> str:
    return "|".join(f["id"] for f in filas[:5])


def _ir_siguiente_pagina(page) -> bool:
    """Intenta avanzar a la página siguiente con varias estrategias GeneXus.

    Devuelve True solo si la página efectivamente cambió de contenido.
    """
    import re as _re

    antes = _firma_pagina(leer_filas_pagina(page))

    candidatos = []
    # 1) Selector explícito por env (lo más confiable si lo configurás).
    if _cfg.CODI_NEXT_SELECTOR:
        candidatos.append(("css", _cfg.CODI_NEXT_SELECTOR))
    # 2) Texto típico de "siguiente".
    candidatos += [
        ("role", r"siguiente|pr[oó]xima|next"),
        ("text", ">"),
        ("text", "»"),
        ("text", "›"),
    ]
    # 3) Imagen con alt "siguiente" dentro de un link.
    candidatos += [
        ("css", "a:has(img[alt*='iguiente'])"),
        ("css", "a:has(img[alt*='ext'])"),
        ("css", "a[onclick*='next'], a[onclick*='Next'], a[onclick*='fwd']"),
    ]

    for tipo, val in candidatos:
        try:
            if tipo == "role":
                loc = page.get_by_role("link", name=_re.compile(val, _re.I))
            elif tipo == "text":
                loc = page.get_by_text(val, exact=True)
            else:
                loc = page.locator(val)
            if loc.count() == 0:
                continue
            loc.first.click(timeout=8000)
            page.wait_for_timeout(_cfg.CRAWL_SLEEP_MS + 1500)
            despues = _firma_pagina(leer_filas_pagina(page))
            if despues and despues != antes:
                return True
        except Exception:
            continue
    return False


def scan_completo(page) -> list[dict]:
    """Recorre TODAS las páginas y devuelve TODAS las licitaciones publicadas.

    No filtra por rubro: clasifica y guarda la decisión como metadato. El filtro
    de qué se manda por Telegram se aplica después, en el pipeline/reporte.
    """
    page.goto(_cfg.CODI_LICITACIONES_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    _aplicar_filtros(page)

    vistos: set[str] = set()
    todas: list[dict] = []

    for nro_pagina in range(1, _cfg.CRAWL_MAX_PAGINAS + 1):
        filas = leer_filas_pagina(page)
        nuevas = [f for f in filas if f["id"] not in vistos]

        for f in nuevas:
            vistos.add(f["id"])
            clasif = clasificar_licitacion(f["texto"])
            todas.append({
                "id": f["id"],
                "decision": clasif.decision,
                "puntaje": clasif.puntaje,
                "motivo": clasif.motivo,
                "texto": f["texto"],
                "visualizar_url": f["visualizar_url"],
                "pagina": nro_pagina,
                "descargas": [],
                "documentos": [],
                "renglones": [],
            })

        logger.info("Página %s: %s filas, %s nuevas (total %s).",
                    nro_pagina, len(filas), len(nuevas), len(todas))

        # Si no hubo filas nuevas, ya no avanza más.
        if not nuevas and nro_pagina > 1:
            break
        if not _ir_siguiente_pagina(page):
            logger.info("No hay más páginas (o no se detectó el control de paginado).")
            break
        page.wait_for_timeout(_cfg.CRAWL_SLEEP_MS)

    logger.info("Scan completo: %s licitaciones en %s páginas.", len(todas), nro_pagina)
    return todas


def descargar_todos(page, descargas: list[dict], maximo: int | None = None) -> list[str]:
    """Descarga TODOS los adjuntos de una licitación (PDF/Word/Excel/zip)."""
    maximo = maximo if maximo is not None else _cfg.CRAWL_MAX_DOCS_POR_LIC
    Path(_cfg.DOWNLOADS_DIR).mkdir(parents=True, exist_ok=True)
    bajados: list[str] = []
    vistos: set[str] = set()
    for d in (descargas or [])[:maximo]:
        href = d.get("href", "")
        if not href or "adescargaradj" not in href or href in vistos:
            continue
        vistos.add(href)
        nombre = _nombre_seguro(d.get("nombre", "adjunto"))
        try:
            with page.expect_download(timeout=60000) as info:
                page.evaluate("(u) => window.location.assign(u)", href)
            download = info.value
            destino = str(Path(_cfg.DOWNLOADS_DIR) / nombre)
            download.save_as(destino)
            bajados.append(destino)
            logger.info("Adjunto bajado: %s", nombre)
            page.wait_for_timeout(_cfg.CRAWL_SLEEP_MS)
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo bajar %s: %s", nombre, e)
    return bajados
