"""Test de paginación de scan_completo con una página simulada (sin red)."""
from radar.sources import codi


class FakePage:
    """Simula 3 páginas de licitaciones y luego se queda sin 'siguiente'."""
    def __init__(self):
        self.pagina = 0
        self.paginas = [
            [{"id": "a", "texto": "x" * 50, "visualizar_url": "u_a"},
             {"id": "b", "texto": "y" * 50, "visualizar_url": "u_b"}],
            [{"id": "c", "texto": "z" * 50, "visualizar_url": "u_c"}],
            [{"id": "c", "texto": "z" * 50, "visualizar_url": "u_c"}],  # repetida -> corta
        ]

    def goto(self, *a, **k): pass
    def wait_for_timeout(self, *a, **k): pass


def test_scan_completo_pagina_y_dedupe(monkeypatch):
    fake = FakePage()

    monkeypatch.setattr(codi, "_aplicar_filtros", lambda page: None)

    def fake_leer_filas(page):
        idx = min(page.pagina, len(page.paginas) - 1)
        return page.paginas[idx]

    def fake_siguiente(page):
        if page.pagina < len(page.paginas) - 1:
            page.pagina += 1
            return True
        return False

    monkeypatch.setattr(codi, "leer_filas_pagina", fake_leer_filas)
    monkeypatch.setattr(codi, "_ir_siguiente_pagina", fake_siguiente)

    licitaciones = codi.scan_completo(fake)
    ids = sorted(l["id"] for l in licitaciones)
    assert ids == ["a", "b", "c"]  # dedupe: 'c' una sola vez
