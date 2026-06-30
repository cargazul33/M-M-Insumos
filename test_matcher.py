from radar.pricing.matcher import calcular_match


def test_match_por_codigo():
    item = {"producto": "toner", "codigo": "CE340A", "buscar_py": "HP CE340A"}
    res = {"titulo": "Toner HP CE340A Original", "descripcion": ""}
    match, score = calcular_match(item, res)
    assert match == "EXACTO" and score == 100


def test_no_match():
    item = {"producto": "monitor 24", "buscar_py": "monitor led 24"}
    res = {"titulo": "heladera no frost", "descripcion": ""}
    match, _ = calcular_match(item, res)
    assert match == "NO MATCH"
