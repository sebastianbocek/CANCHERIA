"""Motor transaccional de inscripciones de equipos a eventos de CANCHERIA.

La interpretacion del lenguaje pertenece al agente. Este modulo solo acepta
datos estructurados y protege persistencia, identidad, pagos y capacidad.
"""

from __future__ import annotations

import contextlib
import csv
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import threading
import unicodedata
import uuid
from pathlib import Path
from cancheria.paths import runtime_dir
from typing import Any, Dict, Iterable, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None


BASE_DIR = runtime_dir() / "events"
BUSINESS_EVENTS_FILE = BASE_DIR / "business_events.json"
BUSINESS_EVENTS_DIR = BASE_DIR / "torneos"
EVENT_REGISTRATION_HOLD_MINUTES = max(
    1, int(os.getenv("EVENT_REGISTRATION_HOLD_MINUTES", "10"))
)

EVENT_REGISTRATION_FIELDS = [
    "registration_id",
    "event_id",
    "event_name",
    "event_date",
    "team_name",
    "contact_name",
    "phone",
    "status",
    "registration_price",
    "required_payment",
    "paid_amount",
    "remaining_amount",
    "payment_status",
    "payment_method",
    "receipt_fingerprint",
    "created_at",
    "hold_started_at",
    "hold_expires_at",
    "last_payment_at",
    "confirmed_at",
    "cancelled_at",
    "expired_at",
    "updated_at",
]

_LOCKS: Dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class EventRegistrationError(RuntimeError):
    """Error de dominio que puede presentarse sin perder invariantes."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": False, "reason": self.code, "message": str(self), **self.details}


def _tz() -> dt.tzinfo:
    if ZoneInfo is not None:
        try:
            return ZoneInfo(os.getenv("LOCAL_TIMEZONE", "America/Argentina/Buenos_Aires"))
        except Exception:
            pass
    return dt.timezone(dt.timedelta(hours=-3))


def _now(value: Optional[dt.datetime] = None) -> dt.datetime:
    current = value or dt.datetime.now(_tz())
    if current.tzinfo is None:
        current = current.replace(tzinfo=_tz())
    return current.astimezone(_tz())


def _parse_datetime(value: Any) -> Optional[dt.datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_tz())
        return parsed.astimezone(_tz())
    except (TypeError, ValueError):
        return None


def normalize_event_date(value: Any) -> str:
    """Normaliza un valor ya comprendido por IA; no interpreta lenguaje natural."""
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value or "").strip()
    parsed: Optional[dt.date] = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            parsed = dt.datetime.strptime(text, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        raise EventRegistrationError(
            "invalid_event_date",
            "La fecha del torneo debe llegar normalizada como YYYY-MM-DD o DD/MM/YYYY.",
        )
    return parsed.isoformat()


def format_event_date(value: Any) -> str:
    iso = normalize_event_date(value)
    return dt.datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def _normalize_identity(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _slug(value: Any) -> str:
    normalized = _normalize_identity(value)
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")[:64] or "torneo"


def _money(value: Any, field: str = "amount") -> int:
    if isinstance(value, bool):
        raise EventRegistrationError(f"invalid_{field}", f"{field} debe ser numerico.")
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        raise EventRegistrationError(f"invalid_{field}", f"{field} debe ser numerico.")
    if parsed < 0:
        raise EventRegistrationError(f"invalid_{field}", f"{field} no puede ser negativo.")
    return parsed


def _capacity(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise EventRegistrationError("invalid_capacity", "La cantidad maxima de equipos debe ser entera.")
    if parsed <= 0:
        raise EventRegistrationError("invalid_capacity", "La cantidad maxima de equipos debe ser mayor que cero.")
    return parsed


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _thread_lock(path: Path) -> threading.RLock:
    key = _path_key(path)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


@contextlib.contextmanager
def _exclusive_file_lock(target: Path):
    """Lock de proceso + lock de archivo, valido en Windows y POSIX."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(f"{target}.lock")
    local_lock = _thread_lock(lock_path)
    with local_lock:
        handle = open(lock_path, "a+b")
        try:
            handle.seek(0)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:  # pragma: no cover - CI principal es Windows
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()


def _atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _atomic_csv_write(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EVENT_REGISTRATION_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in EVENT_REGISTRATION_FIELDS})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def read_business_events() -> List[Dict[str, Any]]:
    path = Path(BUSINESS_EVENTS_FILE)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    events = payload.get("events", []) if isinstance(payload, dict) else payload
    return [dict(item) for item in events if isinstance(item, dict)]


def write_business_events_atomic(events: List[Dict[str, Any]]) -> None:
    path = Path(BUSINESS_EVENTS_FILE)
    with _exclusive_file_lock(path):
        _atomic_json_write(path, {"version": 1, "events": events, "updated_at": _now().isoformat()})


def _event_csv_path(event: Dict[str, Any]) -> Path:
    persisted = str((event or {}).get("registrations_csv_path") or "").strip()
    if not persisted:
        raise EventRegistrationError("missing_event_csv_path", "El evento no tiene CSV persistido.")
    path = Path(persisted)
    return path if path.is_absolute() else BASE_DIR / path


def _new_event_csv_relative(event_id: str, name: str) -> str:
    filename = f"torneo_{event_id}__{_slug(name)}.csv"
    try:
        return str((Path(BUSINESS_EVENTS_DIR) / filename).relative_to(BASE_DIR)).replace("\\", "/")
    except ValueError:
        return str(Path(BUSINESS_EVENTS_DIR) / filename)


def _init_business_event_csv(event: Dict[str, Any]) -> Path:
    path = _event_csv_path(event)
    with _exclusive_file_lock(path):
        if not path.exists():
            _atomic_csv_write(path, [])
    return path


def read_event_registrations(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = _event_csv_path(event)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_event_registrations_atomic(event: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    path = _event_csv_path(event)
    with _exclusive_file_lock(path):
        _atomic_csv_write(path, rows)


def _expire_rows(rows: List[Dict[str, Any]], now: dt.datetime) -> int:
    changed = 0
    for row in rows:
        if row.get("status") != "pending_payment":
            continue
        expires = _parse_datetime(row.get("hold_expires_at"))
        if expires is not None and expires <= now:
            stamp = now.isoformat()
            row["status"] = "expired"
            row["expired_at"] = stamp
            row["updated_at"] = stamp
            changed += 1
    return changed


def _capacity_from_rows(event: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    maximum = _capacity(event.get("capacity"))
    confirmed = sum(1 for row in rows if row.get("status") == "confirmed")
    holds = sum(1 for row in rows if row.get("status") == "pending_payment")
    occupied = confirmed + holds
    available = max(0, maximum - occupied)
    return {
        "capacity": maximum,
        "confirmed": confirmed,
        "active_holds": holds,
        "occupied": occupied,
        "available": available,
        "is_full": available == 0,
    }


def configure_business_event(
    name: Any,
    registration_price: Any,
    capacity: Any,
    event_date: Any,
    *,
    prize: Any = None,
    payment_alias: Optional[str] = None,
    now: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    clean_name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not clean_name:
        raise EventRegistrationError("missing_event_name", "Falta el nombre del torneo.")
    price = _money(registration_price, "registration_price")
    if price <= 0:
        raise EventRegistrationError("invalid_registration_price", "El precio debe ser mayor que cero.")
    prize_amount = None
    if prize is not None:
        prize_amount = _money(prize, "prize")
        if prize_amount <= 0:
            raise EventRegistrationError("invalid_prize", "El premio debe ser mayor que cero.")
    maximum = _capacity(capacity)
    date_iso = normalize_event_date(event_date)
    timestamp = _now(now).isoformat()
    identity = (_normalize_identity(clean_name), date_iso)
    events_path = Path(BUSINESS_EVENTS_FILE)

    with _exclusive_file_lock(events_path):
        events = read_business_events()
        existing = next(
            (
                event for event in events
                if (_normalize_identity(event.get("name")), str(event.get("date") or "")) == identity
            ),
            None,
        )
        created = existing is None
        if existing is None:
            event_id = f"evt_{uuid.uuid4().hex[:10]}"
            existing = {
                "event_id": event_id,
                "created_at": timestamp,
                "registrations_csv_path": _new_event_csv_relative(event_id, clean_name),
            }
            events.append(existing)
        else:
            csv_path = _event_csv_path(existing)
            with _exclusive_file_lock(csv_path):
                rows = read_event_registrations(existing)
                expired = _expire_rows(rows, _now(now))
                if expired:
                    _atomic_csv_write(csv_path, rows)
                state = _capacity_from_rows(existing, rows)
                if maximum < state["occupied"]:
                    raise EventRegistrationError(
                        "capacity_below_occupied",
                        "No se puede reducir el maximo por debajo de confirmados mas holds activos.",
                        capacity_state=state,
                    )

        existing.update({
            "name": clean_name,
            "category": "tournament",
            "registration_mode": "team",
            "registration_price": price,
            "prize": (
                prize_amount
                if prize_amount is not None
                else int(existing.get("prize") or 0)
            ),
            "capacity": maximum,
            "registration_open": True,
            "active": True,
            "payment_alias": str(payment_alias).strip() if payment_alias else None,
            "date": date_iso,
            "updated_at": timestamp,
        })
        _atomic_json_write(events_path, {"version": 1, "events": events, "updated_at": timestamp})

    csv_path = _init_business_event_csv(existing)
    return {"ok": True, "created": created, "event": dict(existing), "csv_path": str(csv_path)}


def list_business_events(*, active_only: bool = True) -> List[Dict[str, Any]]:
    events = read_business_events()
    if active_only:
        events = [event for event in events if event.get("active") and event.get("registration_open")]
    return sorted(events, key=lambda event: (str(event.get("date") or ""), str(event.get("name") or "")))


def get_business_event(
    *, event_id: Any = None, name: Any = None, event_date: Any = None,
    active_only: bool = True,
) -> Optional[Dict[str, Any]]:
    events = list_business_events(active_only=active_only)
    if event_id:
        return next((event for event in events if event.get("event_id") == str(event_id)), None)
    normalized_name = _normalize_identity(name) if name else ""
    date_iso = normalize_event_date(event_date) if event_date else ""
    candidates = [
        event for event in events
        if (not normalized_name or _normalize_identity(event.get("name")) == normalized_name)
        and (not date_iso or event.get("date") == date_iso)
    ]
    return dict(candidates[0]) if len(candidates) == 1 else None


def resolve_business_events(*, name: Any = None, event_date: Any = None) -> List[Dict[str, Any]]:
    normalized_name = _normalize_identity(name) if name else ""
    date_iso = normalize_event_date(event_date) if event_date else ""
    return [
        event for event in list_business_events()
        if (not normalized_name or _normalize_identity(event.get("name")) == normalized_name)
        and (not date_iso or event.get("date") == date_iso)
    ]


def get_event_capacity_state(event: Dict[str, Any], *, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    csv_path = _event_csv_path(event)
    with _exclusive_file_lock(csv_path):
        rows = read_event_registrations(event)
        expired = _expire_rows(rows, _now(now))
        if expired:
            _atomic_csv_write(csv_path, rows)
        return {**_capacity_from_rows(event, rows), "expired_now": expired}


def _row_amount(row: Dict[str, Any], key: str) -> int:
    try:
        return int(float(row.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def create_event_registration_hold(
    event: Dict[str, Any],
    team_name: Any,
    contact_name: Any,
    phone: Any,
    *,
    now: Optional[dt.datetime] = None,
    hold_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    if not event or not event.get("event_id"):
        raise EventRegistrationError("event_not_found", "No existe el torneo indicado.")
    if not event.get("active") or not event.get("registration_open"):
        raise EventRegistrationError("event_closed", "Las inscripciones no estan abiertas.")
    clean_team = re.sub(r"\s+", " ", str(team_name or "")).strip()
    if not clean_team:
        raise EventRegistrationError("missing_team_name", "Falta el nombre del equipo.")
    clean_phone = str(phone or "").strip()
    if not clean_phone:
        raise EventRegistrationError("missing_contact_phone", "No hay telefono real del contacto.")

    current = _now(now)
    csv_path = _event_csv_path(event)
    with _exclusive_file_lock(csv_path):
        rows = read_event_registrations(event)
        _expire_rows(rows, current)
        normalized_team = _normalize_identity(clean_team)
        existing = next(
            (
                row for row in rows
                if _normalize_identity(row.get("team_name")) == normalized_team
                and row.get("status") in {"pending_payment", "confirmed"}
            ),
            None,
        )
        if existing:
            _atomic_csv_write(csv_path, rows)
            return {
                "ok": True,
                "idempotent": True,
                "registration": dict(existing),
                "event": dict(event),
                "capacity_state": _capacity_from_rows(event, rows),
            }

        state = _capacity_from_rows(event, rows)
        if state["is_full"]:
            _atomic_csv_write(csv_path, rows)
            return {
                "ok": False,
                "reason": "event_full",
                "is_full": True,
                "event": dict(event),
                "capacity_state": state,
            }

        minutes = max(1, int(hold_minutes or EVENT_REGISTRATION_HOLD_MINUTES))
        stamp = current.isoformat()
        expires = (current + dt.timedelta(minutes=minutes)).isoformat()
        price = _money(event.get("registration_price"), "registration_price")
        row = {key: "" for key in EVENT_REGISTRATION_FIELDS}
        row.update({
            "registration_id": f"reg_{uuid.uuid4().hex[:12]}",
            "event_id": event.get("event_id"),
            "event_name": event.get("name"),
            "event_date": event.get("date"),
            "team_name": clean_team,
            "contact_name": re.sub(r"\s+", " ", str(contact_name or "")).strip(),
            "phone": clean_phone,
            "status": "pending_payment",
            "registration_price": price,
            "required_payment": price,
            "paid_amount": 0,
            "remaining_amount": price,
            "payment_status": "pending",
            "created_at": stamp,
            "hold_started_at": stamp,
            "hold_expires_at": expires,
            "updated_at": stamp,
        })
        rows.append(row)
        post_state = _capacity_from_rows(event, rows)
        if post_state["occupied"] > post_state["capacity"]:
            raise EventRegistrationError("capacity_invariant_broken", "La capacidad maxima fue excedida.")
        _atomic_csv_write(csv_path, rows)
        return {
            "ok": True,
            "idempotent": False,
            "registration": dict(row),
            "event": dict(event),
            "capacity_state": post_state,
        }


def get_event_registration(
    *, registration_id: Any = None, phone: Any = None,
    statuses: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, Any]]:
    candidates = list_event_registrations_for_phone(phone, statuses=statuses) if phone else []
    if registration_id:
        target = str(registration_id)
        for event in read_business_events():
            for row in read_event_registrations(event):
                if row.get("registration_id") == target:
                    return {"event": event, "registration": row}
        return None
    return candidates[0] if len(candidates) == 1 else None


def list_event_registrations_for_phone(
    phone: Any,
    *, statuses: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    target = re.sub(r"\D", "", str(phone or ""))
    allowed = set(statuses or [])
    results = []
    if not target:
        return results
    for event in read_business_events():
        for row in read_event_registrations(event):
            row_phone = re.sub(r"\D", "", str(row.get("phone") or ""))
            if row_phone != target or (allowed and row.get("status") not in allowed):
                continue
            results.append({"event": event, "registration": row})
    results.sort(key=lambda item: str(item["registration"].get("updated_at") or ""), reverse=True)
    return results


def register_event_payment(
    event: Dict[str, Any],
    registration_id: Any,
    amount: Any,
    *, receipt_fingerprint: str = "",
    payment_method: str = "transfer",
    now: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    payment = _money(amount, "paid_amount")
    if payment <= 0:
        raise EventRegistrationError("invalid_paid_amount", "El pago debe ser mayor que cero.")
    target_id = str(registration_id or "").strip()
    current = _now(now)
    csv_path = _event_csv_path(event)
    with _exclusive_file_lock(csv_path):
        rows = read_event_registrations(event)
        _expire_rows(rows, current)
        target = next((row for row in rows if row.get("registration_id") == target_id), None)
        if target is None:
            raise EventRegistrationError("registration_not_found", "No existe la inscripcion indicada.")
        if target.get("status") == "cancelled":
            raise EventRegistrationError("registration_cancelled", "La inscripcion esta cancelada.")
        if target.get("status") == "confirmed":
            _atomic_csv_write(csv_path, rows)
            return {
                "ok": True,
                "idempotent": True,
                "payment_complete": True,
                "registration": dict(target),
                "event": dict(event),
                "capacity_state": _capacity_from_rows(event, rows),
            }

        if target.get("status") == "expired":
            state_without_target = _capacity_from_rows(event, rows)
            if state_without_target["available"] <= 0:
                _atomic_csv_write(csv_path, rows)
                return {
                    "ok": False,
                    "reason": "late_payment_event_full",
                    "requires_human_review": True,
                    "money_received": True,
                    "registration": dict(target),
                    "event": dict(event),
                    "capacity_state": state_without_target,
                }
            target["status"] = "pending_payment"
            target["expired_at"] = ""
            target["hold_started_at"] = current.isoformat()
            target["hold_expires_at"] = (
                current + dt.timedelta(minutes=EVENT_REGISTRATION_HOLD_MINUTES)
            ).isoformat()

        already_paid = _row_amount(target, "paid_amount")
        required = _row_amount(target, "required_payment") or _row_amount(target, "registration_price")
        accumulated = already_paid + payment
        remaining = max(0, required - accumulated)
        complete = accumulated >= required
        stamp = current.isoformat()
        target.update({
            "paid_amount": accumulated,
            "remaining_amount": remaining,
            "payment_status": "paid" if complete else "partial",
            "payment_method": payment_method,
            "receipt_fingerprint": receipt_fingerprint or target.get("receipt_fingerprint") or "",
            "last_payment_at": stamp,
            "updated_at": stamp,
        })
        if complete:
            target["status"] = "confirmed"
            target["confirmed_at"] = target.get("confirmed_at") or stamp
        state = _capacity_from_rows(event, rows)
        if state["occupied"] > state["capacity"]:
            raise EventRegistrationError("capacity_invariant_broken", "La capacidad maxima fue excedida.")
        _atomic_csv_write(csv_path, rows)
        return {
            "ok": True,
            "idempotent": False,
            "payment_complete": complete,
            "payment_partial": not complete,
            "payment_received": payment,
            "registration": dict(target),
            "event": dict(event),
            "capacity_state": state,
        }


def cancel_event_registration(
    event: Dict[str, Any], registration_id: Any, *, now: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    csv_path = _event_csv_path(event)
    with _exclusive_file_lock(csv_path):
        rows = read_event_registrations(event)
        _expire_rows(rows, _now(now))
        target = next((row for row in rows if row.get("registration_id") == str(registration_id)), None)
        if target is None:
            raise EventRegistrationError("registration_not_found", "No existe la inscripcion indicada.")
        if target.get("status") != "cancelled":
            stamp = _now(now).isoformat()
            target.update(status="cancelled", cancelled_at=stamp, updated_at=stamp)
        _atomic_csv_write(csv_path, rows)
        return {
            "ok": True,
            "registration": dict(target),
            "event": dict(event),
            "capacity_state": _capacity_from_rows(event, rows),
        }


def event_registration_hold_fingerprint(registration: Dict[str, Any]) -> str:
    material = "|".join(str(registration.get(key) or "") for key in (
        "registration_id", "hold_started_at", "hold_expires_at"
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:18]


def event_registration_confirmation_fingerprint(registration: Dict[str, Any]) -> str:
    material = "|".join(str(registration.get(key) or "") for key in (
        "registration_id", "confirmed_at", "paid_amount"
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:18]


def _format_money(value: Any) -> str:
    return "$" + f"{_row_amount({'v': value}, 'v'):,}".replace(",", ".")


def build_pending_event_registration_admin_alert(
    event: Dict[str, Any], registration: Dict[str, Any], capacity_state: Dict[str, Any],
) -> str:
    return (
        "⏳ *NUEVO EQUIPO — TORNEO PENDIENTE*\n\n"
        f"🏆 Torneo: {event.get('name')}\n"
        f"📅 Fecha: {format_event_date(event.get('date'))}\n"
        f"🆔 Evento: {event.get('event_id')}\n"
        f"⚽ Equipo: {registration.get('team_name')}\n\n"
        f"👤 Responsable: {registration.get('contact_name') or '-'}\n"
        f"📱 Teléfono: {registration.get('phone')}\n\n"
        f"🆔 Inscripción: {registration.get('registration_id')}\n\n"
        f"💰 Inscripción: {_format_money(registration.get('required_payment'))}\n"
        f"💵 Pagado: {_format_money(registration.get('paid_amount'))}\n"
        f"💸 Pendiente: {_format_money(registration.get('remaining_amount'))}\n\n"
        "⏳ Estado: Pendiente de comprobante\n"
        f"⏱️ El cupo vence en {EVENT_REGISTRATION_HOLD_MINUTES} minutos si no se valida el pago.\n\n"
        f"👥 Máximo de equipos: {capacity_state.get('capacity')}\n"
        f"✅ Confirmados: {capacity_state.get('confirmed')}\n"
        f"🔒 Holds activos: {capacity_state.get('active_holds')}\n"
        f"📊 Disponibles: {capacity_state.get('available')}"
    )


def build_confirmed_event_registration_admin_alert(
    event: Dict[str, Any], registration: Dict[str, Any], capacity_state: Dict[str, Any],
) -> str:
    return (
        "✅ *EQUIPO CONFIRMADO — TORNEO*\n\n"
        f"🏆 Torneo: {event.get('name')}\n"
        f"📅 Fecha: {format_event_date(event.get('date'))}\n"
        f"🆔 Evento: {event.get('event_id')}\n"
        f"⚽ Equipo: {registration.get('team_name')}\n\n"
        f"👤 Responsable: {registration.get('contact_name') or '-'}\n"
        f"📱 Teléfono: {registration.get('phone')}\n\n"
        f"🆔 Inscripción: {registration.get('registration_id')}\n\n"
        f"💰 Inscripción: {_format_money(registration.get('required_payment'))}\n"
        f"✅ Pagado: {_format_money(registration.get('paid_amount'))}\n"
        f"💸 Pendiente: {_format_money(registration.get('remaining_amount'))}\n\n"
        "🎟️ Estado: CONFIRMADO\n\n"
        f"👥 Máximo de equipos: {capacity_state.get('capacity')}\n"
        f"✅ Equipos confirmados: {capacity_state.get('confirmed')}\n"
        f"🔒 Holds activos: {capacity_state.get('active_holds')}\n"
        f"📊 Cupos disponibles: {capacity_state.get('available')}"
    )


def iter_alert_reconciliation_candidates() -> Iterable[Dict[str, Any]]:
    for event in list_business_events(active_only=False):
        state = get_event_capacity_state(event)
        for registration in read_event_registrations(event):
            status = registration.get("status")
            if status == "pending_payment":
                yield {
                    "category": "event_registration_pending",
                    "event": event,
                    "registration": registration,
                    "capacity_state": state,
                    "fingerprint": event_registration_hold_fingerprint(registration),
                }
            elif status == "confirmed":
                yield {
                    "category": "event_registration_confirmed",
                    "event": event,
                    "registration": registration,
                    "capacity_state": state,
                    "fingerprint": event_registration_confirmation_fingerprint(registration),
                }
