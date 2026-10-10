import copy
import datetime as dt
from contextlib import contextmanager

import pytest

from cancheria.admin import desktop_service as service_module
from cancheria.admin.desktop_service import DesktopAdminService


class FakeCalendar:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)

    @contextmanager
    def atomic(self):
        yield

    def asegurar_ids_reservas(self):
        return copy.deepcopy(self.rows)

    def _leer_todos(self):
        return copy.deepcopy(self.rows)

    def _escribir_todos(self, rows, ordenar=True):
        self.rows = copy.deepcopy(rows)


def build_service(monkeypatch, rows, *, end_hour=16):
    monkeypatch.setattr(
        service_module.cfg,
        "COURTS",
        [{"name": "Cancha 1"}, {"name": "Cancha 2"}],
    )
    monkeypatch.setattr(service_module.cfg, "DEFAULT_COURT_NAME", "Cancha 1")
    monkeypatch.setattr(service_module.cfg, "CALL_SLOT_DURATION_MINUTES", 60)
    monkeypatch.setattr(
        service_module.cfg,
        "obtener_franjas_atencion_minutos",
        lambda: [(10 * 60, end_hour * 60)],
    )
    monkeypatch.setattr(
        service_module.cfg,
        "obtener_dias_atencion",
        lambda: list(range(7)),
    )
    service = object.__new__(DesktopAdminService)
    service.calendar = FakeCalendar(rows)
    return service


def future_day(days=1):
    return dt.date.today() + dt.timedelta(days=days)


def display_day(day):
    names = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
    return f"{names[day.weekday()]} {day.strftime('%d/%m')}"


def test_day_schedule_marks_free_occupied_and_blocked(monkeypatch):
    day = future_day()
    rows = [
        {
            "reservation_id": "7",
            "fecha": display_day(day),
            "hora": "11:00",
            "cancha": "Cancha 1",
            "estado": "reservado",
            "nombre": "Juan",
            "telefono": "123",
        },
        {
            "reservation_id": "8",
            "fecha": display_day(day),
            "hora": "12:00",
            "cancha": "Cancha 1",
            "estado": "reservado",
            "nombre": "CERRADO",
            "telefono": "ADMIN:CERRADO:test",
        },
    ]
    service = build_service(monkeypatch, rows, end_hour=13)

    schedule = service.day_schedule(day.isoformat())
    statuses = {
        (cell["time"], cell["court"]): cell["status"]
        for cell in schedule["cells"]
    }

    assert schedule["slots"] == ["10:00", "11:00", "12:00"]
    assert statuses[("10:00", "Cancha 1")] == "free"
    assert statuses[("11:00", "Cancha 1")] == "occupied"
    assert statuses[("12:00", "Cancha 1")] == "blocked"
    assert statuses[("11:00", "Cancha 2")] == "free"


def test_day_schedule_hides_every_elapsed_slot_for_today(monkeypatch):
    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2031, 5, 10, 14, 30)
            return value if tz is None else value.replace(tzinfo=tz)

    monkeypatch.setattr(service_module.dt, "datetime", FixedDateTime)
    service = build_service(monkeypatch, [], end_hour=17)

    schedule = service.day_schedule("2031-05-10")

    assert schedule["slots"] == ["15:00", "16:00"]
    assert {cell["status"] for cell in schedule["cells"]} == {"free"}


def test_court_catalog_and_sport_update_share_whatsapp_configuration(monkeypatch):
    monkeypatch.setattr(
        service_module.cfg,
        "COURTS",
        [
            {"name": "Cancha 1", "type": "Futbol 5"},
            {"name": "Cancha 2", "type": "Pádel"},
        ],
    )
    captured = {}

    def fake_legacy_callable(name):
        assert name == "actualizar_canchas_config"

        def update(courts):
            captured["courts"] = courts
            return {"ok": True, "respuesta": "ok"}

        return update

    monkeypatch.setattr(service_module, "legacy_callable", fake_legacy_callable)
    service = object.__new__(DesktopAdminService)

    assert service.court_catalog() == [
        {"name": "Cancha 1", "type": "Futbol 5", "icon": "⚽"},
        {"name": "Cancha 2", "type": "Pádel", "icon": "🎾"},
    ]
    result = service.update_court_sport("Cancha 1", "Básquet")

    assert captured["courts"][0] == {"name": "Cancha 1", "type": "Básquet"}
    assert captured["courts"][1] == {"name": "Cancha 2", "type": "Pádel"}
    assert result.startswith("🏀 Cancha 1")


def test_update_booking_moves_all_slots_and_preserves_other_fields(monkeypatch):
    day = future_day()
    rows = [
        {
            "reservation_id": "7",
            "fecha": display_day(day),
            "hora": "10:00",
            "cancha": "Cancha 1",
            "estado": "reservado",
            "nombre": "Juan",
            "telefono": "123",
            "senia_estado": "pagada",
        },
        {
            "reservation_id": "7",
            "fecha": display_day(day),
            "hora": "11:00",
            "cancha": "Cancha 1",
            "estado": "reservado",
            "nombre": "Juan",
            "telefono": "123",
            "senia_estado": "pagada",
        },
    ]
    service = build_service(monkeypatch, rows)

    result = service.update_booking(
        "7",
        day=day.isoformat(),
        time="12:00",
        court="Cancha 2",
        name="Juan Pérez",
        phone="456",
    )

    moved = sorted(service.calendar.rows, key=lambda row: row["hora"])
    assert [row["hora"] for row in moved] == ["12:00", "13:00"]
    assert {row["cancha"] for row in moved} == {"Cancha 2"}
    assert {row["nombre"] for row in moved} == {"Juan Pérez"}
    assert {row["telefono"] for row in moved} == {"456"}
    assert {row["senia_estado"] for row in moved} == {"pagada"}
    assert "Reserva ID 7 actualizada" in result


def test_update_booking_rejects_collision(monkeypatch):
    day = future_day()
    rows = [
        {
            "reservation_id": "7",
            "fecha": display_day(day),
            "hora": "10:00",
            "cancha": "Cancha 1",
            "estado": "reservado",
            "nombre": "Juan",
            "telefono": "123",
        },
        {
            "reservation_id": "9",
            "fecha": display_day(day),
            "hora": "12:00",
            "cancha": "Cancha 1",
            "estado": "reservado",
            "nombre": "Ana",
            "telefono": "999",
        },
    ]
    service = build_service(monkeypatch, rows)

    with pytest.raises(ValueError, match="ocupado"):
        service.update_booking(
            "7",
            day=day.isoformat(),
            time="12:00",
            court="Cancha 1",
            name="Juan",
            phone="123",
        )


def test_unblock_slot_removes_only_selected_block(monkeypatch):
    day = future_day()
    rows = [
        {
            "reservation_id": "1",
            "fecha": display_day(day),
            "hora": "10:00",
            "cancha": "Cancha 1",
            "estado": "reservado",
            "nombre": "CERRADO",
            "telefono": "ADMIN:CERRADO:test",
        },
        {
            "reservation_id": "2",
            "fecha": display_day(day),
            "hora": "11:00",
            "cancha": "Cancha 1",
            "estado": "reservado",
            "nombre": "CERRADO",
            "telefono": "ADMIN:CERRADO:test",
        },
    ]
    service = build_service(monkeypatch, rows)

    service.unblock_slot(day.isoformat(), "10:00", "Cancha 1")

    assert len(service.calendar.rows) == 1
    assert service.calendar.rows[0]["hora"] == "11:00"


def test_notification_counts_sum_only_unresolved_admin_work():
    service = object.__new__(DesktopAdminService)

    counts = service.notification_counts({"active": 8, "pending": 3, "today": 4, "cases": 2})

    assert counts == {
        "bookings": 3,
        "hours": 0,
        "cash": 0,
        "operation": 0,
        "cases": 2,
        "tournaments": 0,
        "fixed_turns": 0,
        "blacklist": 0,
        "commands": 0,
        "total": 5,
    }


def test_admin_notifications_stay_read_until_a_new_item_arrives(tmp_path, monkeypatch):
    service = object.__new__(DesktopAdminService)
    service.runtime = tmp_path / "runtime"
    service._notification_read_store = None
    rows = [
        {
            "reservation_id": "R-1",
            "estado": "reservado",
            "senia_estado": "pendiente",
        }
    ]
    cases = [{"case_id": "C-1", "status": "pending"}]
    monkeypatch.setattr(service, "bookings", lambda: list(rows))
    monkeypatch.setattr(service, "human_cases", lambda: list(cases))
    monkeypatch.setattr(
        "cancheria.admin.desktop_service.event_registration.list_business_events",
        lambda active_only=False: [],
    )

    assert service.unread_notification_counts()["total"] == 2
    assert service.mark_notifications_read()["total"] == 0
    assert service.unread_notification_counts()["total"] == 0

    rows.append({
        "reservation_id": "R-2",
        "estado": "reservado",
        "senia_estado": "parcial",
    })
    counts = service.unread_notification_counts()
    assert counts["bookings"] == 1
    assert counts["cases"] == 0
    assert counts["total"] == 1


def test_admin_can_mark_only_the_clicked_notification_section(tmp_path, monkeypatch):
    service = object.__new__(DesktopAdminService)
    service.runtime = tmp_path / "runtime"
    service._notification_read_store = None
    monkeypatch.setattr(service, "bookings", lambda: [{
        "reservation_id": "R-1",
        "estado": "reservado",
        "senia_estado": "pendiente",
    }])
    monkeypatch.setattr(
        service,
        "human_cases",
        lambda: [{"case_id": "C-1", "status": "pending"}],
    )
    monkeypatch.setattr(
        "cancheria.admin.desktop_service.event_registration.list_business_events",
        lambda active_only=False: [],
    )

    counts = service.mark_notifications_read(["bookings"])
    assert counts["bookings"] == 0
    assert counts["cases"] == 1
    assert counts["total"] == 1


def test_stats_counts_multislot_pending_booking_as_one_notification(monkeypatch):
    rows = [
        {
            "reservation_id": "12",
            "fecha": display_day(future_day()),
            "hora": hour,
            "cancha": "Cancha 1",
            "estado": "reservado",
            "senia_estado": "pendiente",
        }
        for hour in ("20:00", "21:00")
    ]
    service = build_service(monkeypatch, rows)
    monkeypatch.setattr(service, "human_cases", lambda: [])

    assert service.stats()["pending"] == 1
    assert service.notification_counts()["total"] == 1


def test_admin_panel_exposes_hours_tab_and_click_editing():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cancheria"
        / "desktop"
        / "admin_panel.py"
    ).read_text(encoding="utf-8")
    assert 'text="Horas"' in source
    assert 'text="Caja"' in source
    assert "def _refresh_cash" in source
    assert "def _refresh_hours" in source
    assert "def _open_hour_cell" in source
    assert "def _edit_booking_dialog" in source
    assert 'text="Fecha 📅"' in source
    assert '"<Button-3>"' in source
    assert "def _show_court_sport_menu" in source
    assert "def _change_court_sport" in source
    assert '"No quedan horarios futuros para esta fecha."' in source


def test_admin_operation_date_reuses_visual_calendar_picker():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cancheria"
        / "desktop"
        / "admin_panel.py"
    ).read_text(encoding="utf-8")

    operation = source.split("def _build_operation(self) -> None:", 1)[1].split(
        "def _build_cases(self) -> None:", 1
    )[0]
    assert 'text="Fecha 📅"' in operation
    assert "self.block_day_entry" in operation
    assert '"Fecha del bloqueo de agenda"' in operation
    assert 'block_date_label.bind("<Button-1>", open_block_calendar)' in operation
    assert 'self.block_day_entry.bind("<Double-Button-1>", open_block_calendar)' in operation
    assert "command=open_block_calendar" in operation


def test_admin_hours_tab_builds_with_colored_slot_buttons():
    import tkinter as tk

    from cancheria.desktop.admin_panel import AdminPanel, HoursTile

    class UiService:
        def courts(self):
            return ["Cancha 1", "Cancha 2"]

        def stats(self):
            return {"active": 1, "pending": 0, "today": 1, "cases": 0}

        def bookings(self):
            return []

        def human_cases(self):
            return []

        def day_schedule(self, day):
            return {
                "day": day,
                "display_day": "07/10/2026",
                "attention_day": True,
                "courts": self.courts(),
                "slots": ["18:00", "19:00"],
                "cells": [
                    {"day": day, "time": "18:00", "court": "Cancha 1", "status": "free", "booking": None},
                    {"day": day, "time": "18:00", "court": "Cancha 2", "status": "occupied", "booking": {"nombre": "Juan"}},
                    {"day": day, "time": "19:00", "court": "Cancha 1", "status": "blocked", "booking": {"nombre": "CERRADO"}},
                    {"day": day, "time": "19:00", "court": "Cancha 2", "status": "free", "booking": None},
                ],
            }

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk no está disponible en este entorno")
    root.withdraw()
    panel = None
    try:
        panel = AdminPanel(root, UiService(), lambda: None)
        panel.withdraw()
        panel.notebook.select(panel.hours_tab)
        panel.update_idletasks()
        tab_labels = [panel.notebook.tab(tab_id, "text") for tab_id in panel.notebook.tabs()]
        buttons = [
            widget
            for widget in panel.hours_grid.winfo_children()
            if isinstance(widget, HoursTile) and callable(widget.command)
        ]
        assert "Horas" in tab_labels
        assert len(buttons) == 4
        assert {button.fill for button in buttons} == {panel.FREE_GREEN, panel.RED}
        assert "2 horarios · 2 canchas" in panel.hours_status_var.get()
    finally:
        if panel is not None:
            panel.destroy()
        root.destroy()


def test_admin_panel_shows_red_badge_and_opens_only_notified_tab():
    import tkinter as tk

    from cancheria.desktop.admin_panel import AdminPanel

    class UiService:
        def courts(self):
            return ["Cancha 1"]

        def stats(self):
            return {"active": 0, "pending": 0, "today": 0, "cases": 2}

        def notification_counts(self, stats=None):
            return {
                "bookings": 0,
                "hours": 0,
                "operation": 0,
                "cases": 2,
                "commands": 0,
                "total": 2,
            }

        def bookings(self):
            return []

        def human_cases(self):
            return [
                {"case_id": 1, "created_at": "2026-10-08", "nombre": "Juan"},
                {"case_id": 2, "created_at": "2026-10-08", "nombre": "Ana"},
            ]

        def day_schedule(self, day):
            return {
                "day": day,
                "display_day": "08/10/2026",
                "attention_day": True,
                "courts": self.courts(),
                "slots": [],
                "cells": [],
            }

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk no está disponible en este entorno")
    root.withdraw()
    panel = None
    changes = []
    try:
        panel = AdminPanel(root, UiService(), lambda: None, changes.append)
        panel.update_idletasks()

        assert panel.notebook.select() == str(panel.cases_tab)
        assert panel.notebook.tab(panel.cases_tab, "image")
        assert not panel.notebook.tab(panel.bookings_tab, "image")
        assert changes[-1]["total"] == 2
        assert changes[-1]["cases"] == 2
    finally:
        if panel is not None:
            panel.destroy()
        root.destroy()
