from __future__ import annotations

from pathlib import Path

import pytest

from cancheria.admin import desktop_service as service_module
from cancheria.admin.desktop_service import DesktopAdminService


def test_desktop_blacklist_reuses_whatsapp_admin_operations(monkeypatch):
    entries = ["phone:+5493511111111", "name:juan perez"]
    calls: list[tuple[str, str]] = []

    def entry_from_target(target: str) -> str:
        target = str(target).strip()
        if target.startswith(("phone:", "name:")):
            return target
        if target.startswith("+"):
            return f"phone:{target}"
        return f"name:{target.lower()}"

    def label(entry: str) -> str:
        if entry.startswith("phone:"):
            return entry.removeprefix("phone:")
        return "NOMBRE:" + entry.removeprefix("name:").title()

    def legacy(name: str):
        if name == "cargar_blacklist":
            return lambda: list(entries)
        if name == "_blacklist_label":
            return label
        if name == "_blacklist_entry_from_target":
            return entry_from_target
        if name == "bloquear_numero":
            return lambda target: calls.append((name, target)) is None
        if name == "desbloquear_numero":
            return lambda target: calls.append((name, target)) is None
        raise AssertionError(f"Función legacy inesperada: {name}")

    monkeypatch.setattr(service_module, "legacy_callable", legacy)
    service = object.__new__(DesktopAdminService)

    assert service.blacklist_entries() == [
        {"entry": "phone:+5493511111111", "kind": "Teléfono", "label": "+5493511111111"},
        {"entry": "name:juan perez", "kind": "Nombre", "label": "NOMBRE:Juan Perez"},
    ]
    assert "+5493512222222" in service.block_blacklist("+5493512222222")
    assert "NOMBRE:Juan Perez" in service.unblock_blacklist("name:juan perez")
    assert calls == [
        ("bloquear_numero", "+5493512222222"),
        ("desbloquear_numero", "name:juan perez"),
    ]


def test_desktop_blacklist_rejects_invalid_or_authorized_target(monkeypatch):
    def legacy(name: str):
        if name == "bloquear_numero":
            return lambda _target: False
        raise AssertionError(f"Función legacy inesperada: {name}")

    monkeypatch.setattr(service_module, "legacy_callable", legacy)
    service = object.__new__(DesktopAdminService)

    with pytest.raises(ValueError, match="administrador autorizado"):
        service.block_blacklist("+5493510000000")
    with pytest.raises(ValueError, match="Ingresá"):
        service.block_blacklist("")


def test_admin_gui_places_blacklist_before_commands_with_full_management():
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cancheria"
        / "desktop"
        / "admin_panel.py"
    ).read_text(encoding="utf-8")

    blacklist_tab = 'self.notebook.add(self.blacklist_tab, text="Blacklist")'
    commands_tab = 'self.notebook.add(self.commands_tab, text="Comandos y configuración")'
    assert blacklist_tab in source
    assert source.index(blacklist_tab) < source.index(commands_tab)
    assert "def _build_blacklist" in source
    assert '"Bloquear"' in source
    assert '"Desbloquear"' in source
    assert '"Actualizar"' in source
    assert "def _refresh_blacklist" in source
    assert "self.service, method_name" in source
