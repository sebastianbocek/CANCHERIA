from __future__ import annotations

import datetime as dt
from contextlib import nullcontext


class _CalendarStub:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]
        self.write_count = 0

    def asegurar_ids_reservas_pendientes(self):
        return self.rows

    def atomic(self):
        return nullcontext()

    def _leer_todos(self):
        return self.rows

    def _escribir_todos(self, rows, ordenar=True):
        self.rows = rows
        self.write_count += 1


def _expired_transfer_row(*, reservation_id="501"):
    return {
        "reservation_id": reservation_id,
        "fecha": (dt.date.today() + dt.timedelta(days=2)).isoformat(),
        "hora": "20:00",
        "cancha": "Cancha 1",
        "estado": "hold_expirado",
        "senia_estado": "pendiente",
        "payment_method": "transferencia",
        "precio_total": "20000",
        "senia_monto": "10000",
        "monto_pendiente": "10000",
        "duracion_horas": "1",
        "telefono": "+5493510000000",
        "nombre": "Cliente",
    }


def _isolate_expired_hold_side_effects(monkeypatch, legacy, calendar):
    monkeypatch.setattr(legacy, "calendario", calendar)
    monkeypatch.setattr(legacy, "validar_fecha_en_dias_atencion", lambda _value: True)
    monkeypatch.setattr(legacy, "validar_hora_en_franja", lambda _value: True)
    monkeypatch.setattr(legacy, "_json_read", lambda *_args, **_kwargs: {"sent": {}})
    monkeypatch.setattr(legacy, "_json_write", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        legacy, "_discard_stale_hold_expiration_notifications", lambda *_args: None
    )
    monkeypatch.setattr(legacy, "marcar_hold_expirado_pago_tardio", lambda *_args: None)
    monkeypatch.setattr(legacy, "_memoria_cliente_por_reserva", lambda _row: ("client", {}))
    monkeypatch.setattr(legacy, "guardar_memoria_cliente", lambda *_args: None)
    monkeypatch.setattr(legacy, "update_conversation_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(legacy, "registrar_metrica_operativa", lambda *_args: None)


def test_manual_deposit_recovers_non_cash_expired_hold_when_slot_is_free(monkeypatch):
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    expired = _expired_transfer_row()
    calendar = _CalendarStub([expired])
    _isolate_expired_hold_side_effects(monkeypatch, legacy, calendar)

    result = legacy.marcar_senia_pagada_admin({
        "reservation_id": "501",
        "pago_total": False,
        "deterministic": True,
    })

    assert result["ok"] is True
    assert result["restored_after_expiry"] is True
    assert calendar.write_count == 1
    assert calendar.rows[0]["estado"] == legacy.BOOKING_STATUS_RESERVED
    assert calendar.rows[0]["senia_estado"] == "pagada"
    assert calendar.rows[0]["payment_method"] == "transferencia"
    assert calendar.rows[0]["monto_pendiente"] == "10000"


def test_manual_total_recovers_non_cash_expired_hold_and_closes_balance(monkeypatch):
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    calendar = _CalendarStub([_expired_transfer_row(reservation_id="502")])
    _isolate_expired_hold_side_effects(monkeypatch, legacy, calendar)

    result = legacy.marcar_senia_pagada_admin({
        "reservation_id": "502",
        "pago_total": True,
        "deterministic": True,
    })

    assert result["ok"] is True
    assert result["pago_total"] is True
    assert calendar.rows[0]["estado"] == legacy.BOOKING_STATUS_RESERVED
    assert calendar.rows[0]["senia_estado"] == "pagada"
    assert legacy._monto_a_int(calendar.rows[0]["senia_monto"]) == 20000
    assert calendar.rows[0]["monto_pendiente"] == "0"


def test_manual_confirmation_rejects_expired_hold_when_slot_was_taken(monkeypatch):
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    expired = _expired_transfer_row(reservation_id="503")
    occupied = {
        **expired,
        "reservation_id": "900",
        "estado": legacy.BOOKING_STATUS_RESERVED,
        "senia_estado": "pagada",
        "telefono": "+5493519999999",
    }
    calendar = _CalendarStub([expired, occupied])
    _isolate_expired_hold_side_effects(monkeypatch, legacy, calendar)
    monkeypatch.setattr(
        legacy,
        "_admin_cash_confirmation_conflict_message",
        lambda reservation_id, _row, reason: f"{reservation_id}:{reason}",
    )

    result = legacy.marcar_senia_pagada_admin({
        "reservation_id": "503",
        "pago_total": False,
        "deterministic": True,
    })

    assert result["ok"] is False
    assert result["motivo"] == "slot_occupied"
    assert calendar.write_count == 0
    assert calendar.rows[0]["estado"] == "hold_expirado"

