from __future__ import annotations

import csv
import datetime as dt

from cancheria.admin.desktop_service import DesktopAdminService
from cancheria.infrastructure.persistence.json_store import JSONStore


def build_cash_service(tmp_path, monkeypatch, rows):
    service = object.__new__(DesktopAdminService)
    service.root = tmp_path
    service.runtime = tmp_path / "runtime"
    service.runtime.mkdir(parents=True)
    service._cash_store = JSONStore(service.runtime / "caja_movimientos.json")
    service._cash_closures_store = JSONStore(service.runtime / "caja_cierres.json")
    monkeypatch.setattr(service, "bookings", lambda: [dict(row) for row in rows])
    monkeypatch.setattr(
        "cancheria.admin.desktop_service.event_registration.list_business_events",
        lambda active_only=False: [],
    )
    return service


def booking_rows(today: dt.date):
    common = {
        "reservation_id": "R-100",
        "fecha": today.strftime("%d/%m/%Y"),
        "estado": "reservado",
        "telefono": "+5493510000000",
        "nombre": "Cliente Prueba",
        "cancha": "Cancha 1",
        "tipo_turno": "Fútbol 5",
        "precio_total": "20000",
        "senia_estado": "pagada",
        "senia_monto": "10000",
        "senia_pagada_monto": "10000",
        "monto_pendiente": "10000",
        "payment_method": "transferencia",
        "reservado_en": dt.datetime.combine(today, dt.time(10, 30)).isoformat(),
    }
    return [{**common, "hora": "20:00"}, {**common, "hora": "21:00"}]


def test_cash_snapshot_groups_multislot_booking_and_uses_real_amounts(tmp_path, monkeypatch):
    today = dt.date.today()
    service = build_cash_service(tmp_path, monkeypatch, booking_rows(today))

    snapshot = service.cash_snapshot(start_date=today.isoformat(), end_date=today.isoformat())

    assert snapshot["income_today"] == 10000
    assert snapshot["income_month"] == 10000
    assert snapshot["pending_balances"] == 10000
    assert snapshot["future_reservations"] == 20000
    assert snapshot["period_balance"] == 10000
    assert len(snapshot["movements"]) == 1
    assert snapshot["movements"][0]["source_id"] == "R-100"
    assert snapshot["method_income"] == {"Transferencia": 10000}
    assert snapshot["court_income"] == {"Cancha 1": 10000}


def test_cash_manual_income_expense_filters_and_export(tmp_path, monkeypatch):
    today = dt.date.today()
    service = build_cash_service(tmp_path, monkeypatch, [])
    stamp = dt.datetime.combine(today, dt.time(15, 0)).isoformat()
    service.add_cash_movement(
        kind="income", occurred_at=stamp, concept="Alquiler extra", amount="15000",
        method="Efectivo", client="Juan", court="Cancha 2",
    )
    service.add_cash_movement(
        kind="expense", occurred_at=stamp, concept="Mantenimiento", amount="$ 3.000",
        method="Efectivo", client="Proveedor", court="Cancha 2",
    )
    service.add_cash_movement(
        kind="income", occurred_at=stamp, concept="Venta", amount="5000",
        method="Transferencia", client="Ana",
    )

    cash = service.cash_snapshot(
        start_date=today.isoformat(), end_date=today.isoformat(), method="Efectivo"
    )
    assert len(cash["movements"]) == 2
    assert cash["period_balance"] == 12000
    assert cash["income_today"] == 20000

    destination = tmp_path / "export" / "caja.csv"
    exported = service.export_cash_csv(
        destination,
        start_date=today.isoformat(),
        end_date=today.isoformat(),
        method="Todos",
    )
    assert exported == 3
    with destination.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["concepto"] for row in rows} == {
        "Alquiler extra", "Mantenimiento", "Venta"
    }
    assert next(row for row in rows if row["concepto"] == "Mantenimiento")["importe"] == "-3000"


def test_close_cash_keeps_movements_and_writes_auditable_snapshot(tmp_path, monkeypatch):
    today = dt.date.today()
    service = build_cash_service(tmp_path, monkeypatch, [])
    service.add_cash_movement(
        kind="income",
        occurred_at=dt.datetime.combine(today, dt.time(12)).isoformat(),
        concept="Ingreso del día",
        amount=8000,
        method="Efectivo",
    )

    closure = service.close_cash(today.isoformat())

    assert closure["balance"] == 8000
    assert closure["movement_count"] == 1
    assert len(service._cash_manual_rows()) == 1
    stored = service._cash_closures_store.read(default={})
    assert stored["closures"][0]["closure_id"] == closure["closure_id"]
