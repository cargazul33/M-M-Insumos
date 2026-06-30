# Changelog

## V26.0 — Full Crawler Diario Combinado

- Combina V25 profundo con motor estricto del Prompt Maestro.
- Una corrida profunda diaria por GitHub Actions.
- Recorre paginación, entra a detalles y descarga múltiples adjuntos.
- Lee PDF / DOCX / XLSX / TXT / CSV.
- Paraguay primero real con variantes de búsqueda y Brave PY.
- Argentina solo si Paraguay no entrega publicación activa útil.
- Ganador solo con precio publicado + enlace directo útil + publicación activa.
- Mantiene margen, histórico SQLite/JSON y Telegram ejecutivo.
- Sin Excel y sin artifacts visibles.

## V25.0 — Scan profundo CODINEU (modo --full) + margen

Nuevo modo `python -m radar --full`: barrido profundo diario que recorre TODO
el portal, no solo la primera página ni solo los rubros M&M.

Flujo del modo full:
- **Todas las páginas**: paginación con varias estrategias GeneXus + selector
  configurable (`CODI_NEXT_SELECTOR`) por si el portal usa un control propio.
- **Todas las licitaciones publicadas** (sin filtro de rubro; la clasificación
  se guarda como metadato).
- **Entra a cada detalle** y **descarga TODOS los adjuntos**.
- **Lee PDF / Word (.docx) / Excel (.xlsx)** y extrae renglones de todos
  (Word/Excel sin dependencias nuevas: openpyxl + parseo XML del .docx).
- **Clasifica** rubro por rubro.
- **Cotiza** (acotado a `FULL_PRICE_LIMIT` renglones de las mejores licitaciones)
  en Paraguay → Brave → Argentina.
- **Calcula margen posible** (nuevo `pricing/margin.py`): Argentina − Paraguay, o
  vs precio oficial del pliego si está publicado; por unidad, % y por cantidad.
- **Guarda histórico** completo en SQLite (lic_full / doc_full / renglon_full) +
  exporta `inventario_full.json`.
- **Telegram solo lo importante**: top COTIZAR con precio + margen; el resto
  queda en el histórico/artifact.

Otros:
- **Bug de moneda corregido**: "$400.000" (separador de miles AR) se leía como
  400 pesos. Ahora distingue miles vs decimales correctamente.
- Workflow: nuevo job `scan-profundo` (1 vez/día, madrugada) que sube el
  inventario completo como artifact (PDFs/Word/Excel + JSON + SQLite, 30 días).
- +6 tests (Word/Excel, margen, paginación con page simulada) -> 31 en total.

## V24.0 — Motor de decisión Prompt Maestro

Implementa el "PROMPT MAESTRO DEFINITIVO" como reglas de código deterministas
(`radar/pricing/decision.py`), por encima del scraping de la V23:

- **Paraguay primero REAL**: Argentina solo puede ganar si Paraguay no entregó
  publicación activa útil con precio. Antes, un precio AR más barato podía
  ganarle a Paraguay por score; ahora no.
- **Jerarquía del ganador**: EXACTO limpio más barato de PY -> CERCANO
  DEFENDIBLE PY -> (paquete si el renglón es mixto) -> Argentina -> referencia.
- **Renglón mixto (bien+servicio)**: el extractor ahora marca `requiere_servicio`
  / `renglon_mixto`, y el motor emite la advertencia correspondiente.
- **Fusibles/advertencias** con el texto EXACTO del prompt (admisibilidad, stock,
  bien+servicio, SIN MATCH EXACTO LIMPIO, SIN HALLAZGO, SIN PUBLICACIÓN ACTIVA).
- **Modo producción** (`--modo produccion`): salida terse `Ítem N: $PRECIO — ENLACE`.
- **Modo auditoría** (`--modo auditoria`): match, país, estado comercial, semáforo,
  fuentes descartadas y motivo, como pide el prompt.
- +5 tests del motor de decisión (24 en total).

## V23.0 — Hybrid Brave Perfect

- Combina la base limpia de V3 con el motor web de V22.
- Agrega Brave Search API (`BRAVE_API_KEY`).
- Motor de precio: proveedores Paraguay → Brave Paraguay → proveedores Argentina → Brave Argentina.
- Telegram rediseñado para decisión rápida desde celular.
- Elimina artifacts del workflow.
- Agrega cache de `data/` para historial/dedupe sin subir Excel ni reportes.
- Mantiene `python -m radar --selftest` antes de correr producción.
- Ajusta clasificación: limpieza y policía ya no se descartan automáticamente; se revisan según rubro.

## V3.0

- Arquitectura modular `radar/`.
- CLI, tests, SQLite, dedupe, workflow con self-test.

## V22.0

- Primer motor Brave + Telegram ejecutivo.
