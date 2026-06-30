from radar.pricing import currency


def test_limpiar_numero_formato_py():
    assert currency.limpiar_numero("Gs. 1.250.000") == 1250000.0


def test_detectar_moneda():
    assert currency.detectar_moneda("Gs. 1.000") == "PYG"
    assert currency.detectar_moneda("U$S 120") == "USD"
    assert currency.detectar_moneda("$ 5000") == "ARS"


def test_convertir_pyg(monkeypatch):
    monkeypatch.setattr(currency.config, "PYG_TO_ARS", 0.22)
    assert currency.convertir_a_ars("Gs. 1.000.000") == 220000


def test_precio_invalido():
    assert currency.convertir_a_ars("consultar") is None
