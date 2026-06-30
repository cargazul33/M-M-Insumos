from radar.pricing.margin import calcular_margen, margen_legible


def _eval(py="Gs. 1.000.000", ar="$ 400.000", cantidad=10, oficial=""):
    item = {"producto": "TONER", "cantidad": cantidad}
    if oficial:
        item["precio_oficial"] = oficial
    return {
        "item": item,
        "paraguay": [{"fuente": "Nissei", "pais": "PY", "precio": py,
                      "url": "http://py", "valido": True}] if py else [],
        "argentina": [{"fuente": "ML", "pais": "AR", "precio": ar,
                       "url": "http://ar", "valido": True}] if ar else [],
    }


def test_margen_arbitraje_ar_py():
    # PY 1.000.000 Gs * 0.22 = 220.000 ARS ; AR = 400.000 ARS ; margen = 180.000
    m = calcular_margen(_eval())
    assert m["base"] == "arbitraje_ar_py"
    assert m["margen_unit_ars"] == 180000
    assert m["margen_total_ars"] == 1800000  # x10


def test_margen_vs_oficial_tiene_prioridad():
    m = calcular_margen(_eval(oficial="$ 500.000"))
    assert m["base"] == "vs_oficial"
    assert m["margen_unit_ars"] == 280000  # 500.000 - 220.000


def test_sin_referencia_no_calcula():
    m = calcular_margen(_eval(ar=""))
    assert m["margen_unit_ars"] is None
    assert "sin referencia" in margen_legible(m).lower()
