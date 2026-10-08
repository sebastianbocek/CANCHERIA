from __future__ import annotations

import datetime as dt
import json
import re
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from cancheria.config import legacy_config as cfg
from cancheria.domain.reservations.calendar import CalendarioLlamadas
from cancheria.domain.events import registration as event_registration
from cancheria.legacy_bridge import legacy_callable


ACTIVE_STATES = {str(value).strip().lower() for value in cfg.ACTIVE_BOOKING_STATUSES}


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

    def bookings(self) -> list[dict[str, Any]]:
        rows = self.calendar.asegurar_ids_reservas()
        return sorted(
            (dict(row) for row in rows),
            key=lambda row: (str(row.get("fecha") or ""), str(row.get("hora") or "")),
        )

    def stats(self) -> dict[str, int]:
        rows = self.bookings()
        active = [row for row in rows if str(row.get("estado") or "").strip().lower() in ACTIVE_STATES]
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
        today = dt.date.today().strftime("%d/%m")
        today_count = sum(today in str(row.get("fecha") or "") for row in active)
        return {
            "active": len(active),
            "pending": len(pending_reservations),
            "today": today_count,
            "cases": len(self.human_cases()),
            "tournaments": self.pending_tournament_registrations(),
        }

    def notification_counts(self, stats: dict[str, int] | None = None) -> dict[str, int]:
        """Return unresolved administrative work grouped by panel section.

        Notifications are derived from the underlying business state, so merely
        opening the panel never clears them.  They disappear only after the
        pending payment or human-attention case is actually resolved.
        """
        current = stats or self.stats()
        bookings = max(0, int(current.get("pending", 0) or 0))
        cases = max(0, int(current.get("cases", 0) or 0))
        tournaments = max(0, int(current.get("tournaments", 0) or 0))
        return {
            "bookings": bookings,
            "hours": 0,
            "operation": 0,
            "cases": cases,
            "tournaments": tournaments,
            "commands": 0,
            "total": bookings + cases + tournaments,
        }

    def command_reference(self) -> str:
        """Use the exact help catalog exposed by the WhatsApp admin command."""
        return str(legacy_callable("build_mensaje_ayuda_admin")("todos") or "")

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
        cells: list[dict[str, Any]] = []
        for time in slots:
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
                elif slot_dt <= now:
                    status = "past"
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
            "slots": slots,
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

