from __future__ import annotations

import datetime as dt
import csv
import json
import re
import uuid
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from cancheria.config import legacy_config as cfg
from cancheria.config.court_sports import sport_icon, sport_menu_options
from cancheria.domain.reservations.calendar import CalendarioLlamadas
from cancheria.domain.events import registration as event_registration
from cancheria.domain.finance.ledger import FinancialLedger, cents_to_pesos
from cancheria.infrastructure.persistence.json_store import JSONStore
from cancheria.legacy_bridge import legacy_callable


ACTIVE_STATES = {str(value).strip().lower() for value in cfg.ACTIVE_BOOKING_STATUSES}
NOTIFICATION_KEYS = (
    "bookings", "hours", "cash", "operation", "cases", "tournaments", "fixed_turns",
    "blacklist", "commands",
)


class DesktopAdminService:
    """Administrative facade shared by the desktop panel and WhatsApp core.

    Mutations that have side effects beyond the calendar CSV are delegated to
    the exact legacy admin functions used by WhatsApp.  Simple calendar actions
    use ``CalendarioLlamadas``, whose writes are locked and atomic.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.calendar = CalendarioLlamadas(str(self.runtime / "calendario_turnos.csv"))
        try:
            self.calendar.finalizar_turnos_vencidos()
        except OSError:
            # El contador aplica además un filtro defensivo; un bloqueo de E/S
            # transitorio no debe impedir que CANCHERIA o sus alertas inicien.
            pass
        self._notification_read_store = JSONStore(
            self.runtime / "admin_notification_read_state.json"
        )
        self._cash_store = JSONStore(self.runtime / "caja_movimientos.json")
        self._cash_closures_store = JSONStore(self.runtime / "caja_cierres.json")
        self.cash_ledger = FinancialLedger(self.runtime / "caja.db")
        self._migrate_v230_cash_json()

    def _migrate_v230_cash_json(self) -> None:
        """Preserve manual movements created by the first Caja implementation."""
        path = self.runtime / "caja_movimientos.json"
        if not path.is_file():
            return
        for row in self._cash_manual_rows():
            amount = int(row.get("amount") or 0)
            if not amount:
                continue
            self.cash_ledger.record(
                movement_type="manual_income" if amount > 0 else "expense",
                direction="income" if amount > 0 else "expense",
                amount=abs(amount),
                occurred_at=str(row.get("occurred_at") or ""),
                payment_method=str(row.get("method") or ""),
                concept=str(row.get("concept") or "Movimiento migrado"),
                client=str(row.get("client") or ""),
                court=str(row.get("court") or ""),
                origin="migration_v230",
                notes="Migrado desde caja_movimientos.json",
                idempotency_key=f"migration-v230:{row.get('movement_id')}",
            )

    def bookings(self) -> list[dict[str, Any]]:
        finalize = getattr(self.calendar, "finalizar_turnos_vencidos", None)
        if callable(finalize):
            try:
                finalize()
            except OSError:
                pass
        rows = self.calendar.asegurar_ids_reservas()
        return sorted(
            (dict(row) for row in rows),
            key=lambda row: (str(row.get("fecha") or ""), str(row.get("hora") or "")),
        )

    def stats(self) -> dict[str, int]:
        rows = self.bookings()
        active_rows = [
            row for row in rows
            if str(row.get("estado") or "").strip().lower() in ACTIVE_STATES
        ]
        logical: dict[str, list[dict[str, Any]]] = {}
        for index, row in enumerate(active_rows):
            identity = str(row.get("reservation_id") or "").strip() or "|".join(
                str(row.get(key) or "").strip()
                for key in ("telefono", "fecha", "hora", "cancha")
            ) or f"row:{index}"
            logical.setdefault(identity, []).append(row)
        has_ended = getattr(self.calendar, "logical_reservation_has_ended", None)
        if callable(has_ended):
            logical = {
                identity: group
                for identity, group in logical.items()
                if not has_ended(group)
            }
        active = [row for group in logical.values() for row in group]
        pending = [
            row for row in active
            if str(row.get("senia_estado") or "").strip().lower()
            in {"pendiente", "parcial", "parcial_efectivo_pendiente"}
        ]
        pending_reservations = {
            str(row.get("reservation_id") or "").strip()
            or "|".join(
                str(row.get(key) or "").strip()
                for key in ("telefono", "fecha", "cancha")
            )
            for row in pending
        }
        local_now = getattr(self.calendar, "local_now", None)
        today_date = local_now().date() if callable(local_now) else dt.date.today()
        today = today_date.strftime("%d/%m")
        today_count = sum(
            any(today in str(row.get("fecha") or "") for row in group)
            for group in logical.values()
        )
        return {
            "active": len(logical),
            "pending": len(pending_reservations),
            "today": today_count,
            "cases": len(self.human_cases()),
            "tournaments": self.pending_tournament_registrations(),
        }

    def booking_payment_status(self, row: dict[str, Any]) -> str:
        """Expose total payment distinctly without changing booking lifecycle state."""
        deposit_state = str(row.get("senia_estado") or "").strip()
        pending_raw = str(row.get("monto_pendiente") or "").strip()
        if (
            deposit_state.casefold() == "pagada"
            and pending_raw
            and self._cash_amount(pending_raw) == 0
        ):
            return "total pagado"
        return deposit_state

    def notification_counts(self, stats: dict[str, int] | None = None) -> dict[str, int]:
        """Return unresolved administrative work grouped by panel section."""
        current = stats or self.stats()
        bookings = max(0, int(current.get("pending", 0) or 0))
        cases = max(0, int(current.get("cases", 0) or 0))
        tournaments = max(0, int(current.get("tournaments", 0) or 0))
        return {
            "bookings": bookings,
            "hours": 0,
            "cash": 0,
            "operation": 0,
            "cases": cases,
            "tournaments": tournaments,
            "fixed_turns": 0,
            "blacklist": 0,
            "commands": 0,
            "total": bookings + cases + tournaments,
        }

    def unread_notification_counts(
        self, _stats: dict[str, int] | None = None
    ) -> dict[str, int]:
        """Return only unresolved items that the operator has not yet reviewed."""
        current = self._notification_items()
        read = self._read_notification_state()
        counts = {
            key: len(current.get(key, set()) - read.get(key, set()))
            for key in NOTIFICATION_KEYS
        }
        counts["total"] = sum(counts.values())
        return counts

    def mark_notifications_read(self, keys: list[str] | tuple[str, ...] | None = None) -> dict[str, int]:
        """Persist that the current items in ``keys`` were reviewed by the operator."""
        selected = set(keys or NOTIFICATION_KEYS) & set(NOTIFICATION_KEYS)
        current = self._notification_items()
        read = self._read_notification_state()
        for key in selected:
            read[key] = set(current.get(key, set()))
        payload = {
            "version": 1,
            "read": {key: sorted(read.get(key, set())) for key in NOTIFICATION_KEYS},
            "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        self._notification_store().write(payload)
        return self.unread_notification_counts()

    def _notification_store(self) -> JSONStore:
        store = getattr(self, "_notification_read_store", None)
        if store is None:
            store = JSONStore(self.runtime / "admin_notification_read_state.json")
            self._notification_read_store = store
        return store

    def _read_notification_state(self) -> dict[str, set[str]]:
        try:
            payload = self._notification_store().read(default={}) or {}
        except (OSError, ValueError, TypeError):
            payload = {}
        raw = payload.get("read", {}) if isinstance(payload, dict) else {}
        return {
            key: {str(value) for value in raw.get(key, [])}
            if isinstance(raw, dict) and isinstance(raw.get(key, []), list)
            else set()
            for key in NOTIFICATION_KEYS
        }

    def _notification_items(self) -> dict[str, set[str]]:
        """Build stable identities so reading one alert never hides a future item."""
        items = {key: set() for key in NOTIFICATION_KEYS}
        pending_states = {"pendiente", "parcial", "parcial_efectivo_pendiente"}
        for row in self.bookings():
            if str(row.get("estado") or "").strip().lower() not in ACTIVE_STATES:
                continue
            if str(row.get("senia_estado") or "").strip().lower() not in pending_states:
                continue
            identity = str(row.get("reservation_id") or "").strip() or "|".join(
                str(row.get(key) or "").strip()
                for key in ("telefono", "fecha", "cancha")
            )
            if identity:
                items["bookings"].add(identity)

        for index, row in enumerate(self.human_cases()):
            identity = str(row.get("case_id") or row.get("id") or "").strip()
            if not identity:
                identity = "|".join(
                    str(row.get(key) or "").strip()
                    for key in ("created_at", "telefono", "nombre", "reason")
                ) or f"case:{index}"
            items["cases"].add(identity)

        for event in event_registration.list_business_events(active_only=False):
            event_id = str(event.get("event_id") or event.get("id") or "event").strip()
            for index, row in enumerate(event_registration.read_event_registrations(event)):
                if str(row.get("status") or "").strip() != "pending_payment":
                    continue
                registration_id = str(
                    row.get("registration_id") or row.get("admin_id") or ""
                ).strip()
                if not registration_id:
                    registration_id = "|".join(
                        str(row.get(key) or "").strip()
                        for key in ("created_at", "phone", "team_name")
                    ) or str(index)
                items["tournaments"].add(f"{event_id}:{registration_id}")
        return items

    @staticmethod
    def _cash_amount(value: Any) -> int:
        """Parse persisted money without ever inventing or rounding a value."""
        text = str(value or "").strip().replace("$", "").replace(" ", "")
        if not text:
            return 0
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")
        elif "." in text:
            groups = text.split(".")
            if len(groups) > 1 and all(len(group) == 3 for group in groups[1:]):
                text = "".join(groups)
        try:
            return max(0, int(float(text)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _cash_datetime(value: Any, fallback: dt.datetime | None = None) -> dt.datetime:
        text = str(value or "").strip()
        if text:
            try:
                return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                pass
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m"):
                try:
                    parsed = dt.datetime.strptime(text, fmt)
                    if fmt == "%d/%m":
                        parsed = parsed.replace(year=dt.date.today().year)
                    return parsed
                except ValueError:
                    continue
        return fallback or dt.datetime.now()

    @staticmethod
    def _cash_method(value: Any) -> str:
        text = str(value or "").strip().casefold()
        if "efectivo" in text:
            return "Efectivo" if "transfer" not in text else "Mixto"
        if "transfer" in text or "comprobante" in text:
            return "Transferencia"
        return "Otros"

    def _cash_manual_rows(self) -> list[dict[str, Any]]:
        try:
            payload = self._cash_store.read(default={}) or {}
        except (OSError, ValueError, TypeError):
            payload = {}
        rows = payload.get("movements", []) if isinstance(payload, dict) else []
        return [dict(row) for row in rows if isinstance(row, dict)]

    def _cash_write_manual_rows(self, rows: list[dict[str, Any]]) -> None:
        self._cash_store.write({
            "version": 1,
            "movements": rows,
            "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        })

    def add_cash_movement(
        self,
        *,
        kind: str,
        occurred_at: str,
        concept: str,
        amount: Any,
        method: str,
        client: str = "",
        court: str = "",
        related_id: str = "",
        notes: str = "",
        category: str = "",
        responsible: str = "Administrador",
        allow_duplicate: bool = False,
    ) -> dict[str, Any]:
        kind = str(kind or "").strip().casefold()
        if kind not in {"income", "expense"}:
            raise ValueError("El movimiento debe ser un ingreso o un gasto.")
        parsed_amount = self._cash_amount(amount)
        if parsed_amount <= 0:
            raise ValueError("Ingresá un importe mayor que cero.")
        concept = str(concept or "").strip()
        if not concept:
            raise ValueError("Ingresá el concepto del movimiento.")
        moment = self._cash_datetime(occurred_at)
        if not allow_duplicate and self.cash_ledger.has_manual_duplicate(
            occurred_at=moment.isoformat(timespec="seconds"),
            direction=kind,
            amount=parsed_amount,
            payment_method=method,
            concept=concept,
        ):
            raise ValueError(
                "POSSIBLE_DUPLICATE: Ya existe un movimiento manual igual en esa fecha."
            )
        related = str(related_id or "").strip()
        return self.cash_ledger.record(
            movement_type=("manual_income" if kind == "income" else (category or "expense")),
            direction=kind,
            amount=parsed_amount,
            occurred_at=moment.isoformat(timespec="seconds"),
            payment_method=method,
            concept=concept,
            client=client,
            reservation_id=related,
            court=court,
            origin="manual",
            responsible=responsible,
            notes=notes,
        )

    def _all_booking_rows_for_cash(self) -> list[dict[str, Any]]:
        rows = [dict(row) for row in self.bookings()]
        finished = self.runtime / "turnos_terminados.csv"
        if finished.is_file():
            try:
                with finished.open("r", encoding="utf-8-sig", newline="") as handle:
                    rows.extend(dict(row) for row in csv.DictReader(handle))
            except OSError:
                pass
        return rows

    def _booking_cash_movements(self) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for index, row in enumerate(self._all_booking_rows_for_cash()):
            reservation_id = str(row.get("reservation_id") or "").strip()
            identity = reservation_id or "|".join(
                str(row.get(key) or "").strip()
                for key in ("telefono", "fecha", "cancha", "reservado_en")
            ) or f"booking:{index}"
            grouped.setdefault(identity, []).append(row)

        movements: list[dict[str, Any]] = []
        for identity, rows in grouped.items():
            row = sorted(rows, key=lambda item: str(item.get("hora") or ""))[0]
            paid = max(self._cash_amount(item.get("senia_pagada_monto")) for item in rows)
            deposit_state = str(row.get("senia_estado") or "").strip().casefold()
            if paid <= 0 and deposit_state in {"pagada", "pago_total", "total_pagado"}:
                paid = max(self._cash_amount(item.get("senia_monto")) for item in rows)
            total = max(self._cash_amount(item.get("precio_total")) for item in rows)
            pending = max(self._cash_amount(item.get("monto_pendiente")) for item in rows)
            if total > 0 and pending == 0 and deposit_state in {"pagada_total", "pago_total", "total_pagado"}:
                paid = max(paid, total)
            if paid <= 0:
                continue
            booking_day = self._parse_booking_date(row.get("fecha"), dt.date.today().year)
            fallback = (
                dt.datetime.combine(booking_day, dt.time(12, 0))
                if booking_day is not None else dt.datetime.now()
            )
            moment = self._cash_datetime(
                row.get("last_payment_at") or row.get("reservado_en"), fallback
            )
            movements.append({
                "movement_id": f"booking:{identity}",
                "source": "booking",
                "source_id": identity,
                "kind": "income",
                "occurred_at": moment.isoformat(timespec="seconds"),
                "concept": f"Pago reserva · {row.get('tipo_turno') or row.get('cancha') or 'Cancha'}",
                "client": str(row.get("nombre") or row.get("telefono") or "").strip(),
                "method": self._cash_method(row.get("payment_method")),
                "amount": paid,
                "court": str(row.get("cancha") or "").strip(),
                "status": "Completado",
            })
        return movements

    def _tournament_cash_movements(self) -> list[dict[str, Any]]:
        movements: list[dict[str, Any]] = []
        for event in event_registration.list_business_events(active_only=False):
            for row in event_registration.read_event_registrations(event):
                paid = self._cash_amount(row.get("paid_amount"))
                if paid <= 0:
                    continue
                identity = str(row.get("registration_id") or "").strip()
                moment = self._cash_datetime(
                    row.get("last_payment_at") or row.get("confirmed_at") or row.get("created_at")
                )
                movements.append({
                    "movement_id": f"tournament:{identity}",
                    "source": "tournament",
                    "source_id": identity,
                    "kind": "income",
                    "occurred_at": moment.isoformat(timespec="seconds"),
                    "concept": f"Inscripción torneo · {event.get('name') or row.get('event_name') or ''}",
                    "client": str(row.get("team_name") or row.get("contact_name") or "").strip(),
                    "method": self._cash_method(row.get("payment_method")),
                    "amount": paid,
                    "court": "Torneos",
                    "status": "Completado",
                })
        return movements

    def _cash_pending_and_future(self) -> tuple[int, int]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for index, row in enumerate(self.bookings()):
            if str(row.get("estado") or "").strip().casefold() not in ACTIVE_STATES:
                continue
            identity = str(row.get("reservation_id") or "").strip() or f"row:{index}"
            grouped.setdefault(identity, []).append(row)
        pending_total = 0
        future_total = 0
        now = dt.datetime.now()
        today = now.date()
        for rows in grouped.values():
            row = rows[0]
            pending_total += max(self._cash_amount(item.get("monto_pendiente")) for item in rows)
            booking_date = self._parse_booking_date(row.get("fecha"), today.year)
            time_match = re.search(r"(\d{1,2}):(\d{2})", str(row.get("hora") or ""))
            booking_moment = None
            if booking_date is not None:
                hour = int(time_match.group(1)) if time_match else 23
                minute = int(time_match.group(2)) if time_match else 59
                booking_moment = dt.datetime.combine(booking_date, dt.time(hour, minute))
            state = str(row.get("estado") or "").strip().casefold()
            if booking_moment is not None and booking_moment > now and state in {"reservado", "confirmado"}:
                future_total += max(self._cash_amount(item.get("precio_total")) for item in rows)
        for event in event_registration.list_business_events(active_only=False):
            for row in event_registration.read_event_registrations(event):
                if str(row.get("status") or "") not in {"pending_payment", "confirmed"}:
                    continue
                pending_total += self._cash_amount(row.get("remaining_amount"))
                try:
                    event_date = dt.date.fromisoformat(str(event.get("date") or ""))
                except ValueError:
                    event_date = None
                if event_date is not None and event_date >= today and str(row.get("status")) == "confirmed":
                    future_total += self._cash_amount(row.get("required_payment"))
        return pending_total, future_total

    @staticmethod
    def _parse_booking_date(value: Any, default_year: int) -> dt.date | None:
        text = str(value or "").strip()
        try:
            return dt.date.fromisoformat(text)
        except ValueError:
            pass
        match = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", text)
        if not match:
            return None
        try:
            return dt.date(
                int(match.group(3) or default_year), int(match.group(2)), int(match.group(1))
            )
        except ValueError:
            return None

    def cash_snapshot(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        method: str = "Todos",
    ) -> dict[str, Any]:
        today = dt.date.today()
        start = dt.date.fromisoformat(start_date) if start_date else today.replace(day=1)
        end = dt.date.fromisoformat(end_date) if end_date else today
        if end < start:
            raise ValueError("La fecha Hasta no puede ser anterior a Desde.")
        ledger_rows = self.cash_ledger.list_movements(
            start_date=start.isoformat(), end_date=end.isoformat(), payment_method=method
        )
        filtered = []
        for row in ledger_rows:
            signed = cents_to_pesos(row.get("amount_cents"))
            if row.get("direction") == "expense":
                signed = -signed
            filtered.append({
                **row,
                "source": row.get("origin", ""),
                "source_id": row.get("reservation_id") or row.get("registration_id") or "",
                "kind": row.get("direction", ""),
                "method": row.get("payment_method", ""),
                "amount": signed,
                "status": "Completado" if row.get("status") == "confirmed" else row.get("status", ""),
            })
        month_start = today.replace(day=1)
        next_month = (month_start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        income_today = self.cash_ledger.total_income(today.isoformat(), today.isoformat())
        income_month = self.cash_ledger.total_income(
            month_start.isoformat(), (next_month - dt.timedelta(days=1)).isoformat()
        )
        pending, future = self._cash_pending_and_future()
        visible_days = min(366, (end - start).days + 1)
        daily_start = end - dt.timedelta(days=visible_days - 1)
        daily: dict[str, int] = {
            (daily_start + dt.timedelta(days=offset)).isoformat(): 0
            for offset in range(visible_days)
        }
        methods: dict[str, int] = {
            "Efectivo": 0, "Transferencia": 0, "Mixto": 0, "Otros": 0,
        }
        catalog = {
            str(item.get("name") or ""): (
                f"{item.get('name')} · {item.get('type')}"
                if str(item.get("type") or "").strip() else str(item.get("name") or "")
            )
            for item in self.court_catalog()
        }
        courts: dict[str, int] = {label: 0 for label in catalog.values() if label}
        for row in filtered:
            amount = int(row.get("amount") or 0)
            if amount <= 0:
                continue
            day = self._cash_datetime(row.get("occurred_at")).date().isoformat()
            daily[day] = daily.get(day, 0) + amount
            method_name = str(row.get("method") or "Otros")
            methods[method_name] = methods.get(method_name, 0) + amount
            raw_court = str(row.get("court") or "Otros")
            court = catalog.get(raw_court, raw_court)
            courts[court] = courts.get(court, 0) + amount
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "income_today": income_today,
            "income_month": income_month,
            "pending_balances": pending,
            "future_reservations": future,
            "period_balance": sum(int(row.get("amount") or 0) for row in filtered),
            "movements": filtered,
            "daily_income": daily,
            "method_income": methods,
            "court_income": courts,
            "history_notice": (
                "Los ingresos se registran con fecha real desde CANCHERIA v0.2.31; "
                "no se inventan cobros históricos sin evidencia."
            ),
        }

    def cash_close_preview(self, day: str) -> dict[str, int]:
        target = dt.date.fromisoformat(str(day or "").strip()).isoformat()
        rows = self.cash_ledger.list_movements(start_date=target, end_date=target)
        income = sum(
            cents_to_pesos(row.get("amount_cents"))
            for row in rows if row.get("direction") == "income"
        )
        expenses = sum(
            cents_to_pesos(row.get("amount_cents"))
            for row in rows if row.get("direction") == "expense"
        )
        cash_expected = sum(
            cents_to_pesos(row.get("amount_cents"))
            * (1 if row.get("direction") == "income" else -1)
            for row in rows if row.get("payment_method") == "Efectivo"
        )
        return {
            "income": income,
            "expenses": expenses,
            "net": income - expenses,
            "cash_expected": cash_expected,
            "movement_count": len(rows),
        }

    def close_cash(
        self,
        day: str,
        *,
        cash_counted: Any = 0,
        responsible: str = "Administrador",
        notes: str = "",
    ) -> dict[str, Any]:
        target = dt.date.fromisoformat(str(day or "").strip())
        closure = self.cash_ledger.close_day(
            target.isoformat(), cash_counted=cash_counted,
            responsible=responsible, notes=notes,
        )
        return {
            **closure,
            "balance": cents_to_pesos(closure.get("net_cents")),
            "income": cents_to_pesos(closure.get("income_cents")),
            "expenses": cents_to_pesos(closure.get("expense_cents")),
            "cash_expected": cents_to_pesos(closure.get("cash_expected_cents")),
            "cash_counted": cents_to_pesos(closure.get("cash_counted_cents")),
            "difference": cents_to_pesos(closure.get("difference_cents")),
        }

    def export_cash_csv(
        self,
        destination: str | Path,
        *,
        start_date: str,
        end_date: str,
        method: str = "Todos",
    ) -> int:
        return self.cash_ledger.export_csv(
            destination, start_date=start_date, end_date=end_date,
            payment_method=method,
        )

    def command_reference(self) -> str:
        """Use the exact help catalog exposed by the WhatsApp admin command."""
        return str(legacy_callable("build_mensaje_ayuda_admin")("todos") or "")

    def blacklist_entries(self) -> list[dict[str, str]]:
        """Return the same normalized blacklist used by the WhatsApp agent."""
        load_blacklist = legacy_callable("cargar_blacklist")
        blacklist_label = legacy_callable("_blacklist_label")
        result: list[dict[str, str]] = []
        for raw_entry in load_blacklist() or []:
            entry = str(raw_entry or "").strip()
            if not entry:
                continue
            result.append({
                "entry": entry,
                "kind": "Teléfono" if entry.startswith("phone:") else "Nombre",
                "label": str(blacklist_label(entry) or entry),
            })
        return sorted(result, key=lambda item: item["label"].casefold())

    def block_blacklist(self, target: str) -> str:
        """Block a phone/name through the exact WhatsApp administration helper."""
        target = str(target or "").strip()
        if not target:
            raise ValueError("Ingresá un número de teléfono o nombre de contacto.")
        if not legacy_callable("bloquear_numero")(target):
            raise ValueError(
                "No pude bloquear ese contacto. Verificá el número o nombre; "
                "un administrador autorizado no puede incluirse en la blacklist."
            )
        normalized = legacy_callable("_blacklist_entry_from_target")(target)
        label = legacy_callable("_blacklist_label")(normalized)
        return f"{label} fue agregado a la blacklist. El agente no le responderá."

    def unblock_blacklist(self, target: str) -> str:
        """Unblock a phone/name through the exact WhatsApp administration helper."""
        target = str(target or "").strip()
        if not target:
            raise ValueError("Ingresá o seleccioná un contacto bloqueado.")
        if not legacy_callable("desbloquear_numero")(target):
            raise ValueError("No encontré ese número o nombre en la blacklist.")
        normalized = legacy_callable("_blacklist_entry_from_target")(target)
        label = legacy_callable("_blacklist_label")(normalized)
        return f"{label} fue eliminado de la blacklist."

    @staticmethod
    def _next_fixed_occurrence(weekday: int, time: str) -> dt.date:
        now = dt.datetime.now()
        day = now.date() + dt.timedelta(days=(int(weekday) - now.date().weekday()) % 7)
        try:
            slot_time = dt.time.fromisoformat(str(time or "").strip())
        except ValueError:
            slot_time = dt.time.max
        if day == now.date() and dt.datetime.combine(day, slot_time) <= now:
            day += dt.timedelta(days=7)
        return day

    def fixed_turns(self) -> list[dict[str, Any]]:
        """List active weekly turns stored in the shared client memory."""
        path = self.runtime / "client_memory.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        active_bookings = [
            dict(row)
            for row in self.calendar.asegurar_ids_reservas()
            if str(row.get("estado") or "").strip().lower() in ACTIVE_STATES
        ]
        day_names = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
        result: list[dict[str, Any]] = []
        for client_key, raw_memory in payload.items():
            memory = raw_memory if isinstance(raw_memory, dict) else {}
            fixed = memory.get("turno_fijo") or {}
            if not isinstance(fixed, dict) or not fixed.get("activo"):
                continue
            try:
                weekday = int(fixed.get("dia_semana"))
            except (TypeError, ValueError):
                continue
            if weekday not in range(7):
                continue
            time = self._minutes_to_time(self._time_to_minutes(str(fixed.get("hora") or "")))
            court = str(fixed.get("cancha") or "").strip()
            name = str(memory.get("nombre") or "").strip()
            phone = str(memory.get("telefono") or "").strip()
            next_day = self._next_fixed_occurrence(weekday, time)
            slot_rows = [
                row for row in active_bookings
                if self._row_matches_date(row, next_day)
                and str(row.get("hora") or "").strip() == time
                and str(row.get("cancha") or "").strip().casefold() == court.casefold()
            ]
            same_client = any(
                (phone and str(row.get("telefono") or "").strip() == phone)
                or (name and str(row.get("nombre") or "").strip().casefold() == name.casefold())
                for row in slot_rows
            )
            calendar_status = (
                "En agenda" if same_client else "Horario ocupado" if slot_rows else "Pendiente de generar"
            )
            result.append({
                "client_key": str(client_key),
                "name": name or str(client_key).removeprefix("NOMBRE:"),
                "phone": phone,
                "weekday": weekday,
                "day_name": day_names[weekday],
                "time": time,
                "court": court,
                "next_date": next_day.isoformat(),
                "calendar_status": calendar_status,
            })
        return sorted(
            result,
            key=lambda item: (int(item["weekday"]), str(item["time"]), str(item["court"])),
        )

    def create_fixed_turn(
        self,
        *,
        name: str,
        phone: str,
        weekday: int,
        time: str,
        court: str,
    ) -> str:
        name = str(name or "").strip()
        phone = str(phone or "").strip()
        court = str(court or "").strip()
        if not name and not phone:
            raise ValueError("Ingresá el nombre o teléfono del cliente.")
        try:
            weekday = int(weekday)
        except (TypeError, ValueError) as exc:
            raise ValueError("Seleccioná un día de la semana válido.") from exc
        if weekday not in range(7):
            raise ValueError("Seleccioná un día de la semana válido.")
        normalized_time = self._minutes_to_time(self._time_to_minutes(time))
        if court not in self.courts():
            raise ValueError("Seleccioná una cancha válida.")

        command = {
            "accion": "agregar_turno_fijo",
            "nombre": name,
            "telefono": phone,
            "dia_semana": weekday,
            "hora": normalized_time,
            "cancha": court,
        }
        result = legacy_callable("actualizar_turno_fijo_cliente")(command)
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo crear el turno fijo."))

        next_day = self._next_fixed_occurrence(weekday, normalized_time)
        identity = phone or f"NOMBRE:{name}"
        existing_slot = [
            dict(row)
            for row in self.calendar.asegurar_ids_reservas()
            if str(row.get("estado") or "").strip().lower() in ACTIVE_STATES
            and self._row_matches_date(row, next_day)
            and str(row.get("hora") or "").strip() == normalized_time
            and str(row.get("cancha") or "").strip().casefold() == court.casefold()
        ]
        same_client_exists = any(
            (phone and str(row.get("telefono") or "").strip() == phone)
            or (name and str(row.get("nombre") or "").strip().casefold() == name.casefold())
            for row in existing_slot
        )
        created_now = False
        if same_client_exists:
            booked, detail = True, (next_day.strftime("%d/%m/%Y"), normalized_time)
        elif existing_slot:
            booked, detail = False, ("", "")
        else:
            booking_result = legacy_callable("reservar_turno_en_calendario")(
                identity,
                {
                    "nombre": name or identity.removeprefix("NOMBRE:"),
                    "negocio": name or identity.removeprefix("NOMBRE:"),
                    "telefono": identity,
                    "website": "Turno fijo semanal",
                    "whatsapp_link": "",
                    "es_cliente": "si",
                },
                next_day.strftime("%d/%m/%Y"),
                normalized_time,
                cancha=court,
                estado_reserva=cfg.BOOKING_STATUS_PENDING,
                senia_estado="pendiente",
                senia_monto="",
                duracion_horas=getattr(cfg, "DEFAULT_TURN_DURATION_HOURS", 1.0),
            )
            booked = bool(booking_result.get("ok"))
            detail = (
                str(booking_result.get("dia") or ""),
                str(booking_result.get("hora") or normalized_time),
            )
            created_now = booked
        response = self._result_message(result, "Turno fijo creado.")
        if booked:
            client_key = legacy_callable("_telefono_memoria_turno_fijo")(command)
            load_memory = legacy_callable("cargar_memoria_cliente")
            save_memory = legacy_callable("guardar_memoria_cliente")
            memory = load_memory(client_key)
            fixed = dict(memory.get("turno_fijo") or {})
            fixed["ultima_reserva_fecha"] = next_day.isoformat()
            fixed["ultima_generacion"] = dt.datetime.now().isoformat(timespec="seconds")
            memory["turno_fijo"] = fixed
            save_memory(client_key, memory)
            agenda_message = (
                "El próximo turno fue agregado a Horas"
                if created_now
                else "El próximo turno ya estaba en Horas"
            )
            return (
                response
                + f"\n{agenda_message}: "
                + f"{next_day.strftime('%d/%m/%Y')} a las {detail[1] or normalized_time} en {court}."
            )

        return (
            response
            + f"\nEl turno fijo quedó guardado, pero el {next_day.strftime('%d/%m/%Y')} "
            + f"a las {normalized_time} en {court} no pudo agregarse a Horas porque no está disponible."
        )

    def remove_fixed_turn(self, *, client_key: str, name: str = "", phone: str = "") -> str:
        client_key = str(client_key or "").strip()
        name = str(name or "").strip()
        phone = str(phone or "").strip()
        if not client_key and not name and not phone:
            raise ValueError("Seleccioná un turno fijo de la tabla.")
        command = {
            "accion": "quitar_turno_fijo",
            "telefono": phone if phone and not phone.startswith("NOMBRE:") else "",
            "nombre": name or client_key.removeprefix("NOMBRE:"),
        }
        result = legacy_callable("actualizar_turno_fijo_cliente")(command)
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo quitar el turno fijo."))
        return (
            self._result_message(result, "Turno fijo eliminado.")
            + "\nLa próxima reserva que ya estaba generada se conserva en Horas."
        )

    def tournaments(self) -> list[dict[str, Any]]:
        result = []
        for event in event_registration.list_business_events(active_only=False):
            row = dict(event)
            state = event_registration.get_event_capacity_state(row)
            row.update(state)
            result.append(row)
        return result

    def pending_tournament_registrations(self) -> int:
        total = 0
        for event in event_registration.list_business_events(active_only=False):
            event_registration.get_event_capacity_state(event)
            total += sum(
                1 for row in event_registration.read_event_registrations(event)
                if str(row.get("status") or "") == "pending_payment"
            )
        return total

    def create_tournament(
        self,
        *,
        name: str,
        date: str,
        price: str,
        prize: str,
        capacity: str,
        payment_alias: str = "",
    ) -> str:
        result = event_registration.configure_business_event(
            name,
            price,
            capacity,
            date,
            prize=prize,
            payment_alias=payment_alias or None,
        )
        event = result["event"]
        return (
            f"Torneo {event.get('name')} creado para el "
            f"{event_registration.format_event_date(event.get('date'))}."
        )

    def update_tournament(
        self,
        event_id: str,
        *,
        name: str,
        date: str,
        price: str,
        prize: str,
        capacity: str,
    ) -> str:
        result = legacy_callable("editar_torneo_admin")({
            "torneo_event_id": str(event_id),
            "nuevo_nombre_torneo": name,
            "fecha_torneo": date,
            "precio_monto": price,
            "premio_monto": prize,
            "cantidad_maxima_equipos": capacity,
        })
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo editar el torneo."))
        return self._result_message(result, "Torneo actualizado.")

    def delete_tournament(self, event_id: str) -> str:
        result = legacy_callable("borrar_torneo_admin")({
            "torneo_event_id": str(event_id),
        })
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo borrar el torneo."))
        return self._result_message(result, "Torneo borrado.")

    @staticmethod
    def _event(event_id: str) -> dict[str, Any]:
        event = event_registration.get_business_event(
            event_id=str(event_id), active_only=False
        )
        if not event:
            raise ValueError("El torneo ya no existe. Actualizá la lista.")
        return dict(event)

    def tournament_registrations(self, event_id: str) -> list[dict[str, Any]]:
        event = self._event(event_id)
        event_registration.get_event_capacity_state(event)
        rows = event_registration.read_event_registrations(event)
        public_id = legacy_callable("_event_registration_admin_public_id")
        result = []
        for raw in rows:
            row = dict(raw)
            row["display_id"] = (
                str(row.get("admin_id") or "").strip()
                or str(public_id(row.get("registration_id"), create=True) or "").strip()
                or str(row.get("registration_id") or "")
            )
            result.append(row)
        return sorted(result, key=lambda row: str(row.get("created_at") or ""), reverse=True)

    def create_tournament_registration(
        self,
        event_id: str,
        *,
        team_name: str,
        contact_name: str,
        phone: str,
    ) -> str:
        event = self._event(event_id)
        result = event_registration.create_event_registration_hold(
            event,
            team_name,
            contact_name,
            phone,
        )
        if not result.get("ok"):
            raise RuntimeError("El torneo está completo y no admite otra inscripción.")
        row = result["registration"]
        display_id = legacy_callable("_event_registration_admin_public_id")(
            row.get("registration_id"), create=True
        )
        return f"Inscripción ID {display_id or row.get('registration_id')} creada para {row.get('team_name')}."

    def update_tournament_registration(
        self,
        event_id: str,
        registration_id: str,
        *,
        team_name: str,
        contact_name: str,
        phone: str,
    ) -> str:
        event = self._event(event_id)
        result = event_registration.update_event_registration_contact(
            event,
            registration_id,
            team_name=team_name,
            contact_name=contact_name,
            phone=phone,
        )
        row = result["registration"]
        return f"Datos de la inscripción de {row.get('team_name')} actualizados."

    def confirm_tournament_registration(self, registration_id: str, *, total: bool) -> str:
        result = legacy_callable("confirmar_pago_inscripcion_evento_admin")({
            "registration_id": str(registration_id),
            "pago_total": bool(total),
        })
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo confirmar la inscripción."))
        return self._result_message(result, "Pago de inscripción confirmado.")

    def cancel_tournament_registration(self, registration_id: str) -> str:
        result = legacy_callable("liberar_inscripcion_evento_admin")({
            "registration_id": str(registration_id),
        })
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo liberar la inscripción."))
        return self._result_message(result, "Inscripción liberada.")

    @staticmethod
    def _result_message(result: dict[str, Any], fallback: str) -> str:
        return str(result.get("respuesta") or result.get("motivo") or fallback)

    def confirm_payment(self, reservation_id: str, *, total: bool = False) -> str:
        result = legacy_callable("marcar_senia_pagada_admin")({
            "reservation_id": str(reservation_id),
            "id": str(reservation_id),
            "pago_total": bool(total),
            "deterministic": True,
        })
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo confirmar el pago."))
        row = dict(result.get("reserva") or {})
        paid = self._cash_amount(row.get("senia_pagada_monto"))
        total_amount = self._cash_amount(row.get("precio_total"))
        if paid > 0:
            self.cash_ledger.record_cumulative_payment(
                source_kind="booking",
                source_id=str(row.get("reservation_id") or reservation_id),
                total_paid=paid,
                movement_type=("full_payment" if total and paid >= total_amount else "deposit"),
                payment_method=str(row.get("payment_method") or "efectivo"),
                concept="Pago total de reserva" if total else "Seña de reserva",
                client=str(row.get("nombre") or row.get("telefono") or ""),
                court=str(row.get("cancha") or ""),
                responsible="Administrador",
            )
        return self._result_message(result, "Pago confirmado.")

    def cancel_booking(self, reservation_id: str, reason: str = "panel de administración") -> str:
        result = legacy_callable("cancelar_reserva_por_id_admin")({
            "reservation_id": str(reservation_id),
            "id": str(reservation_id),
            "motivo": reason,
            "deterministic": True,
        })
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo cancelar la reserva."))
        return self._result_message(result, "Reserva cancelada.")

    def release_booking(self, reservation_id: str) -> str:
        result = legacy_callable("liberar_reserva_por_id_admin")({
            "reservation_id": str(reservation_id),
            "id": str(reservation_id),
            "deterministic": True,
        })
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo liberar la reserva."))
        return self._result_message(result, "Reserva liberada.")

    def add_booking(
        self,
        *,
        day: str,
        time: str,
        court: str,
        name: str,
        phone: str,
    ) -> str:
        if not day.strip() or not time.strip() or not court.strip() or not name.strip():
            raise ValueError("Completá fecha, hora, cancha y nombre.")
        ok, detail = self.calendar.reservar(
            day.strip(),
            time.strip(),
            phone.strip() or f"ADMIN:MANUAL:{name.strip()}",
            nombre=name.strip(),
            cancha=court.strip(),
            estado=cfg.BOOKING_STATUS_RESERVED,
            senia_estado="no_requiere",
            extra_fields={
                "tipo_turno": getattr(cfg, "DEFAULT_TURN_TYPE", "futbol 5"),
                "duracion_minutos": str(getattr(cfg, "TURN_DURATION_MINUTES", 60)),
                "duracion_horas": str(getattr(cfg, "DEFAULT_TURN_DURATION_HOURS", 1.0)),
                "reservado_en": dt.datetime.now().isoformat(timespec="seconds"),
                "notas": "Reserva manual desde panel de administración",
            },
        )
        if not ok:
            suggestion = ""
            if isinstance(detail, (list, tuple)) and len(detail) >= 2 and any(detail):
                suggestion = f" Próximo disponible sugerido: {detail[0]} {detail[1]}."
            raise RuntimeError("El horario no está disponible o no es válido." + suggestion)
        return f"Reserva creada para {name.strip()} el {detail[0]} a las {detail[1]} en {court.strip()}."

    def block_day(self, day: str, court: str = "", reason: str = "Cerrado desde panel") -> str:
        result = self.calendar.bloquear_dia_completo(day.strip(), motivo=reason, cancha=court.strip() or None)
        if not result.get("ok"):
            raise RuntimeError(f"No se pudo bloquear: {result.get('motivo', 'dato inválido')}")
        return (
            f"{result.get('dia')}: {result.get('bloqueados', 0)} horarios bloqueados; "
            f"{result.get('ocupados', 0)} reservas existentes conservadas."
        )

    def unblock_day(self, day: str, court: str = "") -> str:
        result = self.calendar.desbloquear_dia_completo(day.strip(), cancha=court.strip() or None)
        if not result.get("ok"):
            raise RuntimeError(f"No se pudo desbloquear: {result.get('motivo', 'dato inválido')}")
        return f"{result.get('dia')}: {result.get('desbloqueados', 0)} bloqueos eliminados."

    def human_cases(self) -> list[dict[str, Any]]:
        path = self.runtime / "human_cases.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return []
        return [
            dict(item) for item in payload.get("cases", [])
            if isinstance(item, dict) and str(item.get("status") or "").lower() == "pending"
        ]

    def resolve_case(self, case_id: int) -> str:
        result = legacy_callable("resolver_caso_humano")(case_id, "PANEL_DESKTOP")
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo resolver el caso."))
        return self._result_message(result, "Caso resuelto y contacto reanudado.")

    def courts(self) -> list[str]:
        return [
            str(item.get("name") or "").strip()
            for item in (cfg.COURTS or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ] or [str(getattr(cfg, "DEFAULT_COURT_NAME", "Cancha 1"))]

    def court_catalog(self) -> list[dict[str, str]]:
        catalog: list[dict[str, str]] = []
        for item in cfg.COURTS or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("nombre") or "").strip()
            if not name:
                continue
            court_type = str(item.get("type") or item.get("tipo") or "").strip()
            catalog.append({
                "name": name,
                "type": court_type,
                "icon": sport_icon(court_type),
            })
        if catalog:
            return catalog
        name = str(getattr(cfg, "DEFAULT_COURT_NAME", "Cancha 1"))
        return [{"name": name, "type": "", "icon": "🏟️"}]

    @staticmethod
    def court_sport_options() -> list[dict[str, str]]:
        return sport_menu_options()

    def update_court_sport(self, court_name: str, court_type: str) -> str:
        court_name = str(court_name or "").strip()
        court_type = str(court_type or "").strip()
        if not court_name or not court_type:
            raise ValueError("Seleccioná una cancha y un deporte válidos.")
        courts = []
        found = False
        for item in cfg.COURTS or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("nombre") or "").strip()
            current_type = str(item.get("type") or item.get("tipo") or "").strip()
            if name == court_name:
                current_type = court_type
                found = True
            if name:
                courts.append({"name": name, "type": current_type})
        if not found:
            raise ValueError("La cancha seleccionada ya no existe en la configuración.")
        result = legacy_callable("actualizar_canchas_config")(courts)
        if not result.get("ok"):
            raise RuntimeError(self._result_message(result, "No se pudo cambiar el deporte."))
        return f"{sport_icon(court_type)} {court_name} ahora corresponde a {court_type}."

    @staticmethod
    def _parse_panel_date(value: str) -> dt.date:
        text = str(value or "").strip().lower()
        if text == "hoy":
            return dt.date.today()
        try:
            return dt.date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("Ingresá la fecha con formato AAAA-MM-DD.") from exc

    @staticmethod
    def _row_matches_date(row: dict[str, Any], day: dt.date) -> bool:
        text = str(row.get("fecha") or "")
        match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", text)
        if not match:
            return False
        row_day, row_month = int(match.group(1)), int(match.group(2))
        row_year = int(match.group(3)) if match.group(3) else day.year
        return (row_year, row_month, row_day) == (day.year, day.month, day.day)

    @staticmethod
    def _time_to_minutes(value: str) -> int:
        try:
            hour, minute = str(value or "").strip().split(":", 1)
            total = int(hour) * 60 + int(minute)
        except (TypeError, ValueError) as exc:
            raise ValueError("Ingresá la hora con formato HH:MM.") from exc
        if total < 0 or total >= 24 * 60 or not 0 <= int(minute) <= 59:
            raise ValueError("Ingresá una hora válida con formato HH:MM.")
        return total

    @staticmethod
    def _minutes_to_time(value: int) -> str:
        return f"{value // 60:02d}:{value % 60:02d}"

    def day_schedule(self, day: str) -> dict[str, Any]:
        """Build the admin hour grid from the same CSV/config used by WhatsApp."""
        selected = self._parse_panel_date(day)
        slot_minutes = max(1, int(getattr(cfg, "CALL_SLOT_DURATION_MINUTES", 60) or 60))
        slots: list[str] = []
        for start, end in cfg.obtener_franjas_atencion_minutos():
            current = start
            while current + slot_minutes <= end:
                value = self._minutes_to_time(current)
                if value not in slots:
                    slots.append(value)
                current += slot_minutes

        rows = self.calendar.asegurar_ids_reservas()
        active_rows: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            if str(row.get("estado") or "").strip().lower() not in ACTIVE_STATES:
                continue
            if not self._row_matches_date(row, selected):
                continue
            court = str(row.get("cancha") or getattr(cfg, "DEFAULT_COURT_NAME", "Cancha 1")).strip()
            time = str(row.get("hora") or "").strip()
            active_rows[(court, time)] = dict(row)

        attention_day = selected.weekday() in set(cfg.obtener_dias_atencion())
        now = dt.datetime.now()
        visible_slots = [
            time for time in slots
            if dt.datetime.combine(selected, dt.time.fromisoformat(time)) > now
        ]
        cells: list[dict[str, Any]] = []
        for time in visible_slots:
            slot_dt = dt.datetime.combine(selected, dt.time.fromisoformat(time))
            for court in self.courts():
                booking = active_rows.get((court, time))
                if booking:
                    blocked = (
                        str(booking.get("telefono") or "").startswith("ADMIN:CERRADO")
                        or str(booking.get("nombre") or "").strip().upper() == "CERRADO"
                    )
                    status = "blocked" if blocked else "occupied"
                elif not attention_day:
                    status = "closed"
                else:
                    status = "free"
                cells.append({
                    "day": selected.isoformat(),
                    "time": time,
                    "court": court,
                    "status": status,
                    "booking": booking,
                })

        return {
            "day": selected.isoformat(),
            "display_day": selected.strftime("%d/%m/%Y"),
            "attention_day": attention_day,
            "courts": self.courts(),
            "court_catalog": self.court_catalog(),
            "slots": visible_slots,
            "cells": cells,
        }

    def booking_details(self, reservation_id: str, day: str = "") -> dict[str, Any]:
        rows = self.calendar.asegurar_ids_reservas()
        matches = [
            dict(row) for row in rows
            if str(row.get("reservation_id") or "").strip() == str(reservation_id).strip()
            and str(row.get("estado") or "").strip().lower() in ACTIVE_STATES
        ]
        if not matches:
            raise ValueError("La reserva ya no está activa. Actualizá la grilla.")
        matches.sort(key=lambda row: str(row.get("hora") or ""))
        result = dict(matches[0])
        result["day"] = self._parse_panel_date(day).isoformat() if day else ""
        result["slot_count"] = len(matches)
        return result

    def update_booking(
        self,
        reservation_id: str,
        *,
        day: str,
        time: str,
        court: str,
        name: str,
        phone: str,
    ) -> str:
        selected = self._parse_panel_date(day)
        court = str(court or "").strip()
        name = str(name or "").strip()
        phone = str(phone or "").strip()
        if not court or court not in self.courts():
            raise ValueError("Seleccioná una cancha válida.")
        if not name:
            raise ValueError("Completá el nombre del cliente.")
        if selected < dt.date.today():
            raise ValueError("No se puede mover una reserva a una fecha pasada.")
        if selected.weekday() not in set(cfg.obtener_dias_atencion()):
            raise ValueError("La fecha elegida está fuera de los días de atención.")

        start_minutes = self._time_to_minutes(time)
        normalized_time = self._minutes_to_time(start_minutes)
        slot_minutes = max(1, int(getattr(cfg, "CALL_SLOT_DURATION_MINUTES", 60) or 60))
        lock = self.calendar.atomic() if hasattr(self.calendar, "atomic") else nullcontext()
        with lock:
            rows = self.calendar._leer_todos()
            target_indices = [
                index for index, row in enumerate(rows)
                if str(row.get("reservation_id") or "").strip() == str(reservation_id).strip()
                and str(row.get("estado") or "").strip().lower() in ACTIVE_STATES
            ]
            if not target_indices:
                raise ValueError("La reserva ya no está activa. Actualizá la grilla.")

            target_times = [start_minutes + offset * slot_minutes for offset in range(len(target_indices))]
            windows = cfg.obtener_franjas_atencion_minutos()
            if any(
                not any(window_start <= minute and minute + slot_minutes <= window_end for window_start, window_end in windows)
                for minute in target_times
            ):
                raise ValueError("La reserva completa debe quedar dentro del horario de atención.")
            if selected == dt.date.today() and dt.datetime.combine(
                selected, dt.time.fromisoformat(normalized_time)
            ) <= dt.datetime.now():
                raise ValueError("No se puede mover una reserva a un horario que ya pasó.")

            target_index_set = set(target_indices)
            target_time_values = {self._minutes_to_time(value) for value in target_times}
            for index, row in enumerate(rows):
                if index in target_index_set:
                    continue
                if str(row.get("estado") or "").strip().lower() not in ACTIVE_STATES:
                    continue
                if not self._row_matches_date(row, selected):
                    continue
                row_court = str(row.get("cancha") or getattr(cfg, "DEFAULT_COURT_NAME", "Cancha 1")).strip()
                if row_court == court and str(row.get("hora") or "").strip() in target_time_values:
                    raise ValueError("Uno de los horarios elegidos ya está ocupado en esa cancha.")

            day_names = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
            display_day = f"{day_names[selected.weekday()]} {selected.strftime('%d/%m')}"
            ordered_indices = sorted(target_indices, key=lambda index: str(rows[index].get("hora") or ""))
            for index, minute in zip(ordered_indices, target_times):
                rows[index]["fecha"] = display_day
                rows[index]["hora"] = self._minutes_to_time(minute)
                rows[index]["cancha"] = court
                rows[index]["nombre"] = name
                rows[index]["telefono"] = phone or f"ADMIN:MANUAL:{name}"
            self.calendar._escribir_todos(rows, ordenar=True)

        return f"Reserva ID {reservation_id} actualizada para el {selected.strftime('%d/%m/%Y')} a las {normalized_time} en {court}."

    def unblock_slot(self, day: str, time: str, court: str) -> str:
        selected = self._parse_panel_date(day)
        normalized_time = self._minutes_to_time(self._time_to_minutes(time))
        lock = self.calendar.atomic() if hasattr(self.calendar, "atomic") else nullcontext()
        with lock:
            rows = self.calendar._leer_todos()
            kept = []
            removed = 0
            for row in rows:
                is_block = (
                    str(row.get("telefono") or "").startswith("ADMIN:CERRADO")
                    or str(row.get("nombre") or "").strip().upper() == "CERRADO"
                )
                matches = (
                    is_block
                    and self._row_matches_date(row, selected)
                    and str(row.get("hora") or "").strip() == normalized_time
                    and str(row.get("cancha") or getattr(cfg, "DEFAULT_COURT_NAME", "Cancha 1")).strip() == court
                )
                if matches:
                    removed += 1
                else:
                    kept.append(row)
            if not removed:
                raise ValueError("Ese horario ya no está bloqueado. Actualizá la grilla.")
            self.calendar._escribir_todos(kept, ordenar=True)
        return f"Horario desbloqueado: {selected.strftime('%d/%m/%Y')} {normalized_time}, {court}."

