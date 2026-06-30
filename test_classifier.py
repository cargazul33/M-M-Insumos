from radar.parsing.classifier import (
    clasificar_licitacion, clasificar_renglon, normalizar,
)


def test_normalizar_quita_tildes():
    assert normalizar("Climatización") == "climatizacion"


def test_excluye_salud():
    c = clasificar_licitacion("MINISTERIO DE SALUD - compra de medicamentos")
    assert c.decision == "DESCARTAR"


def test_excluye_cpe():
    assert clasificar_licitacion("CONSEJO PROVINCIAL DE EDUCACION").decision == "DESCARTAR"


def test_cotizar_toner():
    assert clasificar_licitacion("Adquisicion de toner y resmas A4").decision == "COTIZAR"


def test_revisar_mobiliario():
    assert clasificar_licitacion("Compra de sillas y escritorios").decision == "REVISAR"


def test_renglon_toner_cotiza():
    r = clasificar_renglon("CARTUCHO DE TONER CE340A negro")
    assert r.decision == "COTIZAR" and "TONER" in r.rubro


def test_renglon_servicio_descarta():
    r = clasificar_renglon("servicio de mantenimiento mensual tracto sucesivo")
    assert r.decision == "DESCARTAR"


def test_climatizacion_equipo_revisa():
    assert clasificar_renglon("aire acondicionado split 3000 frigorias").decision == "REVISAR"
