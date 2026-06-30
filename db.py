"""Persistencia real en SQLite (la V2 tenía un guardar_bd que no guardaba nada).

Guarda cada oportunidad detectada con su decisión y puntaje para poder analizar
históricos (qué rubros aparecen más, evolución temporal, etc.).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime

from radar.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS oportunidades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha        TEXT NOT NULL,
    decision     TEXT,
    puntaje      INTEGER,
    motivo       TEXT,
    texto        TEXT,
    url          TEXT,
    n_renglones  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_op_fecha ON oportunidades(fecha);
CREATE INDEX IF NOT EXISTS idx_op_decision ON oportunidades(decision);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.executescript(_SCHEMA)


def guardar_oportunidades(oportunidades: list[dict]) -> int:
    if not oportunidades:
        return 0
    init_db()
    fecha = datetime.now().isoformat(timespec="seconds")
    filas = [
        (
            fecha,
            op.get("decision", ""),
            int(op.get("puntaje", 0) or 0),
            op.get("motivo", ""),
            (op.get("texto", "") or "")[:1000],
            op.get("visualizar_url", ""),
            len(op.get("renglones", []) or []),
        )
        for op in oportunidades
    ]
    with _conn() as con:
        con.executemany(
            "INSERT INTO oportunidades "
            "(fecha, decision, puntaje, motivo, texto, url, n_renglones) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            filas,
        )
    return len(filas)


def estadisticas() -> dict:
    init_db()
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM oportunidades").fetchone()[0]
        por_decision = {
            row["decision"]: row["n"]
            for row in con.execute(
                "SELECT decision, COUNT(*) n FROM oportunidades GROUP BY decision"
            )
        }
    return {"total": total, "por_decision": por_decision}


# --------------------------------------------------------------------------- #
# Inventario completo (modo --full): licitaciones + documentos + renglones
# --------------------------------------------------------------------------- #
_SCHEMA_FULL = """
CREATE TABLE IF NOT EXISTS lic_full (
    id_lic       TEXT,
    fecha_scan   TEXT,
    pagina       INTEGER,
    decision     TEXT,
    puntaje      INTEGER,
    motivo       TEXT,
    texto        TEXT,
    url          TEXT,
    n_docs       INTEGER DEFAULT 0,
    n_renglones  INTEGER DEFAULT 0,
    PRIMARY KEY (id_lic, fecha_scan)
);
CREATE TABLE IF NOT EXISTS doc_full (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    id_lic       TEXT,
    fecha_scan   TEXT,
    nombre       TEXT,
    tipo         TEXT,
    ruta_local   TEXT,
    n_renglones  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS renglon_full (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    id_lic        TEXT,
    fecha_scan    TEXT,
    producto      TEXT,
    codigo        TEXT,
    cantidad      INTEGER,
    rubro         TEXT,
    decision      TEXT,
    puntaje       INTEGER,
    precio_oficial TEXT,
    costo_py_ars  INTEGER,
    margen_unit_ars INTEGER,
    margen_total_ars INTEGER
);
CREATE INDEX IF NOT EXISTS idx_lic_full_fecha ON lic_full(fecha_scan);
CREATE INDEX IF NOT EXISTS idx_renglon_full_dec ON renglon_full(decision);
"""


def init_db_full() -> None:
    with _conn() as con:
        con.executescript(_SCHEMA_FULL)


def guardar_inventario_full(licitaciones: list[dict], margenes: dict | None = None) -> dict:
    """Guarda el inventario completo de una corrida --full.

    `margenes` opcional: dict {(id_lic, idx_renglon): margen_dict} para enriquecer.
    """
    if not licitaciones:
        return {"licitaciones": 0, "documentos": 0, "renglones": 0}
    init_db_full()
    margenes = margenes or {}
    fecha = datetime.now().isoformat(timespec="seconds")
    n_lic = n_doc = n_ren = 0

    with _conn() as con:
        for lic in licitaciones:
            id_lic = lic.get("id", "")
            docs = lic.get("documentos", []) or []
            rens = lic.get("renglones", []) or []
            con.execute(
                "INSERT OR REPLACE INTO lic_full "
                "(id_lic, fecha_scan, pagina, decision, puntaje, motivo, texto, url, n_docs, n_renglones) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (id_lic, fecha, lic.get("pagina", 0), lic.get("decision", ""),
                 int(lic.get("puntaje", 0) or 0), lic.get("motivo", ""),
                 (lic.get("texto", "") or "")[:1000], lic.get("visualizar_url", ""),
                 len(docs), len(rens)),
            )
            n_lic += 1
            for d in docs:
                con.execute(
                    "INSERT INTO doc_full (id_lic, fecha_scan, nombre, tipo, ruta_local, n_renglones) "
                    "VALUES (?,?,?,?,?,?)",
                    (id_lic, fecha, d.get("nombre", ""), d.get("tipo", ""),
                     d.get("ruta_local", ""), int(d.get("n_renglones", 0) or 0)),
                )
                n_doc += 1
            for idx, r in enumerate(rens):
                m = margenes.get((id_lic, idx), {})
                con.execute(
                    "INSERT INTO renglon_full "
                    "(id_lic, fecha_scan, producto, codigo, cantidad, rubro, decision, puntaje, "
                    "precio_oficial, costo_py_ars, margen_unit_ars, margen_total_ars) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (id_lic, fecha, r.get("producto", ""), r.get("codigo", ""),
                     r.get("cantidad"), r.get("rubro", ""), r.get("decision", ""),
                     int(r.get("puntaje", 0) or 0), r.get("precio_oficial", ""),
                     m.get("costo_py_ars"), m.get("margen_unit_ars"), m.get("margen_total_ars")),
                )
                n_ren += 1

    return {"licitaciones": n_lic, "documentos": n_doc, "renglones": n_ren}


def exportar_inventario_json(licitaciones: list[dict], ruta) -> str:
    import json as _json
    from pathlib import Path as _Path

    ruta = _Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "total": len(licitaciones),
        "licitaciones": licitaciones,
    }
    ruta.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(ruta)
