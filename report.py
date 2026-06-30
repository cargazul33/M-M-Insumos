"""Reporte ejecutivo para Telegram.

Diseñado para celular: menos ruido, más decisión. Muestra licitación, pliego,
ítems clave y precio base ganador Paraguay/Brave/Argentina.
"""

from __future__ import annotations

import html
import re
from datetime import datetime

from radar.config import APP_VERSION
from radar.pricing.currency import precio_legible
from radar.pricing.decision import bloque_auditoria, decidir
from radar.pricing.validator import contiene_precio, link_directo

SEPARADOR = "━━━━━━━━━━━━━━━━━━━━"


def _esc(t) -> str:
    return html.escape(str(t or ""), quote=False)


def _limpiar(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip()


def _recortar(t: str, n: int = 240) -> str:
    t = _limpiar(t)
    return t[:n] + ("…" if len(t) > n else "")


def _prioridad(decision: str, puntaje: int) -> str:
    if puntaje >= 85 or decision == "COTIZAR":
        return "🟢 COTIZAR YA"
    if puntaje >= 60 or decision == "REVISAR":
        return "🟡 REVISAR"
    return "🔴 DESCARTAR"


def encabezado(n_oportunidades: int, descartadas: int, nuevas: int) -> str:
    return (
        f"🚨 <b>Radar M&amp;M {APP_VERSION}</b>\n"
        f"🌐 Motor: Full Crawler Diario → CODINEU completo → Documentos → Paraguay → Brave → Argentina → Telegram\n"
        f"📋 Detectadas: {n_oportunidades} | 🆕 Nuevas: {nuevas} | 🔴 Descartadas: {descartadas}\n"
        f"🕒 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    )


def _precio_linea(g: dict) -> str:
    precio = g.get("precio") or ""
    if not contiene_precio(g):
        return "SIN PRECIO PUBLICADO LIMPIO"
    return f"{_esc(precio)} ≈ {_esc(precio_legible(precio))} ARS"


def _fuente_linea(g: dict) -> str:
    fuente = g.get("fuente") or g.get("proveedor") or "-"
    pais = g.get("pais") or "-"
    origen = g.get("origen") or ""
    extra = " | Brave" if origen == "BRAVE_WEB" else ""
    return f"{_esc(fuente)} / {_esc(pais)}{extra}"


def _validacion_linea(g: dict) -> str:
    match = g.get("match") or "REVISAR"
    semaforo = g.get("semaforo") or "REVISAR"
    directo = "directo" if (link_directo(g) or g.get("link_directo") is True) else "revisión"
    return f"Match: {_esc(match)} | Validación: {_esc(semaforo)} | Link: {directo}"


def _bloque_decisiones(evaluaciones: list[dict], modo: str) -> str:
    """Bloque Prompt Maestro: línea de producción + (opcional) auditoría."""
    if not evaluaciones:
        return ""
    out = "\n🎯 <b>Decisión M&amp;M (Paraguay primero):</b>\n"
    for idx, ev in enumerate(evaluaciones[:3], start=1):
        d = decidir(ev)
        out += f"<code>{_esc(d.linea_produccion(idx))}</code>\n"
        if modo == "auditoria":
            out += f"{_esc(bloque_auditoria(d))}\n"
    return out


def _bloque_precios(evaluaciones: list[dict]) -> str:
    if not evaluaciones:
        return "\n📦 <b>Ítems:</b> sin renglones cotizables claros en esta corrida.\n"

    out = "\n📦 <b>Ítems clave + precio base ganador</b>\n"
    for idx, ev in enumerate(evaluaciones[:3], start=1):
        item = ev.get("item", {}) or {}
        g = ev.get("ganador") or {}
        producto = item.get("producto") or item.get("texto_original") or "ítem"
        codigo = item.get("codigo") or ""
        cantidad = item.get("cantidad") or ""
        rubro = item.get("rubro") or item.get("categoria") or ""

        out += f"\n<b>{idx}) {_esc(_recortar(producto, 90))}</b>"
        if codigo:
            out += f" [{_esc(codigo)}]"
        out += "\n"
        if cantidad:
            out += f"   Cantidad: {_esc(cantidad)}\n"
        if rubro:
            out += f"   Rubro: {_esc(rubro)}\n"

        if g:
            out += f"   🥇 {_fuente_linea(g)}\n"
            out += f"   💵 {_precio_linea(g)}\n"
            out += f"   🎯 {_validacion_linea(g)}\n"
            if g.get("url"):
                out += f"   🔗 {_esc(g.get('url'))}\n"
            errores = g.get("errores_validacion") or []
            if errores and not contiene_precio(g):
                out += f"   ⚠️ {_esc('; '.join(str(e) for e in errores[:2]))}\n"
        else:
            out += "   SIN HALLAZGO VERIFICABLE. Revisión manual necesaria.\n"

        motivo = ev.get("motivo") or ""
        if motivo and not contiene_precio(g):
            out += f"   Nota: {_esc(_recortar(motivo, 120))}\n"
    return out


def _accion(op: dict, evaluaciones: list[dict]) -> str:
    puntaje = int(op.get("puntaje", 0) or 0)
    con_precio = sum(1 for ev in evaluaciones or [] if contiene_precio(ev.get("ganador") or {}))
    if puntaje >= 85 and con_precio:
        return "✅ Cotizar primero. Hay precio base para arrancar; validar stock, exactitud y margen."
    if puntaje >= 85:
        return "✅ Cotizar primero, pero faltan precios limpios en algunos ítems."
    if puntaje >= 60 and con_precio:
        return "🟡 Revisar rápido. Puede servir si el lote es simple y el margen cierra."
    if puntaje >= 60:
        return "🟡 Revisar solo si los ítems son fáciles de conseguir."
    return "🔴 Baja prioridad."


def _extraer_fecha(texto: str) -> str:
    m = re.search(r"\b(\d{2}/\d{2}/\d{2,4}\s+\d{1,2}:\d{2})\b", texto or "")
    return m.group(1) if m else ""


def bloque_oportunidad(idx: int, op: dict, evaluaciones: list[dict] | None = None,
                       modo: str = "ejecutivo") -> str:
    evaluaciones = evaluaciones or []
    puntaje = int(op.get("puntaje", 0) or 0)
    decision = op.get("decision") or "REVISAR"
    texto = op.get("texto", "")
    fecha = _extraer_fecha(texto)

    out = (
        f"\n{SEPARADOR}\n"
        f"<b>#{idx} — {_esc(_prioridad(decision, puntaje))} {puntaje}/100</b>\n"
        f"📌 {_esc(_recortar(texto, 320))}\n"
    )

    if op.get("motivo"):
        out += f"🧠 {_esc(op.get('motivo'))}\n"
    if fecha:
        out += f"📅 Apertura: {_esc(fecha)}\n"

    descargas = op.get("descargas") or []
    if descargas:
        d = descargas[0]
        out += f"📄 Pliego: {_esc(d.get('nombre') or 'pliego')}\n"
        if d.get("href"):
            out += f"🔗 Descargar: {_esc(d.get('href'))}\n"

    if op.get("visualizar_url"):
        out += f"🌐 Ver licitación: {_esc(op.get('visualizar_url'))}\n"

    if op.get("pdf_bajado"):
        out += f"✅ PDF leído: {_esc(op.get('pdf_bajado'))}\n"

    out += _bloque_precios(evaluaciones)
    out += _bloque_decisiones(evaluaciones, modo)
    out += f"\n🤖 <b>Acción:</b> {_esc(_accion(op, evaluaciones))}\n"
    return out


def reporte_completo(
    nuevas: list[dict],
    descartadas: int,
    total_detectadas: int,
    evaluaciones_por_op: dict[int, list[dict]] | None = None,
    modo: str = "ejecutivo",
) -> str:
    evaluaciones_por_op = evaluaciones_por_op or {}
    if not nuevas:
        return encabezado(total_detectadas, descartadas, 0) + "\nSin oportunidades nuevas/prioritarias en esta corrida.\n"

    partes = [encabezado(total_detectadas, descartadas, len(nuevas))]
    for i, op in enumerate(nuevas, start=1):
        partes.append(bloque_oportunidad(i, op, evaluaciones_por_op.get(i - 1), modo=modo))
    partes.append("\nSin Excel. Sin artifacts. Telegram manda solo lo accionable.")
    return "\n".join(partes).strip()


# --------------------------------------------------------------------------- #
# Reporte del modo FULL (crawl profundo diario)
# --------------------------------------------------------------------------- #
def _contar_por_decision(licitaciones: list[dict]) -> dict:
    out = {"COTIZAR": 0, "REVISAR": 0, "DESCARTAR": 0}
    for l in licitaciones or []:
        out[l.get("decision", "DESCARTAR")] = out.get(l.get("decision", "DESCARTAR"), 0) + 1
    return out


def reporte_full(total, licitaciones, importantes, evals_por_lic, guardado, modo="ejecutivo") -> str:
    from radar.pricing.decision import decidir
    from radar.pricing.margin import margen_legible

    por_dec = _contar_por_decision(licitaciones)
    n_docs = sum(len(l.get("documentos", []) or []) for l in licitaciones)
    n_ren = sum(len(l.get("renglones", []) or []) for l in licitaciones)

    cab = (
        f"🛰️ <b>Radar M&amp;M {APP_VERSION} — Scan profundo CODINEU</b>\n"
        f"🕒 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"📊 Licitaciones: {total} "
        f"(🟢 {por_dec.get('COTIZAR',0)} / 🟡 {por_dec.get('REVISAR',0)} / 🔴 {por_dec.get('DESCARTAR',0)})\n"
        f"📄 Documentos bajados: {n_docs} | 📦 Renglones: {n_ren}\n"
        f"💾 Histórico: {guardado.get('licitaciones',0)} lic / "
        f"{guardado.get('documentos',0)} docs / {guardado.get('renglones',0)} renglones\n"
    )

    if not importantes:
        return (cab + "\nNo hay licitaciones COTIZAR con renglones esta corrida.").strip()

    partes = [cab, f"\n🎯 <b>Top {len(importantes)} para cotizar:</b>"]
    for i, lic in enumerate(importantes, start=1):
        partes.append(f"\n{SEPARADOR}\n<b>#{i} — 🟢 {lic.get('puntaje',0)}/100</b>")
        partes.append(f"📌 {_esc(_recortar(lic.get('texto',''), 240))}")
        if lic.get("visualizar_url"):
            partes.append(f"🌐 {_esc(lic.get('visualizar_url'))}")
        docs = lic.get("documentos", []) or []
        if docs:
            tipos = ", ".join(sorted({d.get("tipo", "?") for d in docs}))
            partes.append(f"📄 {len(docs)} adjunto(s): {_esc(tipos)}")

        evals = evals_por_lic.get(lic.get("id"), [])
        if evals:
            partes.append("📦 <b>Ítems + precio base + margen:</b>")
            for idx, ev in enumerate(evals[:4], start=1):
                item = ev.get("item", {}) or {}
                d = decidir(ev)
                linea = d.linea_produccion(idx).split("\n")[0]
                partes.append(f"<code>{_esc(linea)}</code>")
                m = ev.get("margen") or {}
                partes.append(f"   💹 Margen: {_esc(margen_legible(m))}")
        else:
            partes.append("📦 Renglones detectados; sin precio en esta corrida.")
    partes.append("\nInventario completo guardado en data/ (JSON + SQLite). Sin Excel. Sin artifacts. Telegram = solo lo accionable.")
    return "\n".join(partes).strip()
