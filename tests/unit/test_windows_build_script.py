from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_windows_build_uses_root_exes_and_absolute_icon_variable():
    text = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    assert 'set "ICON=%ROOT%\\assets\\cancheria.ico"' in text
    assert '--icon "%ICON%"' in text
    assert '--distpath "."' in text
    assert 'cancheria.exe' in text
    assert 'configurador_cancheria.exe' in text


def test_windows_build_does_not_collect_every_openai_submodule():
    text = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    assert "--collect-all openai" not in text
    assert "--collect-all playwright" not in text
    assert "--hidden-import openai" in text
    assert "--hidden-import playwright.async_api" in text


def test_windows_build_uses_isolated_virtualenv():
    text = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    assert '.build-venv' in text
    assert 'py -m venv "%BUILD_VENV%"' in text
