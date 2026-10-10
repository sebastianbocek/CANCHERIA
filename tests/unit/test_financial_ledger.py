from __future__ import annotations

import datetime as dt

from cancheria.domain.finance.ledger import FinancialLedger


def test_deposit_then_total_records_only_real_delta_and_is_idempotent(tmp_path):
    ledger = FinancialLedger(tmp_path / "caja.db")
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    first = ledger.record_cumulative_payment(source_kind="booking", source_id="R-1", total_paid=20000, movement_type="deposit", payment_method="transferencia", concept="Seña", occurred_at=stamp)
    second = ledger.record_cumulative_payment(source_kind="booking", source_id="R-1", total_paid=40000, movement_type="balance", payment_method="transferencia", concept="Saldo", occurred_at=stamp)
    duplicate = ledger.record_cumulative_payment(source_kind="booking", source_id="R-1", total_paid=40000, movement_type="balance", payment_method="transferencia", concept="Saldo", occurred_at=stamp)
    rows = ledger.list_movements(start_date=stamp[:10], end_date=stamp[:10])
    assert first["amount_cents"] == 2_000_000
    assert second["amount_cents"] == 2_000_000
    assert duplicate is None
    assert sum(row["amount_cents"] for row in rows) == 4_000_000


def test_full_payment_without_deposit_and_tournament_are_persistent(tmp_path):
    path = tmp_path / "caja.db"
    ledger = FinancialLedger(path)
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    ledger.record_cumulative_payment(source_kind="booking", source_id="R-2", total_paid=30000, movement_type="full_payment", payment_method="efectivo", concept="Pago total", occurred_at=stamp)
    ledger.record_cumulative_payment(source_kind="tournament", source_id="T-1", total_paid=12000, movement_type="tournament_payment", payment_method="transferencia", concept="Inscripción", occurred_at=stamp)
    reopened = FinancialLedger(path)
    rows = reopened.list_movements(start_date=stamp[:10], end_date=stamp[:10])
    assert len(rows) == 2
    assert reopened.total_income(stamp[:10], stamp[:10]) == 42000


def test_expense_refund_and_empty_ledger(tmp_path):
    ledger = FinancialLedger(tmp_path / "caja.db")
    today = dt.date.today().isoformat()
    assert ledger.list_movements(start_date=today, end_date=today) == []
    ledger.record(movement_type="refund", direction="expense", amount="2.500", occurred_at=f"{today}T10:00:00", payment_method="Efectivo", concept="Devolución", origin="manual")
    rows = ledger.list_movements(start_date=today, end_date=today)
    assert rows[0]["amount_cents"] == 250000
    assert rows[0]["direction"] == "expense"
