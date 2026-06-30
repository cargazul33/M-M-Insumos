from radar.pricing import ranking


def test_evaluar_renglon_offline():
    # Sin red: los proveedores degradan a referencia, no debe explotar.
    item = {"producto": "TONER", "codigo": "CE340A",
            "buscar_py": "HP CE340A Paraguay", "buscar_ar": "HP CE340A Argentina",
            "especificaciones": {}}
    ev = ranking.evaluar_renglon(item, incluir_argentina=False)
    assert "resultados" in ev and ev["estado"] in {"CON_PRECIO", "SOLO_REFERENCIA"}
