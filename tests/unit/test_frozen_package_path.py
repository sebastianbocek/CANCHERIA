from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


def test_desktop_configure_paths_exposes_external_cancheria_tree(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    import cancheria
    import cancheria_desktop

    external = str((root / "src" / "cancheria").resolve())
    # Simulate the frozen package having only an internal archive path.
    original = list(cancheria.__path__)
    try:
        cancheria.__path__[:] = [p for p in cancheria.__path__ if str(Path(p).resolve()) != external]
        cancheria_desktop.configure_paths(root)
        assert external in list(cancheria.__path__)
        assert os.environ["CANCHERIA_INSTALL_ROOT"] == str(root.resolve())
        sys.modules.pop("cancheria.legacy_bridge", None)
        module = importlib.import_module("cancheria.legacy_bridge")
        assert module.__file__ is not None
        assert str(root / "src" / "cancheria") in str(Path(module.__file__).resolve())
    finally:
        cancheria.__path__[:] = original


def test_paths_honors_explicit_install_root(monkeypatch, tmp_path):
    monkeypatch.setenv("CANCHERIA_INSTALL_ROOT", str(tmp_path))
    sys.modules.pop("cancheria.paths", None)
    paths = importlib.import_module("cancheria.paths")
    assert paths.PROJECT_ROOT == tmp_path.resolve()
    # Restore package module for following tests in the same interpreter.
    monkeypatch.delenv("CANCHERIA_INSTALL_ROOT", raising=False)
    sys.modules.pop("cancheria.paths", None)
    importlib.import_module("cancheria.paths")
