# Radar M&M V26 — Full Crawler Diario + Prompt Maestro

Radar para M&M Insumos orientado a revisar CODINEU en profundidad una vez por día y avisar por Telegram solo lo accionable.

## Flujo V26

```text
CODINEU completo
→ todas las páginas
→ todas las licitaciones publicadas
→ detalle una por una
→ descarga de todos los adjuntos posibles
→ lectura PDF / DOCX / XLSX / TXT / CSV
→ extracción de renglones
→ clasificación
→ Paraguay primero real
→ Brave Web Paraguay
→ Argentina solo si Paraguay falla
→ precio base ganador
→ margen estimado
→ histórico SQLite/JSON
→ Telegram ejecutivo
```

## Secrets requeridos

- `CODI_USER`
- `CODI_PASS`
- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `BRAVE_API_KEY`

Opcionales:

- `GMAIL_USER`
- `GMAIL_APP_PASSWORD`

## Comandos

```bash
python -m radar --selftest
python -m radar --status
python -m radar --full --modo ejecutivo
python -m radar --full --modo produccion
python -m radar --full --modo auditoria
```

## Filosofía

Una corrida profunda diaria. Revisa todo, descarga todo lo posible, guarda histórico y manda a Telegram solo las oportunidades fuertes. No genera Excel ni sube artifacts visibles.

El motor de decisión aplica el Prompt Maestro: precio publicado, enlace directo útil, publicación activa, Paraguay primero real y Argentina solo si Paraguay no entrega publicación activa útil.
