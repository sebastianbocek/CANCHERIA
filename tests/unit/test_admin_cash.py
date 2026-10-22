from __future__ import annotations

import csv
import datetime as dt
from types import SimpleNamespace

from cancheria.admin.desktop_service import DesktopAdminService
from cancheria.desktop.admin_panel import AdminPanel
from cancheria.domain.finance.ledger import FinancialLedger


def build_cash_service(tmp_path, monkeypatch, rows=()):
    service = object.__new__(DesktopAdminService)
    service.root = tmp_path
    service.runtime = tmp_path / "runtime"
    service.runtime.mkdir(parents=True)
    service.cash_ledger = FinancialLedger(service.runtime / "caja.db")
    monkeypatch.setattr(service, "bookings", lambda: [dict(row) for row in rows])
    monkeypatch.setattr(service, "court_catalog", lambda: [
        {"name": "Cancha 1", "type": "Fútbol 5"},
        {"name": "Cancha 2", "type": "Pádel"},
    ])
    monkeypatch.setattr(
        "cancheria.admin.desktop_service.event_registration.list_business_events",
        lambda active_only=False: [],
    )
    return service


def test_existing_paid_booking_is_not_invented_as_historical_income(tmp_path, monkeypatch):
    today = dt.date.today()
    rows = [{
        "reservation_id": "R-old", "fecha": today.isoformat(), "hora": "23:00",
        "estado": "reservado", "precio_total": "20000", "monto_pendiente": "10000",
        "senia_pagada_monto": "10000", "cancha": "Cancha 1",
    }]
    service = build_cash_service(tmp_path, monkeypatch, rows)
    snapshot = service.cash_snapshot(start_date=today.isoformat(), end_date=today.isoformat())
    assert snapshot["income_today"] == 0
    assert snapshot["movements"] == []
    assert snapshot["pending_balances"] == 10000
    assert "no se inventan cobros históricos" in snapshot["history_notice"]


def test_cash_manual_filters_totals_individual_court_and_export(tmp_path, monkeypatch):
    today = dt.date.today()
    service = build_cash_service(tmp_path, monkeypatch)
    stamp = dt.datetime.combine(today, dt.time(15)).isoformat()
    service.add_cash_movement(kind="income", occurred_at=stamp, concept="Alquiler", amount="15000", method="Efectivo", client="Juan", court="Cancha 1")
    service.add_cash_movement(kind="expense", occurred_at=stamp, concept="Mantenimiento", amount="$ 3.000", method="Efectivo", client="Proveedor", court="Cancha 1")
    service.add_cash_movement(kind="income", occurred_at=stamp, concept="Venta", amount="5000", method="Transferencia", client="Ana", court="Cancha 2")
    cash = service.cash_snapshot(start_date=today.isoformat(), end_date=today.isoformat(), method="Efectivo")
    assert len(cash["movements"]) == 2
    assert cash["period_balance"] == 12000
    assert cash["income_today"] == 20000
    assert cash["court_income"]["Cancha 1 · Fútbol 5"] == 15000
    destination = tmp_path / "caja.csv"
    assert service.export_cash_csv(destination, start_date=today.isoformat(), end_date=today.isoformat()) == 3
    with destination.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.DictReader(handle))
    assert next(row for row in exported if row["concepto"] == "Mantenimiento")["importe_ars"] == "-3000"


def test_manual_duplicate_requires_explicit_override(tmp_path, monkeypatch):
    service = build_cash_service(tmp_path, monkeypatch)
    stamp = dt.datetime.now().isoformat()
    kwargs = dict(kind="income", occurred_at=stamp, concept="Mostrador", amount=1000, method="Efectivo")
    service.add_cash_movement(**kwargs)
    try:
        service.add_cash_movement(**kwargs)
    except ValueError as exc:
        assert str(exc).startswith("POSSIBLE_DUPLICATE:")
    else:
        raise AssertionError("duplicate was not detected")
    service.add_cash_movement(**kwargs, allow_duplicate=True)
    assert len(service.cash_ledger.list_movements(start_date=stamp[:10], end_date=stamp[:10])) == 2


class FakeChartCanvas:
    def __init__(self, *, width=360, height=72):
        self.width = width
        self.height = height
        self.texts = []
        self.rectangles = []
        self.bindings = []
        self._next_id = 1

    def delete(self, _target):
        return None

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def create_text(self, *args, **kwargs):
        self.texts.append((args, kwargs))
        item_id = self._next_id
        self._next_id += 1
        return item_id

    def create_rectangle(self, *args, **kwargs):
        self.rectangles.append((args, kwargs))
        item_id = self._next_id
        self._next_id += 1
        return item_id

    def create_line(self, *args, **kwargs):
        return None

    def tag_bind(self, item_id, event, callback):
        self.bindings.append((item_id, event, callback))

    def bbox(self, _item_id):
        return (100, 5, 220, 20)

    def tag_lower(self, _item_id, _below):
        return None

    def tag_raise(self, _item_id):
        return None


def test_cash_court_chart_does_not_hide_configured_courts():
    panel = object.__new__(AdminPanel)
    panel.NAVY = "#142B50"
    panel.MUTED = "#64748B"
    canvas = FakeChartCanvas(height=72)
    values = {
        "Cancha 1 · Fútbol 5": 20000,
        "Cancha 2 · Fútbol 7": 0,
        "Cancha 3 · Tenis": 0,
        "Cancha 4 · Pádel": 0,
    }

    panel._draw_cash_rank_chart(
        canvas, values, ("#1673FF",), percent=False, limit=None, full_labels=True
    )

    rendered_labels = [kwargs.get("text") for _args, kwargs in canvas.texts]
    assert set(values).issubset(rendered_labels)


def test_cash_daily_chart_binds_amount_tooltip_to_every_bar():
    panel = object.__new__(AdminPanel)
    panel.BLUE = "#1673FF"
    panel.MUTED = "#64748B"
    panel.NAVY = "#142B50"
    canvas = FakeChartCanvas(height=96)

    panel._draw_cash_daily_chart(canvas, {
        "2026-10-20": 0,
        "2026-10-21": 20000,
    })

    bar_rectangles = [
        kwargs for _args, kwargs in canvas.rectangles
        if "cash-daily-bar" in kwargs.get("tags", ())
    ]
    assert len(bar_rectangles) == 2
    events = [event for _item, event, _callback in canvas.bindings]
    assert events.count("<Enter>") == 2
    assert events.count("<Leave>") == 2
    enter_callbacks = [
        callback for _item, event, callback in canvas.bindings if event == "<Enter>"
    ]
    enter_callbacks[-1](SimpleNamespace(x=250, y=30))
    tooltip_labels = [
        kwargs.get("text") for _args, kwargs in canvas.texts
        if "cash-daily-tooltip" in kwargs.get("tags", ())
    ]
    assert "21/10/2026  ·  $20.000" in tooltip_labels


def test_close_cash_is_auditable_and_keeps_movements(tmp_path, monkeypatch):
    today = dt.date.today().isoformat()
    service = build_cash_service(tmp_path, monkeypatch)
    service.add_cash_movement(kind="income", occurred_at=f"{today}T12:00:00", concept="Cobro", amount=8000, method="Efectivo")
    service.add_cash_movement(kind="expense", occurred_at=f"{today}T13:00:00", concept="Insumos", amount=1000, method="Efectivo")
    result = service.close_cash(today, cash_counted=6900, responsible="Seba", notes="Prueba")
    assert result["income"] == 8000
    assert result["expenses"] == 1000
    assert result["balance"] == 7000
    assert result["cash_expected"] == 7000
    assert result["difference"] == -100
    assert len(service.cash_ledger.list_movements(start_date=today, end_date=today)) == 2
