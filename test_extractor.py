from radar.parsing.extractor import estructurar_renglon, extraer_codigo, extraer_cantidad


def test_extraer_codigo():
    assert extraer_codigo("CARTUCHO DE TONER Codigo CE340A") == "CE340A"


def test_extraer_cantidad():
    assert extraer_cantidad("Cantidad 12 unidades") == 12


def test_estructurar_toner():
    r = estructurar_renglon("CARTUCHO DE TONER; Marca Sugerida: HP - Codigo CE340A - Cantidad 12")
    assert r.codigo == "CE340A"
    assert r.decision == "COTIZAR"
    assert "Paraguay" in r.buscar_py
