from pathlib import Path


def test_dynamic_runtime_support_anchors_sqlite_and_json():
    from cancheria.desktop.frozen_runtime_support import stdlib_self_test
    assert stdlib_self_test() == []


def test_main_launcher_imports_frozen_runtime_support():
    root = Path(__file__).resolve().parents[2]
    text = (root / "cancheria_desktop.py").read_text(encoding="utf-8")
    assert "frozen_runtime_support import stdlib_self_test" in text
    assert 'args[0] == "--self-test"' in text


def test_configurator_launcher_imports_frozen_runtime_support():
    root = Path(__file__).resolve().parents[2]
    text = (root / "configurador_cancheria.py").read_text(encoding="utf-8")
    assert "frozen_runtime_support import stdlib_self_test" in text
    assert 'sys.argv[1] == "--self-test"' in text


def test_build_explicitly_includes_dynamic_stdlib_modules():
    root = Path(__file__).resolve().parents[2]
    text = (root / "build_windows.bat").read_text(encoding="utf-8")
    for token in ("--hidden-import json", "--hidden-import sqlite3", "--hidden-import _sqlite3"):
        assert token in text
    assert 'cancheria.exe" --self-test' in text
    assert 'configurador_cancheria.exe" --self-test' in text
