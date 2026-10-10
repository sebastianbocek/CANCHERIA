from __future__ import annotations

import csv
import datetime as dt
import sqlite3
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from cancheria.paths import runtime_dir


SCHEMA = """
CREATE TABLE IF NOT EXISTS cash_movements (
    movement_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    occurred_at TEXT NOT NULL,
    movement_type TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('income', 'expense')),
    amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'ARS',
    payment_method TEXT NOT NULL,
    status TEXT NOT NULL,
    concept TEXT NOT NULL,
    client TEXT NOT NULL DEFAULT '',
    reservation_id TEXT NOT NULL DEFAULT '',
    registration_id TEXT NOT NULL DEFAULT '',
    court TEXT NOT NULL DEFAULT '',
    origin TEXT NOT NULL,
    responsible TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cash_movements_occurred_at
    ON cash_movements(occurred_at);
CREATE INDEX IF NOT EXISTS idx_cash_movements_reservation
    ON cash_movements(reservation_id);
CREATE INDEX IF NOT EXISTS idx_cash_movements_registration
    ON cash_movements(registration_id);
CREATE TABLE IF NOT EXISTS cash_closures (
    closure_id TEXT PRIMARY KEY,
    day TEXT NOT NULL,
    closed_at TEXT NOT NULL,
    income_cents INTEGER NOT NULL,
    expense_cents INTEGER NOT NULL,
    net_cents INTEGER NOT NULL,
    cash_expected_cents INTEGER NOT NULL,
    cash_counted_cents INTEGER NOT NULL,
    difference_cents INTEGER NOT NULL,
    method_totals_json TEXT NOT NULL,
    movement_count INTEGER NOT NULL,
    responsible TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
);
"""


def money_to_cents(value: Any) -> int:
    """Convert a user/config value to integer cents without binary floats."""
    if isinstance(value, int):
        return value * 100
    if isinstance(value, Decimal):
        return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
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
        amount = Decimal(text)
    except InvalidOperation:
        return 0
    return max(0, int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def cents_to_pesos(cents: Any) -> int:
    try:
        return int(Decimal(int(cents or 0)) / Decimal(100))
    except (TypeError, ValueError, InvalidOperation):
        return 0


def normalize_method(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if "efectivo" in text or text == "cash":
        return "Mixto" if "transfer" in text else "Efectivo"
    if "transfer" in text or "comprobante" in text:
        return "Transferencia"
    return "Otros"


class FinancialLedger:
    """SQLite-backed append-only ledger with idempotent payment ingestion."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or (runtime_dir() / "caja.db")).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=20000")
        return connection

    def record(
        self,
        *,
        movement_type: str,
        direction: str,
        amount: Any,
        occurred_at: str | None = None,
        payment_method: str = "",
        status: str = "confirmed",
        concept: str,
        client: str = "",
        reservation_id: str = "",
        registration_id: str = "",
        court: str = "",
        origin: str,
        responsible: str = "",
        notes: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        direction = str(direction or "").strip().casefold()
        if direction not in {"income", "expense"}:
            raise ValueError("La dirección debe ser income o expense.")
        amount_cents = money_to_cents(amount)
        if amount_cents <= 0:
            raise ValueError("El importe debe ser mayor que cero.")
        moment = str(occurred_at or dt.datetime.now().isoformat(timespec="seconds"))
        movement_id = f"cash_{uuid.uuid4().hex}"
        key = str(idempotency_key or f"manual:{movement_id}")
        values = (
            movement_id, key, moment, str(movement_type), direction, amount_cents,
            "ARS", normalize_method(payment_method), str(status), str(concept).strip(),
            str(client or "").strip(), str(reservation_id or "").strip(),
            str(registration_id or "").strip(), str(court or "").strip(),
            str(origin or "").strip(), str(responsible or "").strip(),
            str(notes or "").strip(), dt.datetime.now().isoformat(timespec="seconds"),
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT OR IGNORE INTO cash_movements (
                    movement_id, idempotency_key, occurred_at, movement_type, direction,
                    amount_cents, currency, payment_method, status, concept, client,
                    reservation_id, registration_id, court, origin, responsible, notes,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            row = connection.execute(
                "SELECT * FROM cash_movements WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return dict(row) if row is not None else {}

    def record_cumulative_payment(
        self,
        *,
        source_kind: str,
        source_id: str,
        total_paid: Any,
        movement_type: str,
        payment_method: str,
        concept: str,
        client: str = "",
        court: str = "",
        responsible: str = "",
        occurred_at: str | None = None,
    ) -> dict[str, Any] | None:
        source_kind = str(source_kind).strip().casefold()
        source_id = str(source_id).strip()
        target_cents = money_to_cents(total_paid)
        if not source_id or target_cents <= 0:
            return None
        source_column = "reservation_id" if source_kind == "booking" else "registration_id"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_cents = int(connection.execute(
                f"""SELECT COALESCE(SUM(amount_cents), 0) FROM cash_movements
                    WHERE {source_column} = ? AND direction = 'income'
                    AND status = 'confirmed'""",
                (source_id,),
            ).fetchone()[0])
            delta = target_cents - current_cents
            if delta <= 0:
                return None
            cumulative_key = f"{source_kind}:{source_id}:confirmed-total:{target_cents}"
            movement_id = f"cash_{uuid.uuid4().hex}"
            connection.execute(
                """INSERT OR IGNORE INTO cash_movements (
                    movement_id, idempotency_key, occurred_at, movement_type, direction,
                    amount_cents, currency, payment_method, status, concept, client,
                    reservation_id, registration_id, court, origin, responsible, notes,
                    created_at
                ) VALUES (?, ?, ?, ?, 'income', ?, 'ARS', ?, 'confirmed', ?, ?, ?, ?, ?, ?, ?, '', ?)""",
                (
                    movement_id, cumulative_key,
                    occurred_at or dt.datetime.now().isoformat(timespec="seconds"),
                    movement_type, delta, normalize_method(payment_method), concept, client,
                    source_id if source_kind == "booking" else "",
                    source_id if source_kind != "booking" else "",
                    court, source_kind, responsible,
                    dt.datetime.now().isoformat(timespec="seconds"),
                ),
            )
            row = connection.execute(
                "SELECT * FROM cash_movements WHERE idempotency_key = ?",
                (cumulative_key,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_movements(
        self,
        *,
        start_date: str,
        end_date: str,
        payment_method: str = "Todos",
        statuses: tuple[str, ...] = ("confirmed",),
    ) -> list[dict[str, Any]]:
        clauses = ["date(occurred_at) BETWEEN date(?) AND date(?)"]
        params: list[Any] = [start_date, end_date]
        if str(payment_method).casefold() not in {"", "todos", "all"}:
            clauses.append("payment_method = ?")
            params.append(normalize_method(payment_method))
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        query = "SELECT * FROM cash_movements WHERE " + " AND ".join(clauses)
        query += " ORDER BY occurred_at DESC, created_at DESC"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def has_manual_duplicate(
        self,
        *,
        occurred_at: str,
        direction: str,
        amount: Any,
        payment_method: str,
        concept: str,
    ) -> bool:
        """Detect the same manual entry on the same day before it is appended."""
        amount_cents = money_to_cents(amount)
        with self._connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM cash_movements
                   WHERE origin='manual' AND date(occurred_at)=date(?)
                     AND direction=? AND amount_cents=? AND payment_method=?
                     AND lower(trim(concept))=lower(trim(?))
                   LIMIT 1""",
                (
                    occurred_at, direction, amount_cents,
                    normalize_method(payment_method), str(concept or "").strip(),
                ),
            ).fetchone()
        return row is not None

    def total_income(self, start_date: str, end_date: str) -> int:
        with self._connect() as connection:
            value = connection.execute(
                """SELECT COALESCE(SUM(amount_cents), 0) FROM cash_movements
                   WHERE direction='income' AND status='confirmed'
                   AND date(occurred_at) BETWEEN date(?) AND date(?)""",
                (start_date, end_date),
            ).fetchone()[0]
        return cents_to_pesos(value)

    def close_day(
        self,
        day: str,
        *,
        cash_counted: Any,
        responsible: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        import json

        rows = self.list_movements(start_date=day, end_date=day)
        income = sum(row["amount_cents"] for row in rows if row["direction"] == "income")
        expenses = sum(row["amount_cents"] for row in rows if row["direction"] == "expense")
        methods: dict[str, int] = {}
        for row in rows:
            signed = row["amount_cents"] if row["direction"] == "income" else -row["amount_cents"]
            methods[row["payment_method"]] = methods.get(row["payment_method"], 0) + signed
        expected = methods.get("Efectivo", 0)
        counted = money_to_cents(cash_counted)
        closure = {
            "closure_id": f"close_{uuid.uuid4().hex}",
            "day": day,
            "closed_at": dt.datetime.now().isoformat(timespec="seconds"),
            "income_cents": income,
            "expense_cents": expenses,
            "net_cents": income - expenses,
            "cash_expected_cents": expected,
            "cash_counted_cents": counted,
            "difference_cents": counted - expected,
            "method_totals": methods,
            "movement_count": len(rows),
            "responsible": str(responsible or "").strip(),
            "notes": str(notes or "").strip(),
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO cash_closures (
                    closure_id, day, closed_at, income_cents, expense_cents, net_cents,
                    cash_expected_cents, cash_counted_cents, difference_cents,
                    method_totals_json, movement_count, responsible, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    closure["closure_id"], day, closure["closed_at"], income, expenses,
                    income - expenses, expected, counted, counted - expected,
                    json.dumps(methods, ensure_ascii=False), len(rows),
                    closure["responsible"], closure["notes"],
                ),
            )
        return closure

    def export_csv(
        self,
        destination: str | Path,
        *,
        start_date: str,
        end_date: str,
        payment_method: str = "Todos",
    ) -> int:
        rows = self.list_movements(
            start_date=start_date, end_date=end_date, payment_method=payment_method
        )
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = (
            "fecha_hora", "tipo", "concepto", "cliente", "metodo", "importe_ars",
            "estado", "reserva_id", "inscripcion_id", "cancha", "origen",
            "responsable", "observaciones", "movimiento_id",
        )
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                sign = -1 if row["direction"] == "expense" else 1
                writer.writerow({
                    "fecha_hora": row["occurred_at"],
                    "tipo": row["movement_type"],
                    "concepto": row["concept"],
                    "cliente": row["client"],
                    "metodo": row["payment_method"],
                    "importe_ars": sign * cents_to_pesos(row["amount_cents"]),
                    "estado": row["status"],
                    "reserva_id": row["reservation_id"],
                    "inscripcion_id": row["registration_id"],
                    "cancha": row["court"],
                    "origen": row["origin"],
                    "responsable": row["responsible"],
                    "observaciones": row["notes"],
                    "movimiento_id": row["movement_id"],
                })
        return len(rows)


def record_cumulative_payment(**kwargs: Any) -> dict[str, Any] | None:
    return FinancialLedger().record_cumulative_payment(**kwargs)
