import os

def test_event_module_uses_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CANCHERIA_RUNTIME_DIR", str(tmp_path))
    import importlib
    from cancheria.domain.events import registration
    importlib.reload(registration)
    assert registration.BASE_DIR == tmp_path / "events"
