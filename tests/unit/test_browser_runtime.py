from pathlib import Path

import pytest

from cancheria import browser_runtime


def test_windows_keeps_the_installed_chrome_channel(monkeypatch):
    monkeypatch.delenv(browser_runtime.BROWSER_EXECUTABLE_ENV, raising=False)

    options = browser_runtime.persistent_context_options("profile", platform="win32")

    assert options["channel"] == "chrome"
    assert "executable_path" not in options
    assert "--disable-dev-shm-usage" not in options["args"]


def test_linux_uses_installed_chromium(monkeypatch):
    monkeypatch.delenv(browser_runtime.BROWSER_EXECUTABLE_ENV, raising=False)
    monkeypatch.setattr(
        browser_runtime.shutil,
        "which",
        lambda command: "/usr/bin/chromium" if command == "chromium" else None,
    )

    options = browser_runtime.persistent_context_options("profile", platform="linux")

    assert options["executable_path"] == "/usr/bin/chromium"
    assert "channel" not in options
    assert "--disable-dev-shm-usage" in options["args"]


def test_explicit_browser_override_has_priority(monkeypatch, tmp_path: Path):
    browser = tmp_path / "my-browser"
    browser.write_text("browser", encoding="utf-8")
    monkeypatch.setenv(browser_runtime.BROWSER_EXECUTABLE_ENV, str(browser))

    assert browser_runtime.discover_browser_executable(platform="linux") == str(
        browser.resolve()
    )


def test_invalid_browser_override_is_reported(monkeypatch):
    monkeypatch.setenv(
        browser_runtime.BROWSER_EXECUTABLE_ENV,
        "/definitely/missing/cancheria-browser",
    )

    with pytest.raises(FileNotFoundError, match="navegador inexistente"):
        browser_runtime.discover_browser_executable(platform="linux")
