from __future__ import annotations

import pytest

from cancheria.admin import desktop_service as service_module
from cancheria.admin.desktop_service import DesktopAdminService


def test_desktop_can_delete_used_payment_receipts_through_shared_admin_helper(monkeypatch):
    calls: list[str] = []

    def legacy(name: str):
        assert name == "borrar_used_payment_receipts_admin"

        def delete():
            calls.append(name)
            return {"ok": True, "respuesta": "Registro eliminado."}

        return delete

    monkeypatch.setattr(service_module, "legacy_callable", legacy)
    service = object.__new__(DesktopAdminService)

    assert service.delete_used_payment_receipts() == "Registro eliminado."
    assert calls == ["borrar_used_payment_receipts_admin"]


def test_desktop_reports_payment_receipt_delete_failure(monkeypatch):
    monkeypatch.setattr(
        service_module,
        "legacy_callable",
        lambda _name: lambda: {"ok": False, "respuesta": "Archivo bloqueado."},
    )
    service = object.__new__(DesktopAdminService)

    with pytest.raises(RuntimeError, match="Archivo bloqueado"):
        service.delete_used_payment_receipts()
