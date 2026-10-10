from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PANEL_PATH = ROOT / "src" / "cancheria" / "desktop" / "admin_panel.py"


def test_admin_panel_visual_contract_keeps_all_features_and_callbacks():
    source = PANEL_PATH.read_text(encoding="utf-8")

    for title in (
        "Reservas y pagos",
        "Horas",
        "Caja",
        "Operación",
        "Atención humana",
        "Torneos",
        "Turnos Fijos",
        "Blacklist",
        "Comandos y configuración",
    ):
        assert title in source

    for callback in (
        "self._new_booking_dialog",
        'self._booking_action("deposit")',
        'self._booking_action("total")',
        'self._booking_action("release")',
        'self._booking_action("cancel")',
        "self._resolve_case",
        "self._new_tournament_dialog",
        "self._new_fixed_turn_dialog",
        "self._blacklist_action",
    ):
        assert callback in source

    assert 'NAVY = "#142B50"' in source
    assert 'BLUE = "#1673FF"' in source
    assert 'BG = "#F5F7FB"' in source
    assert 'BORDER = "#E2E8F0"' in source
    assert 'style="Admin.Treeview"' in source
    assert "class AdminTabView" in source
    assert 'root / "assets" / "cancheria.ico"' in source
    assert "self.iconbitmap(str(icon_path))" in source
    assert "self.iconbitmap(default=str(icon_path))" in source
    assert "self.tournament_panes = tk.PanedWindow" in source
    assert 'widget.bind("<MouseWheel>", self._scroll_hours_vertical' in source
    assert 'widget.bind("<Shift-MouseWheel>", self._scroll_hours_horizontal' in source
    assert "class HoursDateField(tk.Canvas)" in source
    assert "class HoursPill(tk.Canvas)" in source
    assert "class HoursTile(tk.Canvas)" in source
    assert 'style="Hours.Vertical.TScrollbar"' in source
    assert "self.hours_summary_pill.set_text(summary)" in source
    assert "self.cash_page_size = 8" in source
    assert '("Fecha", "Concepto", "Cliente", "Método", "Importe", "Estado")' in source
    assert "self.cash_method_buttons" in source
    assert '("daily", "▥  Ingresos por día", 3)' in source
    assert '("methods", "◔  Distribución por método", 2)' in source
    assert '("courts", "▥  Por cancha", 2)' in source


def test_custom_tab_bar_selects_all_tabs_and_scrolls_when_narrow():
    import tkinter as tk

    from cancheria.desktop.admin_panel import AdminTabView

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk no está disponible en este entorno")
    root.geometry("620x420")
    view = AdminTabView(root)
    view.pack(fill="both", expand=True)
    titles = tuple(AdminTabView.TAB_ICONS)
    pages = []
    changes = []
    view.bind("<<NotebookTabChanged>>", lambda _event: changes.append(view.select()))
    try:
        for title in titles:
            page = tk.Frame(view, bg="white")
            pages.append(page)
            view.add(page, text=title)
        root.update_idletasks()
        root.update()

        assert len(view.tabs()) == 9
        assert [view.tab(tab_id, "text") for tab_id in view.tabs()] == list(titles)
        assert view._tabs_requested_width() > view._canvas.winfo_width()
        assert view._scrollbar.winfo_manager()

        for page in pages:
            view.select(page)
            root.update_idletasks()
            root.update()
            assert view.select() == str(page)
            assert view._records[page]["tab"].cget("bg") == view.ACTIVE_BG
            assert page.winfo_manager() == "pack"
            assert sum(bool(item.winfo_manager()) for item in pages) == 1

        assert changes
    finally:
        root.destroy()
