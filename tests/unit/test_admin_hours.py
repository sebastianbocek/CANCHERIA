import copy
import datetime as dt
from contextlib import contextmanager

import pytest

from cancheria.admin import desktop_service as service_module
from cancheria.admin.desktop_service import DesktopAdminService


class FakeCalendar:
    def __init__(self, rows, finished=None):
        self.rows = copy.deepcopy(rows)
        self.finished = copy.deepcopy(finished or [])

    @contextmanager
    def atomic(self):
        yield

    def asegurar_ids_reservas(self):
        return copy.deepcopy(self.rows)

    def _leer_todos(self):
        return copy.deepcopy(self.rows)

    def _leer_terminadas(self):
        return copy.deepcopy(self.finished)

    def _escribir_todos(self, rows, ordenar=True):
        self.rows = copy.deepcopy(rows)

    def _escribir_terminadas(self, rows):
        self.finished = copy.deepcopy(rows)


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


def test_day_schedule_hot_reloads_attention_window_saved_by_configurator(monkeypatch, tmp_path):
    from cancheria.domain.reservations import calendar as calendar_module

    monkeypatch.setattr(service_module.cfg, "COURTS", [{"name": "Cancha 1"}])
    monkeypatch.setattr(service_module.cfg, "CALL_TIME_WINDOWS", [("10:00", "00:00")])
    monkeypatch.setattr(
        calendar_module, "CALL_TIME_WINDOWS", [("10:00", "00:00")], raising=False
    )
    config_path = tmp_path / "legacy_config.py"
    config_path.write_text(
        "CALL_TIME_WINDOWS = [('05:00', '00:00')]\n",
        encoding="utf-8",
    )
    service = object.__new__(DesktopAdminService)
    service.calendar = calendar_module.CalendarioLlamadas(str(tmp_path / "calendar.csv"))
    service._config_path = config_path
    service._config_signature = None

    schedule = service.day_schedule(future_day().isoformat())

    assert schedule["slots"][0] == "05:00"
    assert schedule["slots"][-1] == "23:00"
    assert service_module.cfg.CALL_TIME_WINDOWS == [("05:00", "00:00")]
    assert calendar_module.CALL_TIME_WINDOWS == [("05:00", "00:00")]


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


def test_day_schedule_keeps_a_started_booking_visible_as_in_progress(monkeypatch):
    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2031, 5, 10, 14, 30)
            return value if tz is None else value.replace(tzinfo=tz)

    monkeypatch.setattr(service_module.dt, "datetime", FixedDateTime)
    service = build_service(monkeypatch, [{
        "reservation_id": "LIVE-1",
        "fecha": "Sábado 10/05/2031",
        "hora": "14:00",
        "cancha": "Cancha 1",
        "estado": "reservado",
        "nombre": "Equipo Azul",
        "telefono": "+5493511111111",
        "duracion_horas": "1",
    }], end_hour=17)

    schedule = service.day_schedule("2031-05-10")
    live = next(
        cell for cell in schedule["cells"]
        if cell["time"] == "14:00" and cell["court"] == "Cancha 1"
    )

    assert schedule["slots"] == ["14:00", "15:00", "16:00"]
    assert live["status"] == "in_progress"
    assert live["starts_at"] == "2031-05-10T14:00:00"
    assert live["ends_at"] == "2031-05-10T15:00:00"


def test_day_schedule_keeps_recently_finished_archived_booking_for_third_time(monkeypatch):
    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2031, 5, 10, 14, 30)
            return value if tz is None else value.replace(tzinfo=tz)

    monkeypatch.setattr(service_module.dt, "datetime", FixedDateTime)
    monkeypatch.setattr(service_module.cfg, "POST_GAME_PROMOTION_MINUTES", 60)
    service = build_service(monkeypatch, [], end_hour=17)
    service.calendar.finished = [{
        "reservation_id": "RECENT-1",
        "fecha": "Sábado 10/05/2031",
        "hora": "13:00",
        "cancha": "Cancha 1",
        "estado": "finalizada",
        "nombre": "Equipo Celeste",
        "telefono": "+5493512222222",
        "duracion_horas": "1",
    }]

    schedule = service.day_schedule("2031-05-10")
    recent = next(
        cell for cell in schedule["cells"]
        if cell["time"] == "13:00" and cell["court"] == "Cancha 1"
    )

    assert schedule["slots"] == ["13:00", "15:00", "16:00"]
    assert recent["status"] == "recently_finished"


def test_day_schedule_show_all_includes_elapsed_and_archived_occupied_slots(monkeypatch):
    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2031, 5, 10, 14, 30)
            return value if tz is None else value.replace(tzinfo=tz)

    monkeypatch.setattr(service_module.dt, "datetime", FixedDateTime)
    service = build_service(monkeypatch, [], end_hour=17)
    service.calendar.finished = [{
        "reservation_id": "OLD-1",
        "fecha": "Sábado 10/05/2031",
        "hora": "13:00",
        "cancha": "Cancha 1",
        "estado": "finalizada",
        "nombre": "Reserva anterior",
        "telefono": "123",
    }]

    schedule = service.day_schedule("2031-05-10", include_all=True)
    statuses = {
        (cell["time"], cell["court"]): cell["status"]
        for cell in schedule["cells"]
    }

    assert schedule["slots"] == ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]
    assert statuses[("13:00", "Cancha 1")] == "recently_finished"
    assert statuses[("12:00", "Cancha 1")] == "closed"
    assert statuses[("15:00", "Cancha 1")] == "free"


def test_promotion_link_uses_persisted_whatsapp_link_and_encodes_message(monkeypatch, tmp_path):
    contacts = tmp_path / "reservas_contactos.csv"
    contacts.write_text(
        "telefono,whatsapp_link\n+5493513333333,https://wa.me/5493513333333\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(service_module.cfg, "CONTACTS_CSV", str(contacts))
    monkeypatch.setattr(service_module.cfg, "BUSINESS_NAME", "Club Prueba")
    service = build_service(monkeypatch, [])
    service.root = tmp_path
    service.runtime = tmp_path

    template = service.promotion_message_template()
    link = service.promotion_whatsapp_link(
        {"telefono": "+54 9 351 333-3333"},
        template.replace("{}", "2x1 en bebidas"),
    )

    assert "Club+Prueba" in link
    assert "2x1+en+bebidas" in link
    assert link.startswith("https://wa.me/5493513333333?text=")


def test_customer_message_is_queued_for_active_whatsapp_worker(monkeypatch, tmp_path):
    service = build_service(monkeypatch, [])
    service.root = tmp_path
    service.runtime = tmp_path / "runtime"
    service.runtime.mkdir()
    delivery_id = service.queue_customer_whatsapp_message(
        {
            "reservation_id": "PROMO-1",
            "telefono": "+54 9 351 333-3333",
        },
        "2x1 en bebidas",
    )

    queued = service_module.JSONStore(
        service.runtime / "admin_outbox_requests" / f"{delivery_id}.json"
    ).read({})
    assert delivery_id.startswith("customer_message_")
    assert queued["category"] == "operator_customer_message"
    assert queued["recipient"] == "+5493513333333"
    assert queued["text"] == "2x1 en bebidas"
    assert queued["context"]["reservation_id"] == "PROMO-1"
    assert not (service.runtime / "proactive_state.json").exists()


def test_school_promotion_queues_one_message_per_unique_guardian(monkeypatch, tmp_path):
    service = build_service(monkeypatch, [])
    service.root = tmp_path
    service.runtime = tmp_path / "runtime"
    service.runtime.mkdir()
    delivery_ids = service.queue_customer_whatsapp_message(
        {
            "reservation_id": "school:G-1:2031-05-10",
            "school_group_id": "G-1",
            "recipient_phones": [
                "+54 9 351 111-2222", "+5493511112222", "+54 9 351 333-4444"
            ],
        },
        "2x1 en bebidas",
    ).split(",")

    assert len(delivery_ids) == 2
    queued = [
        service_module.JSONStore(
            service.runtime / "admin_outbox_requests" / f"{delivery_id}.json"
        ).read({})
        for delivery_id in delivery_ids
    ]
    assert {row["recipient"] for row in queued} == {
        "+5493511112222", "+5493513334444"
    }
    assert all(row["context"]["school_group_id"] == "G-1" for row in queued)
    assert service.promotion_recipient_count({
        "recipient_phones": ["+5493511112222", "+5493511112222", "+5493513334444"]
    }) == 2


def test_school_hours_cell_uses_real_guardian_recipients(monkeypatch, tmp_path):
    monkeypatch.setattr(service_module.cfg, "COURTS", [{"name": "Cancha 1"}])
    monkeypatch.setattr(service_module.cfg, "DEFAULT_COURT_NAME", "Cancha 1")
    monkeypatch.setattr(service_module.cfg, "CALL_SLOT_DURATION_MINUTES", 60)
    monkeypatch.setattr(
        service_module.cfg, "obtener_franjas_atencion_minutos", lambda: [(10 * 60, 20 * 60)]
    )
    monkeypatch.setattr(service_module.cfg, "obtener_dias_atencion", lambda: list(range(7)))
    service = DesktopAdminService(tmp_path)
    day = future_day()
    group = service.create_school_group(
        name="Categoría 2015", sport="Fútbol", category="2015", court="Cancha 1",
        capacity=10, monthly_fee=20000,
        schedules=[{
            "weekday": day.weekday(), "start_time": "18:00", "duration_minutes": 60,
        }],
    )
    for name, phone in (("Leo", "+5493511112222"), ("Luz", "+5493513334444")):
        student = service.create_school_student(
            name=name, guardian_name=f"Responsable {name}", guardian_phone=phone
        )
        service.enroll_school_student(student["student_id"], group["group_id"])

    schedule = service.day_schedule(day.isoformat(), include_all=True)
    cell = next(
        row for row in schedule["cells"]
        if row["court"] == "Cancha 1" and row["time"] == "18:00"
    )

    assert cell["booking"]["school_class"] is True
    assert cell["booking"]["school_group_id"] == group["group_id"]
    assert cell["booking"]["telefono"] == ""
    assert cell["booking"]["recipient_phones"] == [
        "+5493511112222", "+5493513334444"
    ]


def test_in_progress_booking_can_update_contact_without_moving_to_past(monkeypatch):
    today = dt.date.today()

    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(today.year, today.month, today.day, 10, 30)
            return value if tz is None else value.replace(tzinfo=tz)

    monkeypatch.setattr(service_module.dt, "datetime", FixedDateTime)
    service = build_service(monkeypatch, [{
        "reservation_id": "CURRENT-1",
        "fecha": display_day(today),
        "hora": "10:00",
        "cancha": "Cancha 1",
        "estado": "reservado",
        "nombre": "Nombre anterior",
        "telefono": "ADMIN:MANUAL:Nombre anterior",
    }], end_hour=14)

    service.update_booking(
        "CURRENT-1", day=today.isoformat(), time="10:00", court="Cancha 1",
        name="Cliente corregido", phone="+5493515556666",
    )

    assert service.calendar.rows[0]["nombre"] == "Cliente corregido"
    assert service.calendar.rows[0]["telefono"] == "+5493515556666"


def test_bookings_with_history_keeps_current_first_and_history_newest_first(monkeypatch):
    current_day = future_day()
    service = build_service(monkeypatch, [{
        "reservation_id": "CURRENT",
        "fecha": display_day(current_day),
        "hora": "20:00",
        "cancha": "Cancha 1",
        "estado": "reservado",
    }])
    service.calendar.finished = [
        {
            "reservation_id": "OLDER",
            "fecha": "Miércoles 08/10/2026",
            "hora": "20:00",
            "cancha": "Cancha 1",
            "estado": "finalizada",
        },
        {
            "reservation_id": "NEWER",
            "fecha": "Viernes 09/10/2026",
            "hora": "21:00",
            "cancha": "Cancha 1",
            "estado": "finalizada",
        },
    ]

    rows = service.bookings_with_history()

    assert [row["reservation_id"] for row in rows] == ["CURRENT", "NEWER", "OLDER"]
    assert rows[1]["_history"] is True


def test_cancelled_booking_is_hidden_from_priority_view_and_visible_in_history(monkeypatch):
    service = build_service(monkeypatch, [
        {
            "reservation_id": "CANCELLED",
            "fecha": "Jueves 22/10/2026",
            "hora": "15:00",
            "cancha": "Cancha 1",
            "estado": "cancelado",
        },
        {
            "reservation_id": "ACTIVE",
            "fecha": "Miércoles 21/10/2026",
            "hora": "21:00",
            "cancha": "Cancha 1",
            "estado": "pendiente",
        },
    ])

    assert [row["reservation_id"] for row in service.bookings()] == ["ACTIVE"]
    history = service.bookings_with_history()
    assert [row["reservation_id"] for row in history] == ["ACTIVE", "CANCELLED"]
    assert history[1]["_history"] is True


def test_delete_booking_removes_every_slot_for_id_and_preserves_other_rows(monkeypatch):
    service = build_service(monkeypatch, [
        {"reservation_id": "7", "fecha": "22/10/2026", "hora": "20:00", "cancha": "Cancha 1"},
        {"reservation_id": "7", "fecha": "22/10/2026", "hora": "21:00", "cancha": "Cancha 1"},
        {"reservation_id": "8", "fecha": "22/10/2026", "hora": "22:00", "cancha": "Cancha 1"},
    ])

    message = service.delete_booking("7")

    assert [row["reservation_id"] for row in service.calendar.rows] == ["8"]
    assert "2 filas eliminadas" in message
    assert "Caja se conservaron" in message


def test_delete_booking_can_remove_a_past_reservation(monkeypatch):
    service = build_service(monkeypatch, [])
    service.calendar.finished = [
        {"reservation_id": "OLD", "fecha": "09/10/2026", "hora": "20:00", "estado": "finalizada"},
        {"reservation_id": "KEEP", "fecha": "10/10/2026", "hora": "20:00", "estado": "finalizada"},
    ]

    service.delete_booking("OLD")

    assert [row["reservation_id"] for row in service.calendar.finished] == ["KEEP"]


def test_delete_booking_rejects_unknown_id_without_writing(monkeypatch):
    service = build_service(monkeypatch, [
        {"reservation_id": "8", "fecha": "22/10/2026", "hora": "22:00", "cancha": "Cancha 1"},
    ])

    with pytest.raises(ValueError, match="No encontré la reserva ID 99"):
        service.delete_booking("99")

    assert [row["reservation_id"] for row in service.calendar.rows] == ["8"]


def test_booking_sort_key_orders_real_dates_and_hours(monkeypatch):
    service = build_service(monkeypatch, [])
    wednesday_late = {
        "reservation_id": "5",
        "fecha": "Miércoles 21/10/2026",
        "hora": "21:00",
    }
    thursday_early = {
        "reservation_id": "4",
        "fecha": "Jueves 22/10/2026",
        "hora": "15:00",
    }

    by_date = sorted(
        [thursday_early, wednesday_late],
        key=lambda row: service.booking_sort_key(row, "fecha"),
    )
    by_hour = sorted(
        [wednesday_late, thursday_early],
        key=lambda row: service.booking_sort_key(row, "hora"),
    )

    assert [row["reservation_id"] for row in by_date] == ["5", "4"]
    assert [row["reservation_id"] for row in by_hour] == ["4", "5"]


def test_past_booking_details_returns_read_only_full_time_range(monkeypatch):
    service = build_service(monkeypatch, [])
    service.calendar.finished = [
        {
            "reservation_id": "OLD-7",
            "fecha": "Viernes 09/10/2026",
            "hora": hour,
            "cancha": "Cancha 1",
            "estado": "finalizada",
            "nombre": "Sebastián",
            "telefono": "3510000000",
            "senia_estado": "pagada",
            "precio_total": "30000",
            "monto_pendiente": "0",
            "duracion_horas": "2",
        }
        for hour in ("21:00", "22:00")
    ]

    details = service.past_booking_details("OLD-7", "2026-10-09")

    assert details["slot_count"] == 2
    assert details["time_range"] == "21:00 a 23:00"
    assert details["nombre"] == "Sebastián"
    assert details["estado"] == "finalizada"
    assert details["monto_pendiente"] == "0"


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
        "bar": 0,
        "operation": 0,
        "cases": 2,
        "tournaments": 0,
        "school": 0,
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


def test_opening_admin_does_not_mark_all_notification_sections_read():
    """El badge global sobrevive hasta abrir la pestaña que lo originó."""
    import inspect

    from cancheria.desktop.gui import CancheriaDesktop

    source = inspect.getsource(CancheriaDesktop.open_admin_panel)
    assert "mark_notifications_read" not in source


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
    assert 'text="Ver reservas pasadas"' in source
    assert 'text="Mostrar todos"' in source
    assert "bookings_with_history" in source
    assert "include_all=True" in source
    assert "def _past_booking_details_dialog" in source
    assert "def _promotion_dialog" in source
    assert '"in_progress", "recently_finished"' in source
    assert '"Enviar Mensaje"' in source
    assert '"Editar turno"' in source
    assert "webbrowser.open_new_tab" not in source
    assert "def _hours_schedule_signature" in source
    assert "self._refresh_hours(schedule)" in source
    assert "Detalle del turno pasado" in source
    assert "Consulta de solo lectura" in source
    assert "def _toggle_booking_sort" in source
    assert 'indicator = "  ▲" if self._booking_sort_ascending else "  ▼"' in source


def test_worker_delivers_operator_messages_through_existing_alert_queue():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "legacy"
        / "WPSetter_legacy.py"
    ).read_text(encoding="utf-8")

    assert 'category == "operator_customer_message"' in source
    assert "is_operator_customer_message" in source
    assert "def ingest_desktop_outbox_requests" in source
    assert "ingest_desktop_outbox_requests()" in source
    assert "await flush_admin_alert_queue(page" in source


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
