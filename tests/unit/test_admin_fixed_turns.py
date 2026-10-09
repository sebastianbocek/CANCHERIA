from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

from cancheria.admin import desktop_service as service_module
from cancheria.admin.desktop_service import DesktopAdminService


class FixedTurnCalendar:
    def __init__(self):
        self.rows = []

    def asegurar_ids_reservas(self):
        return copy.deepcopy(self.rows)

    def reservar(
        self,
        day,
        time,
        phone,
        *,
        nombre="",
        website="",
        cancha="",
        estado="pendiente",
        senia_estado="pendiente",
        extra_fields=None,
        **_kwargs,
    ):
        selected = dt.date.fromisoformat(day)
        row = {
            "reservation_id": "TF-1",
            "fecha": selected.strftime("%d/%m/%Y"),
            "hora": time,
            "telefono": phone,
            "nombre": nombre,
            "website": website,
            "cancha": cancha,
            "estado": estado,
            "senia_estado": senia_estado,
            **(extra_fields or {}),
        }
        self.rows.append(row)
        return True, (row["fecha"], time)


def test_fixed_turn_creation_reuses_whatsapp_memory_and_updates_hours_calendar(
    tmp_path, monkeypatch
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    memory_file = runtime / "client_memory.json"
    memory_file.write_text("{}", encoding="utf-8")
    calls = []
    calendar = FixedTurnCalendar()

    def read_memories():
        return json.loads(memory_file.read_text(encoding="utf-8"))

    def save_memories(payload):
        memory_file.write_text(json.dumps(payload), encoding="utf-8")

    def update_fixed(command):
        calls.append(dict(command))
        memories = read_memories()
        key = command["telefono"]
        memories[key] = {
            "nombre": command["nombre"],
            "telefono": command["telefono"],
            "turno_fijo": {
                "activo": True,
                "dia_semana": command["dia_semana"],
                "dia_nombre": "lunes",
                "hora": command["hora"],
                "cancha": command["cancha"],
                "ultima_reserva_fecha": "",
            },
        }
        save_memories(memories)
        return {"ok": True, "respuesta": "Turno fijo creado."}

    def load_memory(key):
        return read_memories()[key]

    def save_memory(key, memory):
        memories = read_memories()
        memories[key] = memory
        save_memories(memories)
        return True

    def reserve(phone, prospect, day, time, **kwargs):
        selected = dt.datetime.strptime(day, "%d/%m/%Y").date().isoformat()
        ok, detail = calendar.reservar(
            selected,
            time,
            phone,
            nombre=prospect["nombre"],
            website=prospect["website"],
            cancha=kwargs["cancha"],
            estado=kwargs["estado_reserva"],
            senia_estado=kwargs["senia_estado"],
        )
        return {"ok": ok, "dia": detail[0], "hora": detail[1], "cancha": kwargs["cancha"]}

    functions = {
        "actualizar_turno_fijo_cliente": update_fixed,
        "_telefono_memoria_turno_fijo": lambda command: command["telefono"],
        "cargar_memoria_cliente": load_memory,
        "guardar_memoria_cliente": save_memory,
        "reservar_turno_en_calendario": reserve,
    }
    monkeypatch.setattr(service_module, "legacy_callable", lambda name: functions[name])
    monkeypatch.setattr(service_module.cfg, "COURTS", [{"name": "Cancha 1"}])

    service = DesktopAdminService(tmp_path)
    service.calendar = calendar
    result = service.create_fixed_turn(
        name="Juan",
        phone="+5493511111111",
        weekday=0,
        time="20:00",
        court="Cancha 1",
    )

    assert calls[0]["accion"] == "agregar_turno_fijo"
    assert service.calendar.rows[0]["website"] == "Turno fijo semanal"
    assert service.calendar.rows[0]["senia_estado"] == "pendiente"
    assert "próximo turno fue agregado a Horas" in result
    listed = service.fixed_turns()
    assert listed[0]["name"] == "Juan"
    assert listed[0]["calendar_status"] == "En agenda"


def test_remove_fixed_turn_uses_same_whatsapp_operation(monkeypatch):
    captured = {}

    def update(command):
        captured.update(command)
        return {"ok": True, "respuesta": "Turno fijo quitado."}

    monkeypatch.setattr(
        service_module,
        "legacy_callable",
        lambda name: update if name == "actualizar_turno_fijo_cliente" else None,
    )
    service = object.__new__(DesktopAdminService)

    result = service.remove_fixed_turn(
        client_key="+5493511111111",
        name="Juan",
        phone="+5493511111111",
    )

    assert captured == {
        "accion": "quitar_turno_fijo",
        "telefono": "+5493511111111",
        "nombre": "Juan",
    }
    assert "se conserva en Horas" in result


def test_admin_gui_places_fixed_turns_immediately_before_blacklist():
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cancheria"
        / "desktop"
        / "admin_panel.py"
    ).read_text(encoding="utf-8")

    fixed_tab = 'self.notebook.add(self.fixed_turns_tab, text="Turnos Fijos")'
    blacklist_tab = 'self.notebook.add(self.blacklist_tab, text="Blacklist")'
    assert fixed_tab in source
    assert source.index(fixed_tab) < source.index(blacklist_tab)
    assert '"Nuevo turno fijo"' in source
    assert '"Quitar seleccionado"' in source
    assert "def _refresh_fixed_turns" in source
    assert "self._refresh_hours()" in source
