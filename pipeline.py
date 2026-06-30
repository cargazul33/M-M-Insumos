"""Pipeline end-to-end de Radar M&M V23.

Flujo:
  1. Login CO.DI.NEU
  2. Scan listado -> oportunidades COTIZAR/REVISAR
  3. Dedupe opcional contra corridas anteriores
  4. Priorización por puntaje
  5. Para el top-N: detalle, pliego, PDF, renglones
  6. Precio: Paraguay directo + Brave Web + Argentina
  7. Persistencia SQLite/cache
  8. Reporte Telegram ejecutivo
"""

from __future__ import annotations

from pathlib import Path

from radar import config
from radar.logging_setup import get_logger
from radar.notify import telegram
from radar.parsing import pdf
from radar.parsing.extractor import estructurar_renglones
from radar.pricing.ranking import evaluar_renglones
from radar.report import reporte_completo
from radar.sources import codi
from radar.store import db, seen

logger = get_logger("pipeline")


def _priorizar(oportunidades: list[dict]) -> list[dict]:
    return sorted(
        oportunidades or [],
        key=lambda o: (int(o.get("puntaje", 0) or 0), str(o.get("decision", "")) == "COTIZAR"),
        reverse=True,
    )


def _descartadas(total: int, oportunidades: list[dict]) -> int:
    return max(total - len(oportunidades or []), 0)


def ejecutar(enviar: bool = True, con_precios: bool = True, modo: str = "ejecutivo") -> dict:
    db.init_db()

    with codi.sesion() as (_context, page):
        oportunidades = codi.scan(page)
        total = len(oportunidades)
        base = seen.filtrar_nuevas(oportunidades) if config.DEDUPE else oportunidades
        nuevas = _priorizar(base)
        logger.info("%s nuevas/prioritarias de %s detectadas.", len(nuevas), total)

        evaluaciones_por_op: dict[int, list[dict]] = {}
        seleccionadas = nuevas[: config.TOP_LIMIT]

        for idx, op in enumerate(seleccionadas):
            if not op.get("visualizar_url"):
                continue
            try:
                detalle = codi.leer_detalle(page, op["visualizar_url"])
                op["descargas"] = detalle.get("descargas", [])

                renglones_txt: list[str] = []
                bajados: list[str] = []
                if op["descargas"]:
                    bajados = codi.descargar(page, op["descargas"], maximo=1)
                    if bajados:
                        op["pdf_bajado"] = Path(bajados[0]).name
                    for path in bajados:
                        texto_pdf = pdf.leer_pdf(path)
                        renglones_txt += pdf.detectar_renglones(texto_pdf, maximo=config.ITEMS_POR_PDF)

                items_obj = estructurar_renglones(renglones_txt, archivo=op.get("pdf_bajado"))
                # Evita perder tiempo en servicios/mano de obra.
                items_obj = [r for r in items_obj if getattr(r, "decision", "") != "DESCARTAR"]
                op["renglones"] = [r.to_dict() for r in items_obj[: config.ITEMS_POR_PDF]]

                if con_precios and op["renglones"]:
                    evaluaciones_por_op[idx] = evaluar_renglones(
                        op["renglones"], limite=config.PRICE_HUNTER_LIMIT
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("Error procesando oportunidad #%s: %s", idx + 1, e)
                op["motivo"] = (op.get("motivo", "") + f" | Error detalle/PDF: {str(e)[:120]}").strip()

    guardadas = db.guardar_oportunidades(seleccionadas)
    texto = reporte_completo(
        nuevas=seleccionadas,
        descartadas=_descartadas(total, oportunidades),
        total_detectadas=total,
        evaluaciones_por_op=evaluaciones_por_op,
        modo=modo,
    )

    if enviar:
        telegram.enviar(texto)

    return {
        "total": total,
        "nuevas": len(seleccionadas),
        "guardadas": guardadas,
        "reporte": texto,
    }


# --------------------------------------------------------------------------- #
# MODO FULL: crawl profundo diario de CODINEU completo
# --------------------------------------------------------------------------- #
def ejecutar_full(enviar: bool = True, con_precios: bool = True, modo: str = "ejecutivo") -> dict:
    """Recorre TODO CODINEU: todas las páginas, todas las licitaciones, todos los
    documentos; extrae, clasifica, cotiza (acotado), calcula margen, guarda
    histórico y manda por Telegram solo lo importante.
    """
    from radar.parsing.documents import leer_documentos
    from radar.pricing.margin import calcular_margen
    from radar.pricing.ranking import evaluar_renglon
    from radar.report import reporte_full
    from radar.store import db

    db.init_db_full()

    with codi.sesion() as (_context, page):
        licitaciones = codi.scan_completo(page)
        total = len(licitaciones)
        logger.info("Crawl: %s licitaciones publicadas. Bajando documentos...", total)

        for n, lic in enumerate(licitaciones, start=1):
            if not lic.get("visualizar_url"):
                continue
            try:
                detalle = codi.leer_detalle(page, lic["visualizar_url"])
                lic["descargas"] = detalle.get("descargas", [])

                bajados = []
                if config.DOWNLOAD_ALL_DOCS and lic["descargas"]:
                    bajados = codi.descargar_todos(page, lic["descargas"])

                docs_info = leer_documentos(bajados)
                renglones_txt: list[str] = []
                documentos_meta = []
                for info in docs_info:
                    rens = info.get("renglones", [])
                    renglones_txt += rens
                    documentos_meta.append({
                        "nombre": Path(info["archivo"]).name,
                        "tipo": info.get("tipo", ""),
                        "ruta_local": info["archivo"],
                        "n_renglones": len(rens),
                    })
                lic["documentos"] = documentos_meta

                items = estructurar_renglones(renglones_txt)
                lic["renglones"] = [r.to_dict() for r in items]

                if n % 10 == 0:
                    logger.info("Procesadas %s/%s licitaciones.", n, total)
            except Exception as e:  # noqa: BLE001
                logger.warning("Lic #%s (%s) falló: %s", n, lic.get("id"), str(e)[:120])

    # --- Precio + margen ACOTADO sobre las mejores licitaciones relevantes --- #
    margenes: dict = {}
    evals_por_lic: dict[str, list[dict]] = {}
    if con_precios:
        relevantes = sorted(
            [l for l in licitaciones if l.get("decision") in ("COTIZAR", "REVISAR") and l.get("renglones")],
            key=lambda l: int(l.get("puntaje", 0) or 0),
            reverse=True,
        )
        presupuesto = config.FULL_PRICE_LIMIT
        for lic in relevantes:
            if presupuesto <= 0:
                break
            evals = []
            for idx, r in enumerate(lic["renglones"]):
                if presupuesto <= 0:
                    break
                if r.get("decision") == "DESCARTAR":
                    continue
                ev = evaluar_renglon(r)
                m = calcular_margen(ev, r)
                margenes[(lic["id"], idx)] = m
                ev["margen"] = m
                evals.append(ev)
                presupuesto -= 1
            if evals:
                evals_por_lic[lic["id"]] = evals

    # --- Histórico --- #
    guardado = db.guardar_inventario_full(licitaciones, margenes)
    ruta_json = db.exportar_inventario_json(
        licitaciones, config.REPORTS_DIR / "inventario_full.json"
    )

    # --- Telegram: solo lo importante --- #
    importantes = sorted(
        [l for l in licitaciones if l.get("decision") == "COTIZAR" and l.get("renglones")],
        key=lambda l: int(l.get("puntaje", 0) or 0),
        reverse=True,
    )[: config.FULL_TELEGRAM_TOP]

    texto = reporte_full(
        total=total,
        licitaciones=licitaciones,
        importantes=importantes,
        evals_por_lic=evals_por_lic,
        guardado=guardado,
        modo=modo,
    )
    if enviar:
        telegram.enviar(texto)

    return {
        "total": total,
        "guardado": guardado,
        "inventario_json": ruta_json,
        "reporte": texto,
    }
