"""Interfaz de línea de comandos de Radar M&M.

Comandos:
  python -m radar              -> corrida normal (necesita secrets)
  python -m radar --dry-run    -> corre todo menos el envío a Telegram
  python -m radar --selftest   -> prueba OFFLINE de la lógica (sin red ni secrets)
  python -m radar --status     -> muestra estado de configuración
  python -m radar --stats      -> estadísticas del SQLite histórico
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from radar import config
from radar.logging_setup import get_logger, setup_logging

logger = get_logger("cli")


def _selftest() -> int:
    """Valida el núcleo (clasificación, extracción, ranking) sin red ni secrets."""
    from radar.parsing.classifier import clasificar_licitacion
    from radar.parsing.extractor import estructurar_renglones
    from radar.parsing.pdf import detectar_renglones
    from radar.pricing.ranking import evaluar_renglones
    from radar.report import reporte_completo

    sample = (Path(__file__).parent / "samples" / "pliego_demo.txt").read_text(
        encoding="utf-8"
    )

    print("== 1. Clasificación de la licitación ==")
    clasif = clasificar_licitacion(sample)
    print(f"   decisión={clasif.decision} puntaje={clasif.puntaje} :: {clasif.motivo}")
    assert clasif.decision == "COTIZAR", "esperaba COTIZAR"

    print("\n== 2. Detección de renglones ==")
    renglones_txt = detectar_renglones(sample)
    for r in renglones_txt:
        print(f"   - {r[:80]}")
    assert renglones_txt, "no se detectaron renglones"

    print("\n== 3. Estructuración ==")
    items = estructurar_renglones(renglones_txt)
    for it in items:
        print(
            f"   [{it.decision:9}] {it.producto:28} cod={it.codigo or '-':8} "
            f"cant={it.cantidad} -> buscar_py='{it.buscar_py}'"
        )
    assert any(i.codigo == "CE340A" for i in items), "no extrajo el código CE340A"
    assert any(i.decision == "DESCARTAR" for i in items), "no descartó el servicio"

    print("\n== 4. Ranking de precios (self-test offline) ==")
    # Evita llamadas reales a proveedores/Brave en el self-test de GitHub.
    from radar.pricing import ranking as _ranking

    def _fake_py(query):
        return [{
            "fuente": "Nissei", "proveedor": "Nissei", "pais": "PY",
            "query": query, "titulo": query, "descripcion": query,
            "precio": "Gs. 1.000.000", "url": "https://nissei.com/py/producto-demo",
            "stock": True, "stock_texto": "disponible", "estado": "SELFTEST",
            "link_directo": True,
        }]

    _ranking.buscar_en_paraguay = _fake_py
    _ranking.buscar_en_argentina = lambda query: []
    _ranking.buscar_web_general = lambda query, pais="PY": []

    evals = evaluar_renglones([i.to_dict() for i in items[:3]], limite=3)
    for ev in evals:
        g = ev.get("ganador") or {}
        print(
            f"   {ev['item'].get('producto', ''):28} estado={ev['estado']:15} "
            f"ganador={g.get('fuente', '-')} precio={g.get('precio') or '-'}"
        )

    print("\n== 4b. Motor de decisión (Prompt Maestro) ==")
    from radar.pricing.decision import decidir

    # Renglón con ganador PY + un resultado AR más barato: PY debe primar igual.
    ev_py = {
        "item": {"producto": "TONER CE340A", "codigo": "CE340A", "renglon_mixto": False},
        "paraguay": [{
            "fuente": "Nissei", "pais": "PY", "precio": "Gs. 1.000.000",
            "url": "https://nissei.com/py/toner-ce340a", "match": "EXACTO",
            "stock": True, "stock_texto": "disponible", "titulo": "Toner CE340A",
            "valido": True, "semaforo": "LIMPIO", "link_directo": True,
        }],
        "argentina": [{
            "fuente": "Mercado Libre AR", "pais": "AR", "precio": "$ 50.000",
            "url": "https://articulo.ml.com.ar/ce340a", "match": "EXACTO",
            "stock": True, "titulo": "Toner CE340A", "valido": True,
        }],
    }
    d = decidir(ev_py)
    print("   ", d.linea_produccion(1).replace("\n", " | "))
    assert d.pais == "PY", "Paraguay debe primar aunque Argentina sea más barata"

    # Renglón mixto (bien+servicio) -> advertencia de servicio.
    ev_mixto = {
        "item": {"producto": "AIRE ACONDICIONADO con instalacion", "renglon_mixto": True},
        "paraguay": [{
            "fuente": "Shopping China", "pais": "PY", "precio": "Gs. 3.000.000",
            "url": "https://shoppingchina.com.py/split", "match": "CERCANO DEFENDIBLE",
            "stock": True, "titulo": "Split 3000", "valido": True, "semaforo": "LIMPIO",
        }],
        "argentina": [],
    }
    dm = decidir(ev_mixto)
    assert any("SERVICIO" in a for a in dm.advertencias), "falta advertencia bien+servicio"
    print("   mixto -> advertencia OK")

    # Sin nada -> SIN HALLAZGO.
    dn = decidir({"item": {"producto": "x"}, "paraguay": [], "argentina": []})
    assert dn.estado == "SIN_HALLAZGO"
    print("   sin hallazgo OK")

    print("\n== 5. Reporte (modo auditoría) ==")
    op = {
        "decision": clasif.decision, "puntaje": clasif.puntaje,
        "motivo": clasif.motivo, "texto": sample[:200],
        "renglones": [i.to_dict() for i in items],
    }
    reporte = reporte_completo([op], descartadas=0, total_detectadas=1,
                               evaluaciones_por_op={0: evals}, modo="auditoria")
    print(reporte[:1100])

    print("\n== 6. Documentos multi-formato + margen (modo --full) ==")
    from radar.parsing.documents import leer_docx, leer_xlsx
    from radar.pricing.margin import calcular_margen, margen_legible

    fx = Path(__file__).parent.parent / "tests" / "fixtures"
    if (fx / "pliego_demo.xlsx").exists():
        txt_xlsx = leer_xlsx(fx / "pliego_demo.xlsx")
        print(f"   xlsx -> {len(txt_xlsx)} chars, CE340A={'CE340A' in txt_xlsx}")
    if (fx / "pliego_demo.docx").exists():
        txt_docx = leer_docx(fx / "pliego_demo.docx")
        print(f"   docx -> {len(txt_docx)} chars, ESTABILIZADOR={'ESTABILIZADOR' in txt_docx}")

    ev_m = {
        "item": {"producto": "TONER", "cantidad": 10},
        "paraguay": [{"fuente": "Nissei", "pais": "PY", "precio": "Gs. 1.000.000",
                      "url": "http://py", "valido": True}],
        "argentina": [{"fuente": "ML", "pais": "AR", "precio": "$ 400.000",
                       "url": "http://ar", "valido": True}],
    }
    m = calcular_margen(ev_m)
    print(f"   margen -> {margen_legible(m)}")
    assert m["margen_unit_ars"] == 180000, "margen arbitraje incorrecto"
    print("   margen OK (AR 400.000 − PY 220.000 = 180.000 x10)")

    print("\n✅ SELF-TEST OK — núcleo + motor de decisión Prompt Maestro funcionan.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar", description="Radar M&M")
    parser.add_argument("--selftest", action="store_true",
                        help="prueba offline del núcleo (sin red ni secrets)")
    parser.add_argument("--dry-run", action="store_true",
                        help="corre el pipeline sin enviar a Telegram")
    parser.add_argument("--no-precios", action="store_true",
                        help="omite la búsqueda de precios")
    parser.add_argument("--modo", choices=["ejecutivo", "produccion", "auditoria"],
                        default="ejecutivo",
                        help="formato del reporte (Prompt Maestro: produccion/auditoria)")
    parser.add_argument("--full", action="store_true",
                        help="scan PROFUNDO: todas las páginas, todas las licitaciones, "
                             "todos los documentos, extracción + precios + margen + histórico")
    parser.add_argument("--status", action="store_true",
                        help="muestra estado de configuración")
    parser.add_argument("--stats", action="store_true",
                        help="estadísticas del histórico SQLite")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    setup_logging(verbose=args.verbose)

    if args.status:
        print(f"{config.APP_NAME} {config.APP_VERSION}")
        print("Estado:", config.status_resumen())
        return 0

    if args.stats:
        from radar.store import db
        print(db.estadisticas())
        return 0

    if args.selftest:
        try:
            return _selftest()
        except AssertionError as e:
            print(f"❌ SELF-TEST FALLÓ: {e}", file=sys.stderr)
            return 1

    # Corrida normal o full
    from radar.pipeline import ejecutar, ejecutar_full

    if not config.is_codi_configured():
        print("❌ Faltan secrets de CO.DI.NEU. Probá: python -m radar --selftest",
              file=sys.stderr)
        return 2

    logger.info("Iniciando %s %s | %s", config.APP_NAME, config.APP_VERSION,
                config.status_resumen())
    try:
        if args.full:
            resultado = ejecutar_full(
                enviar=not args.dry_run, con_precios=not args.no_precios, modo=args.modo
            )
            g = resultado.get("guardado", {})
            logger.info(
                "Fin FULL: %s licitaciones, %s docs, %s renglones guardados.",
                resultado["total"], g.get("documentos", 0), g.get("renglones", 0),
            )
            logger.info("Inventario JSON: %s", resultado.get("inventario_json"))
        else:
            resultado = ejecutar(
                enviar=not args.dry_run, con_precios=not args.no_precios, modo=args.modo
            )
            logger.info(
                "Fin: %s detectadas, %s nuevas, %s guardadas.",
                resultado["total"], resultado["nuevas"], resultado["guardadas"],
            )
        if args.dry_run:
            print(resultado["reporte"])
        return 0
    except Exception as e:  # noqa: BLE001
        logger.exception("Error en la corrida: %s", e)
        from radar.notify import telegram
        telegram.enviar(f"❌ Error Radar M&M {config.APP_VERSION}: {str(e)[:300]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
