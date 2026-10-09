from __future__ import annotations

import datetime as dt
import json
import re
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from cancheria.config import legacy_config as cfg
from cancheria.config.court_sports import sport_icon, sport_menu_options
from cancheria.domain.reservations.calendar import CalendarioLlamadas
from cancheria.domain.events import registration as event_registration
from cancheria.infrastructure.persistence.json_store import JSONStore
from cancheria.legacy_bridge import legacy_callable


ACTIVE_STATES = {str(value).strip().lower() for value in cfg.ACTIVE_BOOKING_STATUSES}
NOTIFICATION_KEYS = (
    "bookings", "hours", "operation", "cases", "tournaments", "fixed_turns",
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
        self._notification_read_store = JSONStore(
            self.runtime / "admin_notification_read_state.json"
        )

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
        """Return unresolved administrative work grouped by panel section."""
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

