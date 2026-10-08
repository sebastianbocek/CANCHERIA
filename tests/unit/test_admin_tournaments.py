from __future__ import annotations

from pathlib import Path

import pytest

from cancheria.admin import desktop_service as service_module
from cancheria.admin.desktop_service import DesktopAdminService
from cancheria.domain.events import registration


def isolate_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "events"
    monkeypatch.setattr(registration, "BASE_DIR", base)
    monkeypatch.setattr(registration, "BUSINESS_EVENTS_FILE", base / "business_events.json")
    monkeypatch.setattr(registration, "BUSINESS_EVENTS_DIR", base / "torneos")


def test_registration_admin_id_survives_payment_and_contact_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolate_events(monkeypatch, tmp_path)
    event = registration.configure_business_event(
        "Copa GUI", 10000, 8, "2030-10-20", prize=100000
    )["event"]
    row = registration.create_event_registration_hold(
        event, "Los Test", "Sebastián", "+5493511111111"
    )["registration"]
    rows = registration.read_event_registrations(event)
    rows[0]["admin_id"] = "10001"
    registration.write_event_registrations_atomic(event, rows)

    paid = registration.register_event_payment(
        event, row["registration_id"], 5000, payment_method="cash"
    )["registration"]
    assert paid["admin_id"] == "10001"

    edited = registration.update_event_registration_contact(
        event,
        row["registration_id"],
        team_name="Los Test Editados",
        contact_name="Seba",
        phone="+5493522222222",
    )["registration"]
    assert edited["admin_id"] == "10001"
    assert edited["team_name"] == "Los Test Editados"
    assert edited["phone"] == "+5493522222222"
    assert edited["paid_amount"] == "5000"


def test_desktop_tournament_service_reuses_admin_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolate_events(monkeypatch, tmp_path)
    calls: list[tuple[str, dict]] = []

    def legacy(name: str):
        if name == "_event_registration_admin_public_id":
            return lambda _registration_id, create=True: "10001"
        if name == "build_mensaje_ayuda_admin":
            return lambda category="todos": "TODOS LOS COMANDOS\nayuda torneos"

        def operation(payload: dict):
            calls.append((name, dict(payload)))
            return {"ok": True, "respuesta": f"{name}: ok"}

        return operation

    monkeypatch.setattr(service_module, "legacy_callable", legacy)
    (tmp_path / "runtime").mkdir()
    service = DesktopAdminService(tmp_path)
    service.create_tournament(
        name="Copa Escritorio",
        date="2031-05-10",
        price="20000",
        prize="200000",
        capacity="12",
        payment_alias="COPA.GUI",
    )
    event = service.tournaments()[0]
    assert event["name"] == "Copa Escritorio"
    assert event["available"] == 12

    service.create_tournament_registration(
        event["event_id"],
        team_name="Equipo Uno",
        contact_name="Juan",
        phone="+5493510000001",
    )
    rows = service.tournament_registrations(event["event_id"])
    assert rows[0]["display_id"] == "10001"
    assert service.pending_tournament_registrations() == 1

    service.update_tournament_registration(
        event["event_id"],
        rows[0]["registration_id"],
        team_name="Equipo Uno Editado",
        contact_name="Juan Pérez",
        phone="+5493510000002",
    )
    refreshed = service.tournament_registrations(event["event_id"])[0]
    assert refreshed["team_name"] == "Equipo Uno Editado"

    service.update_tournament(
        event["event_id"],
        name="Copa Nueva",
        date="2031-05-11",
        price="25000",
        prize="250000",
        capacity="14",
    )
    service.confirm_tournament_registration(rows[0]["registration_id"], total=True)
    service.cancel_tournament_registration(rows[0]["registration_id"])
    service.delete_tournament(event["event_id"])

    assert [name for name, _payload in calls] == [
        "editar_torneo_admin",
        "confirmar_pago_inscripcion_evento_admin",
        "liberar_inscripcion_evento_admin",
        "borrar_torneo_admin",
    ]
    assert calls[1][1]["pago_total"] is True
    assert "ayuda torneos" in service.command_reference()


def test_admin_gui_exposes_tournaments_and_full_whatsapp_help() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cancheria"
        / "desktop"
        / "admin_panel.py"
    ).read_text(encoding="utf-8")

    assert 'self.notebook.add(self.tournaments_tab, text="Torneos")' in source
    assert source.index('text="Atención humana"') < source.index('text="Torneos"')
    assert '"Nuevo torneo"' in source
    assert '"Editar torneo"' in source
    assert '"Borrar torneo"' in source
    assert '"Nueva inscripción"' in source
    assert '"Editar datos"' in source
    assert '"Confirmar seña"' in source
    assert '"Confirmar total"' in source
    assert '"Liberar / cancelar"' in source
    assert 'getattr(self.service, "command_reference", None)' in source
    assert 'text.tag_configure("command"' in source
