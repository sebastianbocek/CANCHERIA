from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable

from cancheria.domain.finance.ledger import FinancialLedger, cents_to_pesos, money_to_cents


SCHEMA = """
CREATE TABLE IF NOT EXISTS school_teachers (
    teacher_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    specialty TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS school_groups (
    group_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sport TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    age_min INTEGER,
    age_max INTEGER,
    court TEXT NOT NULL,
    teacher_id TEXT NOT NULL DEFAULT '',
    capacity INTEGER NOT NULL CHECK(capacity > 0),
    monthly_fee_cents INTEGER NOT NULL CHECK(monthly_fee_cents >= 0),
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS school_group_schedules (
    schedule_id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL REFERENCES school_groups(group_id),
    weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),
    start_time TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
    UNIQUE(group_id, weekday, start_time)
);
CREATE TABLE IF NOT EXISTS school_students (
    student_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    birth_date TEXT NOT NULL DEFAULT '',
    document TEXT NOT NULL DEFAULT '',
    guardian_name TEXT NOT NULL,
    guardian_phone TEXT NOT NULL,
    emergency_phone TEXT NOT NULL DEFAULT '',
    medical_notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS school_enrollments (
    enrollment_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES school_students(student_id),
    group_id TEXT NOT NULL REFERENCES school_groups(group_id),
    status TEXT NOT NULL DEFAULT 'active',
    start_date TEXT NOT NULL,
    end_date TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(student_id, group_id)
);
CREATE TABLE IF NOT EXISTS school_pre_enrollments (
    pre_enrollment_id TEXT PRIMARY KEY,
    child_name TEXT NOT NULL,
    child_age INTEGER,
    guardian_name TEXT NOT NULL DEFAULT '',
    guardian_phone TEXT NOT NULL,
    group_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    source TEXT NOT NULL DEFAULT 'WhatsApp',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS school_attendance (
    attendance_id TEXT PRIMARY KEY,
    enrollment_id TEXT NOT NULL REFERENCES school_enrollments(enrollment_id),
    class_date TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    responsible TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(enrollment_id, class_date)
);
CREATE TABLE IF NOT EXISTS school_fees (
    fee_id TEXT PRIMARY KEY,
    enrollment_id TEXT NOT NULL REFERENCES school_enrollments(enrollment_id),
    period TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
    paid_cents INTEGER NOT NULL DEFAULT 0 CHECK(paid_cents >= 0),
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(enrollment_id, period)
);
CREATE TABLE IF NOT EXISTS school_payments (
    payment_id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    fee_id TEXT NOT NULL REFERENCES school_fees(fee_id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    method TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    responsible TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS school_class_exceptions (
    exception_id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL REFERENCES school_groups(group_id),
    class_date TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(group_id, class_date)
);
CREATE TABLE IF NOT EXISTS school_history (
    history_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    responsible TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_school_students_guardian_phone
    ON school_students(guardian_phone);
CREATE INDEX IF NOT EXISTS idx_school_enrollments_group
    ON school_enrollments(group_id, status);
CREATE INDEX IF NOT EXISTS idx_school_fees_status
    ON school_fees(status, due_date);
CREATE INDEX IF NOT EXISTS idx_school_schedules_slot
    ON school_group_schedules(weekday, start_time);
"""


DAY_NAMES = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
ATTENDANCE_STATES = {"present", "absent", "excused", "recovered", "cancelled"}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _minutes(value: str) -> int:
    try:
        hour, minute = str(value or "").strip().split(":", 1)
        total = int(hour) * 60 + int(minute)
    except (TypeError, ValueError) as exc:
        raise ValueError("Ingresá la hora con formato HH:MM.") from exc
    if not 0 <= total < 24 * 60 or not 0 <= int(minute) <= 59:
        raise ValueError("Ingresá una hora válida con formato HH:MM.")
    return total


def _time(value: str) -> str:
    total = _minutes(value)
    return f"{total // 60:02d}:{total % 60:02d}"


def _date(value: Any, *, allow_empty: bool = False) -> str:
    text = str(value or "").strip()
    if not text and allow_empty:
        return ""
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError("Ingresá la fecha con formato AAAA-MM-DD.") from exc


def _period(value: Any | None = None) -> str:
    text = str(value or dt.date.today().strftime("%Y-%m")).strip()
    try:
        return dt.datetime.strptime(text, "%Y-%m").strftime("%Y-%m")
    except ValueError as exc:
        raise ValueError("Ingresá el período con formato AAAA-MM.") from exc


def _phone(value: Any) -> str:
    return "".join(char for char in str(value or "").strip() if char.isdigit() or char == "+")


class SchoolService:
    """Persistent school management shared by the desktop UI and WhatsApp tools."""

    def __init__(
        self,
        path: str | Path,
        cash_ledger: FinancialLedger,
        *,
        courts_provider: Callable[[], list[str]] | None = None,
        conflict_provider: Callable[[str, str, str], bool] | None = None,
    ) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cash_ledger = cash_ledger
        self.courts_provider = courts_provider or (lambda: [])
        self.conflict_provider = conflict_provider
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=20000")
        return connection

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any]:
        return dict(row) if row is not None else {}

    def _history(
        self,
        connection: sqlite3.Connection,
        entity_type: str,
        entity_id: str,
        action: str,
        payload: dict[str, Any],
        responsible: str = "",
    ) -> None:
        connection.execute(
            """INSERT INTO school_history (
                history_id, entity_type, entity_id, action, payload_json,
                responsible, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                _new_id("hist"), entity_type, entity_id, action,
                json.dumps(payload, ensure_ascii=False, default=str),
                str(responsible or "").strip(), _now(),
            ),
        )

    def teachers(self, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        where = "" if include_inactive else "WHERE active=1"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                f"SELECT * FROM school_teachers {where} ORDER BY name COLLATE NOCASE"
            ).fetchall()]

    def create_teacher(self, *, name: str, phone: str = "", specialty: str = "") -> dict[str, Any]:
        name = str(name or "").strip()
        if not name:
            raise ValueError("Completá el nombre del profesor.")
        teacher_id, moment = _new_id("teacher"), _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO school_teachers
                   (teacher_id, name, phone, specialty, active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                (teacher_id, name, _phone(phone), str(specialty or "").strip(), moment, moment),
            )
            self._history(connection, "teacher", teacher_id, "created", {"name": name})
            return self._row(connection.execute(
                "SELECT * FROM school_teachers WHERE teacher_id=?", (teacher_id,)
            ).fetchone())

    def _normalize_schedules(self, schedules: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[int, str]] = set()
        for raw in schedules or []:
            try:
                weekday = int(raw.get("weekday"))
                duration = int(raw.get("duration_minutes") or 60)
            except (TypeError, ValueError) as exc:
                raise ValueError("Revisá el día y la duración del horario.") from exc
            if weekday not in range(7) or duration <= 0 or duration > 8 * 60:
                raise ValueError("El día o la duración del horario no son válidos.")
            start = _time(str(raw.get("start_time") or ""))
            if _minutes(start) + duration > 24 * 60:
                raise ValueError("La clase debe terminar antes de la medianoche.")
            identity = (weekday, start)
            if identity in seen:
                continue
            seen.add(identity)
            normalized.append({"weekday": weekday, "start_time": start, "duration_minutes": duration})
        if not normalized:
            raise ValueError("Agregá al menos un día y horario al grupo.")
        by_weekday: dict[int, list[tuple[int, int]]] = {}
        for item in normalized:
            start_minutes = _minutes(item["start_time"])
            by_weekday.setdefault(int(item["weekday"]), []).append(
                (start_minutes, start_minutes + int(item["duration_minutes"]))
            )
        for intervals in by_weekday.values():
            ordered = sorted(intervals)
            if any(current_start < previous_end for (_, previous_end), (current_start, _) in zip(ordered, ordered[1:])):
                raise ValueError(
                    "Los horarios seleccionados se superponen entre sí para el mismo día."
                )
        return normalized

    def _validate_group_conflicts(
        self,
        *,
        court: str,
        schedules: list[dict[str, Any]],
        excluding_group_id: str = "",
    ) -> None:
        with self._connect() as connection:
            existing = connection.execute(
                """SELECT s.*, g.name FROM school_group_schedules s
                   JOIN school_groups g ON g.group_id=s.group_id
                   WHERE g.active=1 AND lower(g.court)=lower(?) AND g.group_id<>?""",
                (court, excluding_group_id),
            ).fetchall()
        for requested in schedules:
            requested_start = _minutes(requested["start_time"])
            requested_end = requested_start + int(requested["duration_minutes"])
            for row in existing:
                if int(row["weekday"]) != int(requested["weekday"]):
                    continue
                current_start = _minutes(row["start_time"])
                current_end = current_start + int(row["duration_minutes"])
                if requested_start < current_end and current_start < requested_end:
                    raise ValueError(
                        f"El horario se superpone con el grupo {row['name']} en {court}."
                    )
        if self.conflict_provider is None:
            return
        today = dt.date.today()
        for requested in schedules:
            weekday = int(requested["weekday"])
            first = today + dt.timedelta(days=(weekday - today.weekday()) % 7)
            start = _minutes(requested["start_time"])
            end = start + int(requested["duration_minutes"])
            for week in range(53):
                class_day = first + dt.timedelta(days=week * 7)
                cursor = start
                while cursor < end:
                    if self.conflict_provider(
                        class_day.isoformat(),
                        f"{cursor // 60:02d}:{cursor % 60:02d}",
                        court,
                    ):
                        raise ValueError(
                            f"Ya existe una reserva en {court} el "
                            f"{class_day.strftime('%d/%m/%Y')} a las "
                            f"{cursor // 60:02d}:{cursor % 60:02d}."
                        )
                    cursor += 60

    def create_group(
        self,
        *,
        name: str,
        sport: str,
        category: str,
        court: str,
        capacity: int,
        monthly_fee: Any,
        schedules: Iterable[dict[str, Any]],
        teacher_id: str = "",
        age_min: int | None = None,
        age_max: int | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        name, sport, court = (str(value or "").strip() for value in (name, sport, court))
        if not name or not sport:
            raise ValueError("Completá el nombre y el deporte del grupo.")
        if court not in self.courts_provider():
            raise ValueError("Seleccioná una cancha configurada en CANCHERIA.")
        try:
            capacity = int(capacity)
        except (TypeError, ValueError) as exc:
            raise ValueError("Ingresá una capacidad válida.") from exc
        if capacity <= 0:
            raise ValueError("La capacidad debe ser mayor que cero.")
        fee_cents = money_to_cents(monthly_fee)
        normalized = self._normalize_schedules(schedules)
        self._validate_group_conflicts(court=court, schedules=normalized)
        group_id, moment = _new_id("group"), _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO school_groups (
                    group_id, name, sport, category, age_min, age_max, court,
                    teacher_id, capacity, monthly_fee_cents, active, notes,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                (
                    group_id, name, sport, str(category or "").strip(), age_min, age_max,
                    court, str(teacher_id or "").strip(), capacity, fee_cents,
                    str(notes or "").strip(), moment, moment,
                ),
            )
            for schedule in normalized:
                connection.execute(
                    """INSERT INTO school_group_schedules
                       (schedule_id, group_id, weekday, start_time, duration_minutes)
                       VALUES (?, ?, ?, ?, ?)""",
                    (_new_id("schedule"), group_id, schedule["weekday"], schedule["start_time"], schedule["duration_minutes"]),
                )
            self._history(connection, "group", group_id, "created", {"name": name, "schedules": normalized})
        return self.group(group_id)

    def update_group(self, group_id: str, **changes: Any) -> dict[str, Any]:
        current = self.group(group_id)
        if not current:
            raise ValueError("El grupo ya no existe.")
        schedules = self._normalize_schedules(changes.get("schedules") or current["schedules"])
        court = str(changes.get("court", current["court"]) or "").strip()
        if court not in self.courts_provider():
            raise ValueError("Seleccioná una cancha configurada en CANCHERIA.")
        self._validate_group_conflicts(court=court, schedules=schedules, excluding_group_id=group_id)
        values = {
            "name": str(changes.get("name", current["name"]) or "").strip(),
            "sport": str(changes.get("sport", current["sport"]) or "").strip(),
            "category": str(changes.get("category", current["category"]) or "").strip(),
            "age_min": changes.get("age_min", current.get("age_min")),
            "age_max": changes.get("age_max", current.get("age_max")),
            "court": court,
            "teacher_id": str(changes.get("teacher_id", current.get("teacher_id")) or "").strip(),
            "capacity": int(changes.get("capacity", current["capacity"])),
            "monthly_fee_cents": money_to_cents(changes["monthly_fee"]) if "monthly_fee" in changes else int(current["monthly_fee_cents"]),
            "active": 1 if changes.get("active", current.get("active")) else 0,
            "notes": str(changes.get("notes", current.get("notes")) or "").strip(),
        }
        if not values["name"] or not values["sport"] or values["capacity"] <= 0:
            raise ValueError("Revisá el nombre, deporte y capacidad del grupo.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE school_groups SET name=?, sport=?, category=?, age_min=?, age_max=?,
                   court=?, teacher_id=?, capacity=?, monthly_fee_cents=?, active=?, notes=?, updated_at=?
                   WHERE group_id=?""",
                (*values.values(), _now(), group_id),
            )
            connection.execute("DELETE FROM school_group_schedules WHERE group_id=?", (group_id,))
            for schedule in schedules:
                connection.execute(
                    "INSERT INTO school_group_schedules VALUES (?, ?, ?, ?, ?)",
                    (_new_id("schedule"), group_id, schedule["weekday"], schedule["start_time"], schedule["duration_minutes"]),
                )
            self._history(connection, "group", group_id, "updated", {**values, "schedules": schedules})
        return self.group(group_id)

    def group(self, group_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT g.*, t.name AS teacher_name,
                   (SELECT COUNT(*) FROM school_enrollments e
                    WHERE e.group_id=g.group_id AND e.status='active') AS enrolled
                   FROM school_groups g LEFT JOIN school_teachers t ON t.teacher_id=g.teacher_id
                   WHERE g.group_id=?""",
                (str(group_id),),
            ).fetchone()
            if row is None:
                return {}
            result = dict(row)
            result["schedules"] = [dict(item) for item in connection.execute(
                "SELECT * FROM school_group_schedules WHERE group_id=? ORDER BY weekday, start_time",
                (str(group_id),),
            ).fetchall()]
        result["available"] = max(0, int(result["capacity"]) - int(result["enrolled"]))
        result["monthly_fee"] = cents_to_pesos(result["monthly_fee_cents"])
        result["schedule_text"] = self._schedule_text(result["schedules"])
        return result

    def delete_group(self, group_id: str, *, responsible: str = "Administrador") -> dict[str, Any]:
        """Delete a group and its dependent school records without erasing students or cash history."""
        current = self.group(group_id)
        if not current:
            raise ValueError("El grupo ya no existe.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            enrollment_ids = [
                str(row[0]) for row in connection.execute(
                    "SELECT enrollment_id FROM school_enrollments WHERE group_id=?", (group_id,)
                ).fetchall()
            ]
            fee_ids: list[str] = []
            if enrollment_ids:
                placeholders = ",".join("?" for _ in enrollment_ids)
                fee_ids = [
                    str(row[0]) for row in connection.execute(
                        f"SELECT fee_id FROM school_fees WHERE enrollment_id IN ({placeholders})",
                        enrollment_ids,
                    ).fetchall()
                ]
                if fee_ids:
                    fee_placeholders = ",".join("?" for _ in fee_ids)
                    connection.execute(
                        f"DELETE FROM school_payments WHERE fee_id IN ({fee_placeholders})", fee_ids
                    )
                connection.execute(
                    f"DELETE FROM school_fees WHERE enrollment_id IN ({placeholders})", enrollment_ids
                )
                connection.execute(
                    f"DELETE FROM school_attendance WHERE enrollment_id IN ({placeholders})",
                    enrollment_ids,
                )
                connection.execute("DELETE FROM school_enrollments WHERE group_id=?", (group_id,))
            connection.execute("DELETE FROM school_group_schedules WHERE group_id=?", (group_id,))
            connection.execute("DELETE FROM school_class_exceptions WHERE group_id=?", (group_id,))
            # A WhatsApp lead remains useful even if its suggested group is deleted.
            connection.execute(
                "UPDATE school_pre_enrollments SET group_id='', updated_at=? WHERE group_id=?",
                (_now(), group_id),
            )
            self._history(
                connection,
                "group",
                group_id,
                "deleted",
                {
                    "name": current.get("name", ""),
                    "enrollments_removed": len(enrollment_ids),
                    "fees_removed": len(fee_ids),
                },
                responsible,
            )
            connection.execute("DELETE FROM school_groups WHERE group_id=?", (group_id,))
        return {
            "group_id": group_id,
            "name": current.get("name", ""),
            "deleted": True,
            "enrollments_removed": len(enrollment_ids),
        }

    @staticmethod
    def _schedule_text(schedules: Iterable[dict[str, Any]]) -> str:
        return " · ".join(
            f"{DAY_NAMES[int(item['weekday'])]} {item['start_time']} ({int(item['duration_minutes'])} min)"
            for item in schedules
        )

    def groups(self, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        where = "" if include_inactive else "WHERE g.active=1"
        with self._connect() as connection:
            ids = [str(row[0]) for row in connection.execute(
                f"SELECT g.group_id FROM school_groups g {where} ORDER BY g.name COLLATE NOCASE"
            ).fetchall()]
        return [self.group(group_id) for group_id in ids]

    def create_student(
        self,
        *,
        name: str,
        guardian_name: str,
        guardian_phone: str,
        birth_date: str = "",
        document: str = "",
        emergency_phone: str = "",
        medical_notes: str = "",
    ) -> dict[str, Any]:
        name, guardian_name = str(name or "").strip(), str(guardian_name or "").strip()
        guardian_phone = _phone(guardian_phone)
        if not name or not guardian_name or not guardian_phone:
            raise ValueError("Completá alumno, responsable y teléfono.")
        normalized_birth = _date(birth_date, allow_empty=True)
        student_id, moment = _new_id("student"), _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO school_students (
                    student_id, name, birth_date, document, guardian_name,
                    guardian_phone, emergency_phone, medical_notes, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
                (
                    student_id, name, normalized_birth, str(document or "").strip(),
                    guardian_name, guardian_phone, _phone(emergency_phone),
                    str(medical_notes or "").strip(), moment, moment,
                ),
            )
            self._history(connection, "student", student_id, "created", {"name": name})
            return self._row(connection.execute(
                "SELECT * FROM school_students WHERE student_id=?", (student_id,)
            ).fetchone())

    def students(self, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        where = "" if include_inactive else "WHERE s.status='active'"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                f"""SELECT s.*, e.enrollment_id, e.group_id, e.status AS enrollment_status,
                    g.name AS group_name
                    FROM school_students s
                    LEFT JOIN school_enrollments e ON e.student_id=s.student_id AND e.status='active'
                    LEFT JOIN school_groups g ON g.group_id=e.group_id
                    {where}
                    ORDER BY s.name COLLATE NOCASE"""
            ).fetchall()]

    def update_student(self, student_id: str, **changes: Any) -> dict[str, Any]:
        with self._connect() as connection:
            current = connection.execute(
                "SELECT * FROM school_students WHERE student_id=?", (student_id,)
            ).fetchone()
        if current is None:
            raise ValueError("El alumno ya no existe.")
        values = dict(current)
        for key in (
            "name", "birth_date", "document", "guardian_name", "guardian_phone",
            "emergency_phone", "medical_notes", "status",
        ):
            if key in changes:
                values[key] = changes[key]
        values["name"] = str(values.get("name") or "").strip()
        values["guardian_name"] = str(values.get("guardian_name") or "").strip()
        values["guardian_phone"] = _phone(values.get("guardian_phone"))
        values["emergency_phone"] = _phone(values.get("emergency_phone"))
        values["birth_date"] = _date(values.get("birth_date"), allow_empty=True)
        if not values["name"] or not values["guardian_name"] or not values["guardian_phone"]:
            raise ValueError("Completá alumno, responsable y teléfono.")
        moment = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE school_students SET name=?, birth_date=?, document=?,
                   guardian_name=?, guardian_phone=?, emergency_phone=?, medical_notes=?,
                   status=?, updated_at=? WHERE student_id=?""",
                (
                    values["name"], values["birth_date"], str(values.get("document") or "").strip(),
                    values["guardian_name"], values["guardian_phone"], values["emergency_phone"],
                    str(values.get("medical_notes") or "").strip(),
                    str(values.get("status") or "active").strip(), moment, student_id,
                ),
            )
            self._history(connection, "student", student_id, "updated", {
                "name": values["name"], "status": values.get("status")
            })
            return self._row(connection.execute(
                "SELECT * FROM school_students WHERE student_id=?", (student_id,)
            ).fetchone())

    def delete_student(self, student_id: str, *, responsible: str = "Administrador") -> dict[str, Any]:
        """Delete one student and school-only dependants while preserving ledger movements."""
        with self._connect() as connection:
            current_row = connection.execute(
                "SELECT * FROM school_students WHERE student_id=?", (student_id,)
            ).fetchone()
            if current_row is None:
                raise ValueError("El alumno ya no existe.")
            current = dict(current_row)
            connection.execute("BEGIN IMMEDIATE")
            enrollment_ids = [
                str(row[0]) for row in connection.execute(
                    "SELECT enrollment_id FROM school_enrollments WHERE student_id=?", (student_id,)
                ).fetchall()
            ]
            fee_ids: list[str] = []
            if enrollment_ids:
                placeholders = ",".join("?" for _ in enrollment_ids)
                fee_ids = [
                    str(row[0]) for row in connection.execute(
                        f"SELECT fee_id FROM school_fees WHERE enrollment_id IN ({placeholders})",
                        enrollment_ids,
                    ).fetchall()
                ]
                if fee_ids:
                    fee_placeholders = ",".join("?" for _ in fee_ids)
                    connection.execute(
                        f"DELETE FROM school_payments WHERE fee_id IN ({fee_placeholders})", fee_ids
                    )
                connection.execute(
                    f"DELETE FROM school_fees WHERE enrollment_id IN ({placeholders})", enrollment_ids
                )
                connection.execute(
                    f"DELETE FROM school_attendance WHERE enrollment_id IN ({placeholders})",
                    enrollment_ids,
                )
                connection.execute("DELETE FROM school_enrollments WHERE student_id=?", (student_id,))
            self._history(
                connection,
                "student",
                student_id,
                "deleted",
                {
                    "name": current.get("name", ""),
                    "enrollments_removed": len(enrollment_ids),
                    "fees_removed": len(fee_ids),
                },
                responsible,
            )
            connection.execute("DELETE FROM school_students WHERE student_id=?", (student_id,))
        return {
            "student_id": student_id,
            "name": current.get("name", ""),
            "deleted": True,
            "enrollments_removed": len(enrollment_ids),
        }

    def enroll_student(
        self,
        student_id: str,
        group_id: str,
        *,
        start_date: str | None = None,
        notes: str = "",
        responsible: str = "Administrador",
    ) -> dict[str, Any]:
        group = self.group(group_id)
        if not group or not group.get("active"):
            raise ValueError("Seleccioná un grupo activo.")
        if int(group["available"]) <= 0:
            raise ValueError("El grupo no tiene cupos disponibles.")
        with self._connect() as connection:
            student = connection.execute(
                "SELECT * FROM school_students WHERE student_id=? AND status='active'", (student_id,)
            ).fetchone()
            if student is None:
                raise ValueError("Seleccioná un alumno activo.")
            enrollment_id, moment = _new_id("enrollment"), _now()
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """INSERT INTO school_enrollments (
                        enrollment_id, student_id, group_id, status, start_date,
                        end_date, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, 'active', ?, NULL, ?, ?, ?)""",
                    (
                        enrollment_id, student_id, group_id,
                        _date(start_date or dt.date.today().isoformat()),
                        str(notes or "").strip(), moment, moment,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("El alumno ya está inscripto en ese grupo.") from exc
            self._history(connection, "enrollment", enrollment_id, "created", {
                "student_id": student_id, "group_id": group_id
            }, responsible)
        self.ensure_monthly_fees(_period())
        return self.enrollment(enrollment_id)

    def enrollment(self, enrollment_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT e.*, s.name AS student_name, s.guardian_name, s.guardian_phone,
                   g.name AS group_name, g.monthly_fee_cents, g.court
                   FROM school_enrollments e
                   JOIN school_students s ON s.student_id=e.student_id
                   JOIN school_groups g ON g.group_id=e.group_id
                   WHERE e.enrollment_id=?""", (enrollment_id,),
            ).fetchone()
            return self._row(row)

    def enrollments(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        where = "WHERE e.status='active'" if active_only else ""
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                f"""SELECT e.*, s.name AS student_name, s.guardian_name, s.guardian_phone,
                    g.name AS group_name, g.court, g.monthly_fee_cents
                    FROM school_enrollments e
                    JOIN school_students s ON s.student_id=e.student_id
                    JOIN school_groups g ON g.group_id=e.group_id
                    {where} ORDER BY g.name COLLATE NOCASE, s.name COLLATE NOCASE"""
            ).fetchall()]

    def group_contacts(self, group_id: str) -> list[dict[str, str]]:
        """Return unique active guardian contacts for an Escuelita group."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT s.guardian_name, s.guardian_phone, s.name AS student_name
                   FROM school_enrollments e
                   JOIN school_students s ON s.student_id=e.student_id
                   WHERE e.group_id=? AND e.status='active' AND s.status='active'
                   ORDER BY s.name COLLATE NOCASE""",
                (str(group_id or ""),),
            ).fetchall()
        result: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            phone = _phone(row["guardian_phone"])
            digits = "".join(character for character in phone if character.isdigit())
            if len(digits) < 8 or digits in seen:
                continue
            seen.add(digits)
            result.append({
                "name": str(row["guardian_name"] or "").strip(),
                "phone": phone,
                "student_name": str(row["student_name"] or "").strip(),
            })
        return result

    def cancel_enrollment(
        self, enrollment_id: str, *, responsible: str = "Administrador"
    ) -> dict[str, Any]:
        current = self.enrollment(enrollment_id)
        if not current:
            raise ValueError("La inscripción ya no existe.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE school_enrollments SET status='cancelled', end_date=?, updated_at=?
                   WHERE enrollment_id=?""",
                (dt.date.today().isoformat(), _now(), enrollment_id),
            )
            self._history(
                connection, "enrollment", enrollment_id, "cancelled", {}, responsible
            )
        return self.enrollment(enrollment_id)

    def resolve_pre_enrollment(
        self, pre_enrollment_id: str, status: str, *, responsible: str = "Administrador"
    ) -> dict[str, Any]:
        status = str(status or "").strip().casefold()
        if status not in {"approved", "rejected", "cancelled"}:
            raise ValueError("Seleccioná una resolución válida para la preinscripción.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE school_pre_enrollments SET status=?, updated_at=? WHERE pre_enrollment_id=?",
                (status, _now(), pre_enrollment_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("La preinscripción ya no existe.")
            self._history(
                connection, "pre_enrollment", pre_enrollment_id, status, {}, responsible
            )
            return self._row(connection.execute(
                "SELECT * FROM school_pre_enrollments WHERE pre_enrollment_id=?",
                (pre_enrollment_id,),
            ).fetchone())

    def create_pre_enrollment(
        self,
        *,
        child_name: str,
        guardian_phone: str,
        child_age: int | None = None,
        guardian_name: str = "",
        group_id: str = "",
        notes: str = "",
        source: str = "WhatsApp",
        request_key: str = "",
    ) -> dict[str, Any]:
        child_name, guardian_phone = str(child_name or "").strip(), _phone(guardian_phone)
        if not child_name or not guardian_phone:
            raise ValueError("Para la preinscripción hacen falta el nombre del alumno y un teléfono responsable.")
        if group_id:
            group = self.group(group_id)
            if not group or not group.get("active") or int(group.get("available") or 0) <= 0:
                raise ValueError("El grupo elegido no tiene un cupo disponible.")
        identity = str(request_key or "").strip()
        with self._connect() as connection:
            if identity:
                prior = connection.execute(
                    "SELECT * FROM school_pre_enrollments WHERE notes LIKE ? LIMIT 1",
                    (f"%request:{identity}%",),
                ).fetchone()
                if prior is not None:
                    return dict(prior)
            pre_id, moment = _new_id("pre"), _now()
            stored_notes = str(notes or "").strip()
            if identity:
                stored_notes = " · ".join(part for part in (stored_notes, f"request:{identity}") if part)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO school_pre_enrollments (
                    pre_enrollment_id, child_name, child_age, guardian_name,
                    guardian_phone, group_id, status, source, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
                (pre_id, child_name, child_age, str(guardian_name or "").strip(), guardian_phone,
                 str(group_id or "").strip(), str(source or "WhatsApp"), stored_notes, moment, moment),
            )
            self._history(connection, "pre_enrollment", pre_id, "created", {
                "child_name": child_name, "group_id": group_id, "source": source
            })
            return self._row(connection.execute(
                "SELECT * FROM school_pre_enrollments WHERE pre_enrollment_id=?", (pre_id,)
            ).fetchone())

    def pre_enrollments(self, *, pending_only: bool = True) -> list[dict[str, Any]]:
        where = "WHERE p.status='pending'" if pending_only else ""
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                f"""SELECT p.*, g.name AS group_name FROM school_pre_enrollments p
                    LEFT JOIN school_groups g ON g.group_id=p.group_id
                    {where} ORDER BY p.created_at DESC"""
            ).fetchall()]

    def ensure_monthly_fees(self, period: str | None = None) -> int:
        period = _period(period)
        due_date = f"{period}-10"
        moment, inserted = _now(), 0
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT e.enrollment_id, g.monthly_fee_cents
                   FROM school_enrollments e JOIN school_groups g ON g.group_id=e.group_id
                   WHERE e.status='active' AND g.active=1"""
            ).fetchall()
            for row in rows:
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO school_fees (
                        fee_id, enrollment_id, period, amount_cents, paid_cents,
                        due_date, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 0, ?, 'pending', ?, ?)""",
                    (_new_id("fee"), row["enrollment_id"], period, int(row["monthly_fee_cents"]), due_date, moment, moment),
                )
                inserted += int(cursor.rowcount > 0)
        return inserted

    def fees(self, *, period: str | None = None, pending_only: bool = False) -> list[dict[str, Any]]:
        period = _period(period)
        self.ensure_monthly_fees(period)
        clauses, params = ["f.period=?"], [period]
        if pending_only:
            clauses.append("f.status IN ('pending','partial','overdue')")
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT f.*, e.student_id, e.group_id, s.name AS student_name,
                   s.guardian_name, s.guardian_phone, g.name AS group_name
                   FROM school_fees f
                   JOIN school_enrollments e ON e.enrollment_id=f.enrollment_id
                   JOIN school_students s ON s.student_id=e.student_id
                   JOIN school_groups g ON g.group_id=e.group_id
                   WHERE """ + " AND ".join(clauses) + " ORDER BY f.due_date, s.name COLLATE NOCASE",
                params,
            ).fetchall()
            result = [dict(row) for row in rows]
        today = dt.date.today()
        for row in result:
            if row["status"] in {"pending", "partial"} and dt.date.fromisoformat(row["due_date"]) < today:
                row["status"] = "overdue"
            row["amount"] = cents_to_pesos(row["amount_cents"])
            row["paid"] = cents_to_pesos(row["paid_cents"])
            row["balance"] = cents_to_pesos(max(0, int(row["amount_cents"]) - int(row["paid_cents"])))
        return result

    def record_payment(
        self,
        fee_id: str,
        *,
        amount: Any,
        method: str,
        responsible: str = "Administrador",
        request_key: str | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        amount_cents = money_to_cents(amount)
        if amount_cents <= 0:
            raise ValueError("El importe debe ser mayor que cero.")
        request_key = str(request_key or f"school:{fee_id}:{uuid.uuid4().hex}")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT fee_id FROM school_payments WHERE request_key=?", (request_key,)
            ).fetchone()
            if duplicate is not None:
                if duplicate["fee_id"] != fee_id:
                    raise ValueError("La clave de pago ya fue utilizada para otra cuota.")
                row = self._fee(connection, fee_id)
                row["amount"] = cents_to_pesos(row["amount_cents"])
                row["paid"] = cents_to_pesos(row["paid_cents"])
                row["balance"] = cents_to_pesos(
                    max(0, int(row["amount_cents"]) - int(row["paid_cents"]))
                )
                return row
            fee = connection.execute("SELECT * FROM school_fees WHERE fee_id=?", (fee_id,)).fetchone()
            if fee is None:
                raise ValueError("La cuota ya no existe.")
            balance = int(fee["amount_cents"]) - int(fee["paid_cents"])
            if balance <= 0:
                raise ValueError("La cuota no tiene saldo pendiente.")
            if amount_cents > balance:
                raise ValueError("El importe supera el saldo pendiente de la cuota.")
            payment_id, moment = _new_id("schoolpay"), str(occurred_at or _now())
            connection.execute(
                """INSERT INTO school_payments
                   (payment_id, request_key, fee_id, amount_cents, method, occurred_at, responsible, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (payment_id, request_key, fee_id, amount_cents, str(method or "Otros"), moment, responsible, _now()),
            )
            new_paid = int(fee["paid_cents"]) + amount_cents
            status = "paid" if new_paid >= int(fee["amount_cents"]) else "partial"
            connection.execute(
                "UPDATE school_fees SET paid_cents=?, status=?, updated_at=? WHERE fee_id=?",
                (new_paid, status, _now(), fee_id),
            )
            detail = self._fee(connection, fee_id)
            self._history(connection, "fee", fee_id, "payment", {
                "payment_id": payment_id, "amount_cents": amount_cents, "method": method
            }, responsible)
        self.cash_ledger.record(
            movement_type="school_fee_payment",
            direction="income",
            amount=cents_to_pesos(amount_cents),
            occurred_at=moment,
            payment_method=method,
            concept=f"Cuota Escuelita · {detail.get('period')}",
            client=str(detail.get("student_name") or ""),
            registration_id=fee_id,
            court=str(detail.get("court") or "Escuelita"),
            origin="Escuelita",
            responsible=responsible,
            idempotency_key=f"school-payment:{request_key}",
        )
        return self.fee(fee_id)

    @staticmethod
    def _fee(connection: sqlite3.Connection, fee_id: str) -> dict[str, Any]:
        row = connection.execute(
            """SELECT f.*, s.name AS student_name, s.guardian_phone,
               g.name AS group_name, g.court
               FROM school_fees f
               JOIN school_enrollments e ON e.enrollment_id=f.enrollment_id
               JOIN school_students s ON s.student_id=e.student_id
               JOIN school_groups g ON g.group_id=e.group_id
               WHERE f.fee_id=?""", (fee_id,),
        ).fetchone()
        return dict(row) if row is not None else {}

    def fee(self, fee_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = self._fee(connection, fee_id)
        if row:
            row["amount"] = cents_to_pesos(row["amount_cents"])
            row["paid"] = cents_to_pesos(row["paid_cents"])
            row["balance"] = cents_to_pesos(max(0, int(row["amount_cents"]) - int(row["paid_cents"])))
        return row

    def record_attendance(
        self,
        enrollment_id: str,
        class_date: str,
        status: str,
        *,
        notes: str = "",
        responsible: str = "Administrador",
    ) -> dict[str, Any]:
        status = str(status or "").strip().casefold()
        if status not in ATTENDANCE_STATES:
            raise ValueError("Seleccioná un estado de asistencia válido.")
        class_date = _date(class_date)
        with self._connect() as connection:
            if connection.execute(
                "SELECT 1 FROM school_enrollments WHERE enrollment_id=? AND status='active'", (enrollment_id,)
            ).fetchone() is None:
                raise ValueError("La inscripción ya no está activa.")
            moment = _now()
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT attendance_id FROM school_attendance WHERE enrollment_id=? AND class_date=?",
                (enrollment_id, class_date),
            ).fetchone()
            attendance_id = current["attendance_id"] if current else _new_id("attendance")
            connection.execute(
                """INSERT INTO school_attendance (
                    attendance_id, enrollment_id, class_date, status, notes,
                    responsible, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(enrollment_id, class_date) DO UPDATE SET
                    status=excluded.status, notes=excluded.notes,
                    responsible=excluded.responsible, updated_at=excluded.updated_at""",
                (attendance_id, enrollment_id, class_date, status, str(notes or "").strip(), responsible, moment, moment),
            )
            self._history(connection, "attendance", attendance_id, "recorded", {
                "enrollment_id": enrollment_id, "class_date": class_date, "status": status
            }, responsible)
            return self._row(connection.execute(
                "SELECT * FROM school_attendance WHERE attendance_id=?", (attendance_id,)
            ).fetchone())

    def report_absence(
        self,
        guardian_phone: str,
        *,
        class_date: str,
        group_id: str = "",
        notes: str = "Aviso recibido por WhatsApp",
    ) -> dict[str, Any]:
        phone = _phone(guardian_phone)
        with self._connect() as connection:
            params: list[Any] = [phone]
            query = """SELECT e.enrollment_id, s.name AS student_name, g.name AS group_name
                       FROM school_enrollments e
                       JOIN school_students s ON s.student_id=e.student_id
                       JOIN school_groups g ON g.group_id=e.group_id
                       WHERE e.status='active' AND s.guardian_phone=?"""
            if group_id:
                query += " AND e.group_id=?"
                params.append(group_id)
            rows = connection.execute(query, params).fetchall()
        if len(rows) != 1:
            raise ValueError("No se pudo identificar una única inscripción activa para registrar la ausencia.")
        attendance = self.record_attendance(
            rows[0]["enrollment_id"], class_date, "excused", notes=notes, responsible="Agente IA"
        )
        return {**attendance, "student_name": rows[0]["student_name"], "group_name": rows[0]["group_name"]}

    def contact_balance(self, guardian_phone: str, *, period: str | None = None) -> dict[str, Any]:
        phone = _phone(guardian_phone)
        fees = [row for row in self.fees(period=period) if _phone(row.get("guardian_phone")) == phone]
        return {
            "period": _period(period),
            "fees": fees,
            "total": sum(int(row["amount"]) for row in fees),
            "paid": sum(int(row["paid"]) for row in fees),
            "balance": sum(int(row["balance"]) for row in fees),
        }

    def public_catalog(self, *, child_age: int | None = None) -> list[dict[str, Any]]:
        result = []
        for group in self.groups():
            if child_age is not None:
                if group.get("age_min") is not None and child_age < int(group["age_min"]):
                    continue
                if group.get("age_max") is not None and child_age > int(group["age_max"]):
                    continue
            result.append({
                "group_id": group["group_id"],
                "name": group["name"],
                "sport": group["sport"],
                "category": group["category"],
                "age_min": group.get("age_min"),
                "age_max": group.get("age_max"),
                "court": group["court"],
                "teacher": group.get("teacher_name") or "",
                "schedule": group["schedule_text"],
                "monthly_fee": group["monthly_fee"],
                "available": group["available"],
            })
        return result

    def classes_for_day(self, day: str | dt.date) -> list[dict[str, Any]]:
        selected = day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day))
        result = []
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT s.*, g.name AS group_name, g.sport, g.category, g.court,
                   g.teacher_id, t.name AS teacher_name,
                   (SELECT COUNT(*) FROM school_enrollments e
                    WHERE e.group_id=g.group_id AND e.status='active') AS enrolled
                   FROM school_group_schedules s
                   JOIN school_groups g ON g.group_id=s.group_id
                   LEFT JOIN school_teachers t ON t.teacher_id=g.teacher_id
                   WHERE g.active=1 AND s.weekday=?
                   ORDER BY s.start_time, g.court""", (selected.weekday(),),
            ).fetchall()
            for row in rows:
                exception = connection.execute(
                    "SELECT status FROM school_class_exceptions WHERE group_id=? AND class_date=?",
                    (row["group_id"], selected.isoformat()),
                ).fetchone()
                if exception is not None and exception["status"] == "cancelled":
                    continue
                result.append({**dict(row), "class_date": selected.isoformat()})
        return result

    def slot_blocked(self, day: dt.date, time: str, court: str, *, slot_minutes: int = 60) -> bool:
        slot_start = _minutes(time)
        slot_end = slot_start + max(1, int(slot_minutes))
        for item in self.classes_for_day(day):
            if str(item.get("court") or "").strip().casefold() != str(court or "").strip().casefold():
                continue
            class_start = _minutes(item["start_time"])
            class_end = class_start + int(item["duration_minutes"])
            if slot_start < class_end and class_start < slot_end:
                return True
        return False

    def history(self, entity_type: str = "", entity_id: str = "") -> list[dict[str, Any]]:
        clauses, params = [], []
        if entity_type:
            clauses.append("entity_type=?")
            params.append(entity_type)
        if entity_id:
            clauses.append("entity_id=?")
            params.append(entity_id)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                f"SELECT * FROM school_history {where} ORDER BY created_at DESC", params
            ).fetchall()]

    def snapshot(self, *, period: str | None = None) -> dict[str, Any]:
        period = _period(period)
        groups = self.groups()
        students = self.students()
        fees = self.fees(period=period)
        today_classes = self.classes_for_day(dt.date.today())
        pending_pre = self.pre_enrollments()
        return {
            "period": period,
            "active_students": len({row["student_id"] for row in students}),
            "active_groups": len(groups),
            "pending_fees": sum(1 for row in fees if int(row["balance"]) > 0),
            "pending_amount": sum(int(row["balance"]) for row in fees),
            "income_month": sum(int(row["paid"]) for row in fees),
            "classes_today": len(today_classes),
            "pending_pre_enrollments": len(pending_pre),
            "groups": groups,
            "students": students,
            "fees": fees,
            "today_classes": today_classes,
            "pre_enrollments": pending_pre,
        }


def school_slot_block(
    database_path: str | Path,
    day: dt.date,
    time: str,
    court: str,
    *,
    slot_minutes: int = 60,
) -> bool:
    """Read-only availability hook used by the booking calendar.

    It intentionally fails open if the optional module/database is unavailable;
    an I/O issue is handled by the agent's normal safe-exit path instead of
    corrupting the calendar CSV.
    """
    path = Path(database_path)
    if not path.is_file():
        return False
    try:
        slot_start = _minutes(time)
        slot_end = slot_start + max(1, int(slot_minutes))
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """SELECT s.group_id, s.start_time, s.duration_minutes
                   FROM school_group_schedules s
                   JOIN school_groups g ON g.group_id=s.group_id
                   WHERE g.active=1 AND s.weekday=? AND lower(g.court)=lower(?)
                     AND NOT EXISTS (
                         SELECT 1 FROM school_class_exceptions e
                         WHERE e.group_id=s.group_id AND e.class_date=? AND e.status='cancelled'
                     )""",
                (day.weekday(), str(court or "").strip(), day.isoformat()),
            ).fetchall()
        finally:
            connection.close()
        return any(
            slot_start < _minutes(row["start_time"]) + int(row["duration_minutes"])
            and _minutes(row["start_time"]) < slot_end
            for row in rows
        )
    except (OSError, sqlite3.Error, ValueError):
        return False
