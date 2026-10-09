from __future__ import annotations

from pathlib import Path
import tkinter as tk

import pytest


ROOT = Path(__file__).resolve().parents[2]
GUI_PATH = ROOT / "src" / "cancheria" / "desktop" / "gui.py"


def test_desktop_visual_contract_is_local_and_keeps_callbacks() -> None:
    text = GUI_PATH.read_text(encoding="utf-8")

    for color in (
        "#F4F8FF",
        "#FFFFFF",
        "#1673FF",
        "#0B1930",
        "#DCE7F5",
        "#139B51",
        "#F59E0B",
        "#DC2626",
        "#B91C1C",
    ):
        assert color in text

    assert "class ModernButton(tk.Canvas)" in text
    assert 'self.profile_dir.name' in text
    assert 'assets" / "cancheria-logo-cropped.png"' in text
    assert 'ttk.Scrollbar(console' in text
    assert 'self.log.tag_configure("success"' in text
    assert 'self.log.tag_configure("warning"' in text
    assert 'self.log.tag_configure("error"' in text

    for callback in (
        "self.start_agent",
        "self.stop_agent",
        "self.toggle_ai_pause",
        "self.close_session",
        "self.new_session",
        "self.open_configurator",
        "self.open_admin_panel",
        "self.open_manual",
        "self.open_settings",
    ):
        assert callback in text


def test_desktop_logo_resource_exists() -> None:
    logo = ROOT / "assets" / "cancheria-logo-cropped.png"
    assert logo.is_file()
    assert logo.stat().st_size > 10_000


def test_desktop_widgets_resize_and_keep_real_actions() -> None:
    from cancheria.desktop.gui import CancheriaDesktop

    try:
        app = CancheriaDesktop()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")

    try:
        app.geometry("900x680+0+0")
        app.update_idletasks()
        app.update()

        assert app.btn_on._command.__name__ == "start_agent"
        assert app.btn_off._command.__name__ == "stop_agent"
        assert app.btn_ai_pause._command.__name__ == "toggle_ai_pause"
        assert app.btn_logout._command.__name__ == "close_session"
        assert app.btn_new._command.__name__ == "new_session"
        assert app.btn_config._command.__name__ == "open_configurator"
        assert app.btn_admin._command.__name__ == "open_admin_panel"
        assert app.btn_manual._command.__name__ == "open_manual"
        assert app.btn_settings._command.__name__ == "open_settings"

        for widget in (
            app.btn_on,
            app.btn_off,
            app.btn_ai_pause,
            app.btn_logout,
            app.btn_new,
            app.btn_config,
            app.btn_admin,
            app.btn_manual,
            app.btn_settings,
        ):
            assert widget.winfo_width() >= 140
            assert widget.winfo_height() >= 50

        app.btn_ai_pause.configure(text="REANUDAR IA")
        app.update_idletasks()
        assert app.btn_ai_pause._text == "REANUDAR IA"
        assert app.log.winfo_height() > 70
    finally:
        app.destroy()


def test_activity_console_adds_visual_timestamp_and_severity_without_losing_message() -> None:
    from cancheria.desktop.gui import CancheriaDesktop

    try:
        app = CancheriaDesktop()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")

    try:
        original = "✓ Operación completada correctamente."
        app._append_log(original)
        displayed = app.log.get("1.0", "end-1c")
        assert original in displayed
        assert displayed.count("[") >= 2
        success_ranges = app.log.tag_ranges("success")
        assert success_ranges
    finally:
        app.destroy()
