"""Persistent financial ledger used by the administration dashboard."""

from .ledger import FinancialLedger, record_cumulative_payment

__all__ = ["FinancialLedger", "record_cumulative_payment"]
