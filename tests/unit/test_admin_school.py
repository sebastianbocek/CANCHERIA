from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

from cancheria.domain.finance.ledger import FinancialLedger, cents_to_pesos
from cancheria.domain.reservations.calendar import CalendarioLlamadas
from cancheria.domain.school import SchoolService, school_slot_block
from cancheria.admin.desktop_service import DesktopAdminService


def build_school(tmp_path, *, conflicts=None):
    runtime = tmp_path / "runtime"
    return SchoolService(
        runtime / "escuelita.db",
        FinancialLedger(runtime / "caja.db"),
        courts_provider=lambda: ["Cancha 1", "Cancha 2"],
        conflict_provider=conflicts,
    )


def create_group(school, *, name="Categoría 2017", weekday=None, start="18:00"):
    teacher = school.create_teacher(name="Ana", phone="3510000000")
    return school.create_group(
        name=name,
        sport="Fútbol",
        category="2017",
        court="Cancha 1",
        capacity=12,
        monthly_fee=30000,
        age_min=8,
        age_max=10,
        teacher_id=teacher["teacher_id"],
        schedules=[{
            "weekday": dt.date.today().weekday() if weekday is None else weekday,
            "start_time": start,
            "duration_minutes": 90,
        }],
    )


def test_group_persists_and_blocks_real_calendar_slots(tmp_path):
    school = build_school(tmp_path)
    group = create_group(school)
    today = dt.date.today()

    assert group["teacher_name"] == "Ana"
    assert group["available"] == 12
    assert school_slot_block(tmp_path / "runtime" / "escuelita.db", today, "18:00", "Cancha 1")
    assert school_slot_block(tmp_path / "runtime" / "escuelita.db", today, "19:00", "Cancha 1")
    assert not school_slot_block(tmp_path / "runtime" / "escuelita.db", today, "20:00", "Cancha 1")

    reopened = build_school(tmp_path)
    assert reopened.group(group["group_id"])["schedule_text"].startswith(
        ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
    )

    calendar = CalendarioLlamadas(str(tmp_path / "runtime" / "calendario_turnos.csv"))
    assert calendar._esta_reservado(today, dt.time(18, 0), "Cancha 1") is True


def test_group_and_student_can_be_edited_from_the_admin_contract(tmp_path):
    school = build_school(tmp_path)
    group = create_group(school)
    student = school.create_student(
        name="Leo", guardian_name="Sebastián", guardian_phone="3511112222"
    )

    updated_group = school.update_group(
        group["group_id"],
        name="Categoría 2016/17",
        capacity=16,
        monthly_fee=35000,
        schedules=[{
            "weekday": dt.date.today().weekday(),
            "start_time": "19:00",
            "duration_minutes": 60,
        }],
    )
    updated_student = school.update_student(
        student["student_id"], guardian_name="Sebastián B.", medical_notes="Apto"
    )

    assert updated_group["name"] == "Categoría 2016/17"
    assert updated_group["capacity"] == 16
    assert updated_group["monthly_fee"] == 35000
    assert updated_group["schedules"][0]["start_time"] == "19:00"
    assert updated_student["guardian_name"] == "Sebastián B."
    assert updated_student["medical_notes"] == "Apto"


def test_group_and_student_can_be_deleted_without_orphans_or_losing_cash_history(tmp_path):
    school = build_school(tmp_path)
    group = create_group(school)
    student = school.create_student(
        name="Leo", guardian_name="Sebastián", guardian_phone="3511112222"
    )
    enrollment = school.enroll_student(student["student_id"], group["group_id"])
    school.record_attendance(enrollment["enrollment_id"], dt.date.today().isoformat(), "present")
    fee = school.fees()[0]
    school.record_payment(fee["fee_id"], amount=10000, method="Efectivo", request_key="delete-1")
    today = dt.date.today().isoformat()
    assert len(school.cash_ledger.list_movements(start_date=today, end_date=today)) == 1

    deleted_group = school.delete_group(group["group_id"])
    assert deleted_group["deleted"] is True
    assert school.group(group["group_id"]) == {}
    assert school.students()[0]["student_id"] == student["student_id"]
    assert school.students()[0]["enrollment_id"] is None
    assert school.fees() == []
    assert len(school.cash_ledger.list_movements(start_date=today, end_date=today)) == 1

    group_two = create_group(school, name="Categoría 2016", start="19:00")
    enrollment_two = school.enroll_student(student["student_id"], group_two["group_id"])
    assert enrollment_two["student_id"] == student["student_id"]
    deleted_student = school.delete_student(student["student_id"])
    assert deleted_student["deleted"] is True
    assert school.students(include_inactive=True) == []
    assert school.enrollments(active_only=False) == []

    with school._connect() as connection:
        actions = [row[0] for row in connection.execute(
            "SELECT action FROM school_history WHERE action='deleted' ORDER BY created_at"
        ).fetchall()]
    assert actions == ["deleted", "deleted"]


def test_group_rejects_school_and_booking_conflicts(tmp_path):
    school = build_school(tmp_path)
    create_group(school)
    with pytest.raises(ValueError, match="superpone"):
        create_group(school, name="Otro grupo")

    occupied = build_school(
        tmp_path / "other",
        conflicts=lambda day, time, court: time == "17:00" and court == "Cancha 1",
    )
    with pytest.raises(ValueError, match="reserva"):
        create_group(occupied, start="17:00")


def test_students_enrollment_attendance_partial_payments_and_cash(tmp_path):
    school = build_school(tmp_path)
    group = create_group(school)
    student = school.create_student(
        name="Leo", birth_date="2017-04-02", guardian_name="Sebastián",
        guardian_phone="+54 9 351 111-2222", medical_notes="Sin observaciones",
    )
    enrollment = school.enroll_student(student["student_id"], group["group_id"])
    attendance = school.record_attendance(
        enrollment["enrollment_id"], dt.date.today().isoformat(), "present"
    )
    assert attendance["status"] == "present"

    fee = school.fees()[0]
    partial = school.record_payment(
        fee["fee_id"], amount=10000, method="Efectivo", request_key="receipt-1"
    )
    assert partial["status"] == "partial"
    assert partial["balance"] == 20000
    duplicate = school.record_payment(
        fee["fee_id"], amount=10000, method="Efectivo", request_key="receipt-1"
    )
    assert duplicate["paid"] == 10000
    paid = school.record_payment(
        fee["fee_id"], amount=20000, method="Transferencia", request_key="receipt-2"
    )
    assert paid["status"] == "paid"
    assert paid["balance"] == 0

    movements = school.cash_ledger.list_movements(
        start_date=dt.date.today().isoformat(), end_date=dt.date.today().isoformat()
    )
    school_rows = [row for row in movements if row["origin"] == "Escuelita"]
    assert len(school_rows) == 2
    assert sum(cents_to_pesos(row["amount_cents"]) for row in school_rows) == 30000


def test_group_contacts_returns_unique_active_guardian_phones(tmp_path):
    school = build_school(tmp_path)
    group = create_group(school)
    for name, guardian, phone in (
        ("Leo", "Sebastián", "+54 9 351 111-2222"),
        ("Luz", "Sebastián", "+54 9 351 111-2222"),
        ("Mateo", "Laura", "+54 9 351 333-4444"),
    ):
        student = school.create_student(
            name=name, guardian_name=guardian, guardian_phone=phone
        )
        school.enroll_student(student["student_id"], group["group_id"])

    contacts = school.group_contacts(group["group_id"])

    assert [row["phone"] for row in contacts] == [
        "+5493511112222", "+5493513334444"
    ]


def test_pre_enrollment_balance_and_absence_are_contact_scoped(tmp_path):
    school = build_school(tmp_path)
    group = create_group(school)
    pre = school.create_pre_enrollment(
        child_name="Mateo", child_age=9, guardian_phone="+5493512223333",
        group_id=group["group_id"], request_key="wa-turn-1",
    )
    duplicate = school.create_pre_enrollment(
        child_name="Mateo", child_age=9, guardian_phone="+5493512223333",
        group_id=group["group_id"], request_key="wa-turn-1",
    )
    assert duplicate["pre_enrollment_id"] == pre["pre_enrollment_id"]

    student = school.create_student(
        name="Mateo", guardian_name="Laura", guardian_phone="+5493512223333"
    )
    enrollment = school.enroll_student(student["student_id"], group["group_id"])
    balance = school.contact_balance("+5493512223333")
    assert balance["balance"] == 30000
    absence = school.report_absence(
        "+5493512223333", class_date=dt.date.today().isoformat()
    )
    assert absence["enrollment_id"] == enrollment["enrollment_id"]
    assert absence["status"] == "excused"


def test_desktop_cash_snapshot_includes_school_fee_balance(tmp_path):
    service = DesktopAdminService(tmp_path)
    teacher = service.create_school_teacher(name="Profe")
    group = service.create_school_group(
        name="Inicial", sport="Fútbol", category="Inicial", court=service.courts()[0],
        capacity=10, monthly_fee=24000, teacher_id=teacher["teacher_id"],
        schedules=[{"weekday": dt.date.today().weekday(), "start_time": "18:00", "duration_minutes": 60}],
    )
    student = service.create_school_student(
        name="Luz", guardian_name="María", guardian_phone="3514445555"
    )
    service.enroll_school_student(student["student_id"], group["group_id"])
    fee = service.school_fees()[0]
    assert service.cash_snapshot()["pending_balances"] == 24000
    service.record_school_payment(
        fee["fee_id"], amount=9000, method="Efectivo", request_key="school-cash-1"
    )
    snapshot = service.cash_snapshot()
    assert snapshot["pending_balances"] == 15000
    assert any(row.get("origin") == "Escuelita" for row in snapshot["movements"])


def test_school_ui_and_canonical_whatsapp_contract_are_present():
    root = Path(__file__).resolve().parents[2]
    panel = (root / "src/cancheria/desktop/admin_panel.py").read_text(encoding="utf-8")
    agent = (root / "legacy/WPSetter_legacy.py").read_text(encoding="utf-8")

    assert panel.index('text="Torneos"') < panel.index('text="Escuelita"') < panel.index('text="Turnos Fijos"')
    for label in (
        "+  Nuevo alumno", "+  Nuevo grupo", "Editar seleccionado",
        "Registrar pago", "Tomar asistencia",
    ):
        assert label in panel
    assert "def _edit_school_group_dialog" in panel
    assert "def _edit_school_student_dialog" in panel
    assert "delete_school_student" in panel
    assert "delete_school_group" in panel
    assert '"🗑  Borrar"' in panel
    assert '"Editar turno"' in panel
    assert "school_group_id" in panel
    assert '"<Double-1>"' in panel
    assert "self.school_side_canvas" in panel
    assert "self.school_side_scroll" in panel
    assert "tree.configure(yscrollcommand=scroll.set)" in panel
    assert 'widget.bind("<MouseWheel>", self._scroll_school_side, add="+")' in panel
    assert 'widget.bind("<Button-4>", self._scroll_school_side, add="+")' in panel
    assert 'widget.bind("<Button-5>", self._scroll_school_side, add="+")' in panel
    for operation in (
        "query_school", "pre_enroll_school", "query_school_balance", "report_school_absence"
    ):
        assert operation in agent
    for tool in (
        "consultar_escuelita", "preinscribir_escuelita",
        "consultar_cuotas_escuelita", "avisar_ausencia_escuelita",
    ):
        assert tool in agent
    assert "school_tool_unresolved" in agent
    assert "_canonical_v184_silent_failure" in agent
    build_script = (root / "build_windows.bat").read_text(encoding="utf-8")
    assert "--hidden-import cancheria.domain.school.service" in build_script


def test_school_sidebar_mousewheel_scrolls_from_content_area():
    from cancheria.desktop.admin_panel import AdminPanel

    calls = []
    panel = object.__new__(AdminPanel)
    panel.school_side_canvas = SimpleNamespace(
        yview_scroll=lambda units, mode: calls.append((units, mode))
    )

    assert panel._scroll_school_side(SimpleNamespace(delta=-120, num=None)) == "break"
    assert panel._scroll_school_side(SimpleNamespace(delta=120, num=None)) == "break"
    assert panel._scroll_school_side(SimpleNamespace(delta=0, num=4)) == "break"
    assert panel._scroll_school_side(SimpleNamespace(delta=0, num=5)) == "break"
    assert calls == [(3, "units"), (-3, "units"), (-3, "units"), (3, "units")]


@pytest.mark.asyncio
async def test_whatsapp_school_tools_execute_structured_contract_without_phrase_router(tmp_path, monkeypatch):
    import legacy.WPSetter_legacy as agent

    school = build_school(tmp_path)
    group = create_group(school)
    monkeypatch.setattr(agent, "_SCHOOL_AGENT_SERVICE", school)
    perception = {
        "execution_contract": {
            "authoritative": True,
            "allowed_tools": ["consultar_escuelita"],
        }
    }
    query = await agent.ejecutar_tool_agent_v2(
        "consultar_escuelita", {"child_age": 9}, {}, perception, {},
        "+5493510000000", {}, ["consulta"],
    )
    assert query["ok"] is True
    assert query["data"]["groups"][0]["group_id"] == group["group_id"]

    perception["execution_contract"]["allowed_tools"] = ["preinscribir_escuelita"]
    created = await agent.ejecutar_tool_agent_v2(
        "preinscribir_escuelita",
        {"child_name": "Tomás", "child_age": 9, "group_id": group["group_id"], "request_key": "turn-1"},
        {}, perception, {}, "+5493510000000", {}, ["quiero inscribir"],
    )
    assert created["ok"] is True
    assert created["data"]["pre_enrollment"]["status"] == "pending"
