from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

from cancheria.admin.desktop_service import DesktopAdminService
from cancheria.domain.reservations import calendar as calendar_module
from cancheria.domain.reservations.calendar import CalendarioLlamadas


LOCAL_TZ = ZoneInfo("America/Argentina/Cordoba")


def build_calendar(tmp_path: Path, monkeypatch) -> CalendarioLlamadas:
    finished = tmp_path / "turnos_terminados.csv"
    monkeypatch.setattr(calendar_module, "CALENDARIO_TERMINADAS_CSV", str(finished))
    return CalendarioLlamadas(str(tmp_path / "calendario_turnos.csv"))


def booking(**overrides):
    row = {
        "reservation_id": "7",
        "fecha": "Viernes 09/10/2026",
        "hora": "21:00",
        "cancha": "Cancha 1",
        "estado": "reservado",
        "nombre": "Juan",
        "telefono": "+5493510000000",
        "duracion_horas": "1",
        "duracion_minutos": "60",
        "senia_estado": "pagada",
        "senia_pagada_monto": "20000",
        "precio_total": "20000",
        "monto_pendiente": "0",
    }
    row.update(overrides)
    return row


def write_rows(calendar: CalendarioLlamadas, rows: list[dict]) -> None:
    with calendar.atomic():
        calendar._escribir_todos(rows, ordenar=True)


def test_expired_booking_is_finalized_and_payment_history_is_preserved(tmp_path, monkeypatch):
    calendar = build_calendar(tmp_path, monkeypatch)
    write_rows(calendar, [booking()])

    moved = calendar.finalizar_turnos_vencidos(
        dt.datetime(2026, 10, 10, 9, 0, tzinfo=LOCAL_TZ)
    )

    assert moved == 1
    assert calendar._leer_todos() == []
    finished = calendar._leer_terminadas()
    assert len(finished) == 1
    assert finished[0]["estado"] == "finalizada"
    assert finished[0]["senia_pagada_monto"] == "20000"
    assert finished[0]["monto_pendiente"] == "0"


def test_booking_remains_active_until_its_full_duration_ends(tmp_path, monkeypatch):
    calendar = build_calendar(tmp_path, monkeypatch)
    write_rows(calendar, [booking(fecha="Sábado 10/10/2026", duracion_horas="2")])

    assert calendar.finalizar_turnos_vencidos(
        dt.datetime(2026, 10, 10, 22, 0, tzinfo=LOCAL_TZ)
    ) == 0
    assert len(calendar._leer_todos()) == 1

    assert calendar.finalizar_turnos_vencidos(
        dt.datetime(2026, 10, 10, 23, 0, tzinfo=LOCAL_TZ)
    ) == 1
    assert calendar._leer_terminadas()[0]["estado"] == "finalizada"


def test_terminal_status_is_preserved_when_archived(tmp_path, monkeypatch):
    calendar = build_calendar(tmp_path, monkeypatch)
    write_rows(calendar, [booking(estado="cancelado")])

    calendar.finalizar_turnos_vencidos(
        dt.datetime(2026, 10, 10, 9, 0, tzinfo=LOCAL_TZ)
    )

    assert calendar._leer_terminadas()[0]["estado"] == "cancelado"


def test_dashboard_defensively_excludes_expired_rows_and_counts_logical_bookings(
    tmp_path, monkeypatch
):
    calendar = build_calendar(tmp_path, monkeypatch)
    write_rows(calendar, [booking()])
    monkeypatch.setattr(
        calendar,
        "finalizar_turnos_vencidos",
        lambda: (_ for _ in ()).throw(OSError("archivo ocupado")),
    )
    monkeypatch.setattr(
        calendar,
        "logical_reservation_has_ended",
        lambda _rows: True,
    )

    service = object.__new__(DesktopAdminService)
    service.calendar = calendar
    monkeypatch.setattr(service, "human_cases", lambda: [])
    monkeypatch.setattr(service, "pending_tournament_registrations", lambda: 0)

    assert service.stats()["active"] == 0
    assert service.stats()["today"] == 0


def test_dashboard_counts_a_multi_slot_booking_only_once(tmp_path, monkeypatch):
    calendar = build_calendar(tmp_path, monkeypatch)
    rows = [
        booking(fecha="Domingo 11/10/2026", hora="20:00", cancha="Cancha 1"),
        booking(fecha="Domingo 11/10/2026", hora="21:00", cancha="Cancha 1"),
    ]
    write_rows(calendar, rows)
    monkeypatch.setattr(
        calendar,
        "local_now",
        lambda: dt.datetime(2026, 10, 10, 9, 0, tzinfo=LOCAL_TZ),
    )

    service = object.__new__(DesktopAdminService)
    service.calendar = calendar
    monkeypatch.setattr(service, "human_cases", lambda: [])
    monkeypatch.setattr(service, "pending_tournament_registrations", lambda: 0)

    assert service.stats()["active"] == 1


def test_multi_slot_booking_finishes_after_the_last_slot(tmp_path, monkeypatch):
    calendar = build_calendar(tmp_path, monkeypatch)
    rows = [
        booking(fecha="Sábado 10/10/2026", hora="20:00", duracion_horas="2"),
        booking(fecha="Sábado 10/10/2026", hora="21:00", duracion_horas="2"),
    ]
    write_rows(calendar, rows)

    assert calendar.finalizar_turnos_vencidos(
        dt.datetime(2026, 10, 10, 21, 59, tzinfo=LOCAL_TZ)
    ) == 0
    assert calendar.finalizar_turnos_vencidos(
        dt.datetime(2026, 10, 10, 22, 0, tzinfo=LOCAL_TZ)
    ) == 2
    assert {row["estado"] for row in calendar._leer_terminadas()} == {"finalizada"}


def test_date_without_year_uses_nearest_calendar_year(tmp_path, monkeypatch):
    calendar = build_calendar(tmp_path, monkeypatch)
    write_rows(calendar, [booking(fecha="Miércoles 31/12", hora="23:00")])

    assert calendar.finalizar_turnos_vencidos(
        dt.datetime(2027, 1, 1, 0, 0, tzinfo=LOCAL_TZ)
    ) == 1

    write_rows(calendar, [booking(fecha="Viernes 01/01", hora="21:00")])
    assert calendar.finalizar_turnos_vencidos(
        dt.datetime(2026, 12, 31, 12, 0, tzinfo=LOCAL_TZ)
    ) == 0


def test_total_payment_has_distinct_display_without_finishing_booking():
    service = object.__new__(DesktopAdminService)
    row = booking(fecha="Domingo 11/10/2026")

    assert service.booking_payment_status(row) == "total pagado"
    assert row["estado"] == "reservado"
    assert service.booking_payment_status({**row, "monto_pendiente": "10000"}) == "pagada"


