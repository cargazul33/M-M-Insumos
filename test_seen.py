from radar.store import seen


def test_dedupe(tmp_path, monkeypatch):
    monkeypatch.setattr(seen, "_SEEN_FILE", tmp_path / "seen.json")
    ops = [{"texto": "lic A", "visualizar_url": "u1"},
           {"texto": "lic B", "visualizar_url": "u2"}]
    primera = seen.filtrar_nuevas(ops)
    assert len(primera) == 2
    segunda = seen.filtrar_nuevas(ops)  # mismas -> nada nuevo
    assert len(segunda) == 0
