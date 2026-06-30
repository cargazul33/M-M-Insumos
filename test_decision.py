from radar.pricing.decision import decidir, ADV_BIEN_SERVICIO


def _py_ar(precio_py=True, precio_ar=True, mixto=False, valido_py=True):
    return {
        "item": {"producto": "TONER CE340A", "codigo": "CE340A", "renglon_mixto": mixto},
        "paraguay": [{
            "fuente": "Nissei", "pais": "PY",
            "precio": "Gs. 1.000.000" if precio_py else "",
            "url": "https://nissei.com/py/toner-ce340a",
            "match": "EXACTO", "stock": True, "stock_texto": "disponible",
            "titulo": "Toner CE340A", "valido": valido_py, "semaforo": "LIMPIO",
            "link_directo": True,
        }],
        "argentina": [{
            "fuente": "Mercado Libre AR", "pais": "AR",
            "precio": "$ 50.000" if precio_ar else "",
            "url": "https://articulo.ml.com.ar/ce340a",
            "match": "EXACTO", "stock": True, "titulo": "Toner CE340A",
            "valido": True, "semaforo": "LIMPIO",
        }],
    }


def test_paraguay_prima_aunque_argentina_mas_barata():
    d = decidir(_py_ar())
    assert d.estado == "GANADOR"
    assert d.pais == "PY"


def test_argentina_solo_si_paraguay_vacio():
    ev = _py_ar(precio_py=False)
    ev["paraguay"][0]["url"] = ""  # sin link util en PY
    d = decidir(ev)
    assert d.pais == "AR"


def test_renglon_mixto_advierte_servicio():
    d = decidir(_py_ar(mixto=True))
    assert ADV_BIEN_SERVICIO in d.advertencias


def test_sin_hallazgo():
    d = decidir({"item": {"producto": "x"}, "paraguay": [], "argentina": []})
    assert d.estado == "SIN_HALLAZGO"


def test_linea_produccion_formato():
    d = decidir(_py_ar())
    linea = d.linea_produccion(1)
    assert linea.startswith("Ítem 1:")
    assert "http" in linea
