from pathlib import Path
from radar.parsing.documents import leer_documento, leer_docx, leer_xlsx

FX = Path(__file__).parent / "fixtures"


def test_leer_xlsx_extrae_texto_y_renglones():
    texto = leer_xlsx(FX / "pliego_demo.xlsx")
    assert "CE340A" in texto and "MONITOR" in texto
    info = leer_documento(FX / "pliego_demo.xlsx")
    assert info["tipo"] == "xlsx"
    assert any("CARTUCHO" in r or "TONER" in r for r in info["renglones"])


def test_leer_docx_extrae_texto():
    texto = leer_docx(FX / "pliego_demo.docx")
    assert "CE340A" in texto and "ESTABILIZADOR" in texto
    info = leer_documento(FX / "pliego_demo.docx")
    assert info["tipo"] == "docx"
    assert info["renglones"]


def test_router_extension_desconocida_no_rompe():
    info = leer_documento(FX / "no_existe.rar")
    assert info["renglones"] == []
