from __future__ import annotations

import datetime as dt
import sqlite3
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from cancheria.domain.finance.ledger import FinancialLedger, cents_to_pesos, money_to_cents


SCHEMA = """
CREATE TABLE IF NOT EXISTS bar_categories (
    category_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bar_products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category_id TEXT NOT NULL REFERENCES bar_categories(category_id),
    sale_price_cents INTEGER NOT NULL CHECK(sale_price_cents >= 0),
    cost_price_cents INTEGER,
    stock INTEGER NOT NULL DEFAULT 0,
    minimum_stock INTEGER NOT NULL DEFAULT 0,
    unit TEXT NOT NULL DEFAULT 'unidad',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bar_products_category ON bar_products(category_id);
CREATE TABLE IF NOT EXISTS bar_orders (
    order_id TEXT PRIMARY KEY,
    order_number INTEGER NOT NULL UNIQUE,
    client TEXT NOT NULL DEFAULT '',
    origin TEXT NOT NULL CHECK(origin IN ('Cancha', 'Mesa', 'Mostrador')),
    location TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    delivery_status TEXT NOT NULL DEFAULT 'open'
        CHECK(delivery_status IN ('open', 'preparing', 'delivered', 'cancelled')),
    payment_status TEXT NOT NULL DEFAULT 'pending'
        CHECK(payment_status IN ('pending', 'partial', 'paid', 'refunded')),
    total_cents INTEGER NOT NULL CHECK(total_cents >= 0),
    stock_deducted_at TEXT,
    stock_restored_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_bar_orders_created ON bar_orders(created_at);
CREATE INDEX IF NOT EXISTS idx_bar_orders_status ON bar_orders(delivery_status, payment_status);
CREATE TABLE IF NOT EXISTS bar_order_items (
    item_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES bar_orders(order_id),
    product_id TEXT NOT NULL REFERENCES bar_products(product_id),
    product_name TEXT NOT NULL,
    category_name TEXT NOT NULL,
    unit TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0),
    line_total_cents INTEGER NOT NULL CHECK(line_total_cents >= 0)
);
CREATE INDEX IF NOT EXISTS idx_bar_items_order ON bar_order_items(order_id);
CREATE TABLE IF NOT EXISTS bar_payments (
    payment_id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL REFERENCES bar_orders(order_id),
    kind TEXT NOT NULL CHECK(kind IN ('payment', 'refund')),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    method TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    responsible TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_bar_payments_order ON bar_payments(order_id);
CREATE INDEX IF NOT EXISTS idx_bar_payments_date ON bar_payments(occurred_at);
CREATE TABLE IF NOT EXISTS bar_inventory_movements (
    movement_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    product_id TEXT NOT NULL REFERENCES bar_products(product_id),
    order_id TEXT REFERENCES bar_orders(order_id),
    operation TEXT NOT NULL CHECK(operation IN ('add', 'remove', 'sale', 'return')),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    delta INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    responsible TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_bar_inventory_product ON bar_inventory_movements(product_id, occurred_at);
CREATE TABLE IF NOT EXISTS bar_order_history (
    history_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES bar_orders(order_id),
    event_type TEXT NOT NULL,
    previous_value TEXT NOT NULL DEFAULT '',
    new_value TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    responsible TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_bar_history_order ON bar_order_history(order_id, occurred_at);
CREATE TABLE IF NOT EXISTS bar_expenses (
    expense_id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    category TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    method TEXT NOT NULL,
    description TEXT NOT NULL,
    supplier TEXT NOT NULL DEFAULT '',
    responsible TEXT NOT NULL DEFAULT ''
);
"""


DELIVERY_LABELS = {
    "open": "Abierto",
    "preparing": "En preparación",
    "delivered": "Entregado",
    "cancelled": "Cancelado",
}
PAYMENT_LABELS = {
    "pending": "Pendiente",
    "partial": "Parcial",
    "paid": "Pagado",
    "refunded": "Reembolsado",
}
PAYMENT_METHODS = {"Efectivo", "Transferencia", "Tarjeta", "Mercado Pago", "Otros"}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _money_from_cents(value: int) -> Decimal:
    return (Decimal(int(value)) / Decimal(100)).quantize(Decimal("0.01"))


class BarService:
    """SQLite-backed POS with transactional stock and idempotent Caja sync."""

    def __init__(
        self,
        path: str | Path,
        cash_ledger: FinancialLedger,
        *,
        courts_provider=None,
    ) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cash_ledger = cash_ledger
        self.courts_provider = courts_provider or (lambda: [])
        with self._connect() as connection:
            connection.executescript(SCHEMA)
        self._seed_categories()
        self.sync_financial_entries()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=20000")
        return connection

    @staticmethod
    def _clean_name(value: Any, field: str) -> str:
        text = " ".join(str(value or "").split())
        if not text:
            raise ValueError(f"Ingresá {field}.")
        return text

    @staticmethod
    def _positive_int(value: Any, field: str) -> int:
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            raise ValueError(f"{field} debe ser un número entero.") from None
        if number <= 0:
            raise ValueError(f"{field} debe ser mayor que cero.")
        return number

    @staticmethod
    def _non_negative_int(value: Any, field: str) -> int:
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            raise ValueError(f"{field} debe ser un número entero.") from None
        if number < 0:
            raise ValueError(f"{field} no puede ser negativo.")
        return number

    def _seed_categories(self) -> None:
        for name in ("Bebidas", "Comidas", "Snacks"):
            self.create_category(name)

    def create_category(self, name: str) -> dict[str, Any]:
        clean = self._clean_name(name, "el nombre de la categoría")
        key = clean.casefold()
        moment = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT OR IGNORE INTO bar_categories
                   (category_id, name, name_key, active, created_at, updated_at)
                   VALUES (?, ?, ?, 1, ?, ?)""",
                (_id("cat"), clean, key, moment, moment),
            )
            row = connection.execute(
                "SELECT * FROM bar_categories WHERE name_key=?", (key,)
            ).fetchone()
        return dict(row)

    def categories(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM bar_categories"
        if active_only:
            query += " WHERE active=1"
        query += " ORDER BY name COLLATE NOCASE"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query).fetchall()]

    def create_product(
        self,
        *,
        name: str,
        category: str,
        sale_price: Any,
        cost_price: Any = "",
        stock: Any = 0,
        minimum_stock: Any = 0,
        unit: str = "unidad",
        active: bool = True,
        responsible: str = "Administrador",
    ) -> dict[str, Any]:
        clean_name = self._clean_name(name, "el nombre del producto")
        category_row = self.create_category(category)
        sale_cents = money_to_cents(sale_price)
        if sale_cents <= 0:
            raise ValueError("El precio de venta debe ser mayor que cero.")
        cost_cents = money_to_cents(cost_price) if str(cost_price or "").strip() else None
        current_stock = self._non_negative_int(stock, "El stock")
        minimum = self._non_negative_int(minimum_stock, "El stock mínimo")
        clean_unit = self._clean_name(unit, "la unidad de medida")
        product_id = _id("prod")
        moment = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO bar_products (
                    product_id, name, category_id, sale_price_cents, cost_price_cents,
                    stock, minimum_stock, unit, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    product_id, clean_name, category_row["category_id"], sale_cents,
                    cost_cents, current_stock, minimum, clean_unit, int(bool(active)),
                    moment, moment,
                ),
            )
            if current_stock:
                connection.execute(
                    """INSERT INTO bar_inventory_movements (
                        movement_id, idempotency_key, product_id, order_id, operation,
                        quantity, delta, occurred_at, reason, responsible
                    ) VALUES (?, ?, ?, NULL, 'add', ?, ?, ?, ?, ?)""",
                    (
                        _id("stock"), f"initial:{product_id}", product_id,
                        current_stock, current_stock, moment, "Stock inicial", responsible,
                    ),
                )
            row = self._product_row(connection, product_id)
        return self._decorate_product(dict(row))

    def update_product(self, product_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {
            "name", "category", "sale_price", "cost_price", "minimum_stock", "unit", "active"
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Campos de producto no válidos: {', '.join(sorted(unknown))}")
        category_id = None
        if "category" in changes:
            category_id = self.create_category(changes["category"])["category_id"]
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._product_row(connection, product_id)
            if current is None:
                raise ValueError("El producto no existe.")
            values: dict[str, Any] = {}
            if "name" in changes:
                values["name"] = self._clean_name(changes["name"], "el nombre del producto")
            if category_id is not None:
                values["category_id"] = category_id
            if "sale_price" in changes:
                amount = money_to_cents(changes["sale_price"])
                if amount <= 0:
                    raise ValueError("El precio de venta debe ser mayor que cero.")
                values["sale_price_cents"] = amount
            if "cost_price" in changes:
                raw = str(changes["cost_price"] or "").strip()
                values["cost_price_cents"] = money_to_cents(raw) if raw else None
            if "minimum_stock" in changes:
                values["minimum_stock"] = self._non_negative_int(
                    changes["minimum_stock"], "El stock mínimo"
                )
            if "unit" in changes:
                values["unit"] = self._clean_name(changes["unit"], "la unidad de medida")
            if "active" in changes:
                values["active"] = int(bool(changes["active"]))
            values["updated_at"] = _now()
            assignments = ", ".join(f"{key}=?" for key in values)
            connection.execute(
                f"UPDATE bar_products SET {assignments} WHERE product_id=?",
                (*values.values(), product_id),
            )
            row = self._product_row(connection, product_id)
        return self._decorate_product(dict(row))

    @staticmethod
    def _product_row(connection: sqlite3.Connection, product_id: str):
        return connection.execute(
            """SELECT p.*, c.name AS category FROM bar_products p
               JOIN bar_categories c ON c.category_id=p.category_id
               WHERE p.product_id=?""",
            (str(product_id),),
        ).fetchone()

    @staticmethod
    def _decorate_product(row: dict[str, Any]) -> dict[str, Any]:
        row["sale_price"] = cents_to_pesos(row.get("sale_price_cents"))
        row["cost_price"] = (
            cents_to_pesos(row.get("cost_price_cents"))
            if row.get("cost_price_cents") is not None else None
        )
        row["active"] = bool(row.get("active"))
        stock = int(row.get("stock") or 0)
        minimum = int(row.get("minimum_stock") or 0)
        if stock <= minimum:
            row["stock_level"] = "critical"
        elif stock <= max(minimum + 1, minimum * 2):
            row["stock_level"] = "low"
        else:
            row["stock_level"] = "ok"
        return row

    def products(self, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        query = """SELECT p.*, c.name AS category FROM bar_products p
                   JOIN bar_categories c ON c.category_id=p.category_id"""
        if not include_inactive:
            query += " WHERE p.active=1"
        query += " ORDER BY p.name COLLATE NOCASE"
        with self._connect() as connection:
            return [self._decorate_product(dict(row)) for row in connection.execute(query)]

    def product(self, product_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = self._product_row(connection, product_id)
        if row is None:
            raise ValueError("El producto no existe.")
        return self._decorate_product(dict(row))

    def adjust_stock(
        self,
        *,
        product_id: str,
        quantity: Any,
        operation: str,
        reason: str,
        responsible: str = "Administrador",
        allow_negative: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = str(operation or "").strip().casefold()
        if operation not in {"add", "remove"}:
            raise ValueError("La operación debe ser add o remove.")
        amount = self._positive_int(quantity, "La cantidad")
        clean_reason = self._clean_name(reason, "el motivo")
        key = str(idempotency_key or _id("manual-stock"))
        moment = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM bar_inventory_movements WHERE idempotency_key=?", (key,)
            ).fetchone()
            if existing is not None:
                if existing["product_id"] != product_id:
                    raise ValueError("La clave de idempotencia ya pertenece a otro producto.")
                row = self._product_row(connection, product_id)
                return self._decorate_product(dict(row))
            product = self._product_row(connection, product_id)
            if product is None:
                raise ValueError("El producto no existe.")
            delta = amount if operation == "add" else -amount
            new_stock = int(product["stock"]) + delta
            if new_stock < 0 and not allow_negative:
                raise ValueError("No hay stock suficiente para realizar el movimiento.")
            connection.execute(
                "UPDATE bar_products SET stock=?, updated_at=? WHERE product_id=?",
                (new_stock, moment, product_id),
            )
            connection.execute(
                """INSERT INTO bar_inventory_movements (
                    movement_id, idempotency_key, product_id, order_id, operation,
                    quantity, delta, occurred_at, reason, responsible
                ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)""",
                (_id("stock"), key, product_id, operation, amount, delta, moment, clean_reason, responsible),
            )
            row = self._product_row(connection, product_id)
        return self._decorate_product(dict(row))

    def inventory_history(self, product_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                """SELECT * FROM bar_inventory_movements WHERE product_id=?
                   ORDER BY occurred_at DESC, movement_id DESC""",
                (product_id,),
            )]

    @staticmethod
    def _normalize_items(items: Iterable[dict[str, Any]]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for item in items:
            product_id = str(item.get("product_id") or "").strip()
            try:
                quantity = int(item.get("quantity") or 0)
            except (TypeError, ValueError):
                quantity = 0
            if product_id and quantity > 0:
                normalized[product_id] = normalized.get(product_id, 0) + quantity
        if not normalized:
            raise ValueError("Seleccioná al menos un producto.")
        return normalized

    @staticmethod
    def _reserved_quantity(
        connection: sqlite3.Connection, product_id: str, *, exclude_order: str = ""
    ) -> int:
        row = connection.execute(
            """SELECT COALESCE(SUM(i.quantity), 0)
               FROM bar_order_items i JOIN bar_orders o ON o.order_id=i.order_id
               WHERE i.product_id=? AND o.delivery_status IN ('open', 'preparing')
                 AND o.order_id<>?""",
            (product_id, exclude_order),
        ).fetchone()
        return int(row[0] or 0)

    def _validate_origin(self, origin: str, location: str) -> tuple[str, str]:
        normalized = str(origin or "").strip().title()
        if normalized not in {"Cancha", "Mesa", "Mostrador"}:
            raise ValueError("Seleccioná un origen válido.")
        clean_location = " ".join(str(location or "").split())
        if normalized == "Cancha":
            courts = [str(value) for value in self.courts_provider()]
            if not clean_location or clean_location not in courts:
                raise ValueError("Seleccioná una cancha configurada en CANCHERIA.")
        return normalized, clean_location

    def _build_order_items(
        self,
        connection: sqlite3.Connection,
        items: Iterable[dict[str, Any]],
        *,
        exclude_order: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        quantities = self._normalize_items(items)
        rows: list[dict[str, Any]] = []
        total = 0
        for product_id, quantity in quantities.items():
            product = self._product_row(connection, product_id)
            if product is None or not bool(product["active"]):
                raise ValueError("Uno de los productos no existe o está inactivo.")
            reserved = self._reserved_quantity(connection, product_id, exclude_order=exclude_order)
            available = int(product["stock"]) - reserved
            if quantity > available:
                raise ValueError(
                    f"Stock insuficiente para {product['name']}: disponible {max(0, available)}."
                )
            line_total = int(product["sale_price_cents"]) * quantity
            rows.append({
                "item_id": _id("item"),
                "product_id": product_id,
                "product_name": product["name"],
                "category_name": product["category"],
                "unit": product["unit"],
                "quantity": quantity,
                "unit_price_cents": int(product["sale_price_cents"]),
                "line_total_cents": line_total,
            })
            total += line_total
        return rows, total

    def create_order(
        self,
        *,
        items: Iterable[dict[str, Any]],
        client: str = "",
        origin: str,
        location: str = "",
        notes: str = "",
        responsible: str = "Administrador",
    ) -> dict[str, Any]:
        clean_origin, clean_location = self._validate_origin(origin, location)
        order_id = _id("order")
        moment = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            built, total = self._build_order_items(connection, items)
            order_number = int(connection.execute(
                "SELECT COALESCE(MAX(order_number), 0) + 1 FROM bar_orders"
            ).fetchone()[0])
            connection.execute(
                """INSERT INTO bar_orders (
                    order_id, order_number, client, origin, location, notes,
                    delivery_status, payment_status, total_cents, created_at,
                    updated_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', 'pending', ?, ?, ?, ?)""",
                (
                    order_id, order_number, str(client or "").strip(), clean_origin,
                    clean_location, str(notes or "").strip(), total, moment, moment,
                    str(responsible or "").strip(),
                ),
            )
            for row in built:
                connection.execute(
                    """INSERT INTO bar_order_items (
                        item_id, order_id, product_id, product_name, category_name,
                        unit, quantity, unit_price_cents, line_total_cents
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row["item_id"], order_id, row["product_id"], row["product_name"],
                     row["category_name"], row["unit"], row["quantity"],
                     row["unit_price_cents"], row["line_total_cents"]),
                )
            self._history(connection, order_id, "created", "", "open", responsible, notes)
        return self.order(order_id)

    def update_order(
        self,
        order_id: str,
        *,
        items: Iterable[dict[str, Any]],
        client: str = "",
        origin: str,
        location: str = "",
        notes: str = "",
        responsible: str = "Administrador",
    ) -> dict[str, Any]:
        clean_origin, clean_location = self._validate_origin(origin, location)
        moment = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute("SELECT * FROM bar_orders WHERE order_id=?", (order_id,)).fetchone()
            if order is None:
                raise ValueError("El pedido no existe.")
            if order["delivery_status"] not in {"open", "preparing"}:
                raise ValueError("Solo se pueden editar pedidos abiertos o en preparación.")
            built, total = self._build_order_items(connection, items, exclude_order=order_id)
            paid = self._net_paid(connection, order_id)
            if total < paid:
                raise ValueError("El total editado no puede ser menor que el importe ya cobrado.")
            connection.execute("DELETE FROM bar_order_items WHERE order_id=?", (order_id,))
            for row in built:
                connection.execute(
                    """INSERT INTO bar_order_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row["item_id"], order_id, row["product_id"], row["product_name"],
                     row["category_name"], row["unit"], row["quantity"],
                     row["unit_price_cents"], row["line_total_cents"]),
                )
            status = self._payment_status(total, paid, had_refund=False)
            connection.execute(
                """UPDATE bar_orders SET client=?, origin=?, location=?, notes=?,
                   total_cents=?, payment_status=?, updated_at=? WHERE order_id=?""",
                (str(client or "").strip(), clean_origin, clean_location,
                 str(notes or "").strip(), total, status, moment, order_id),
            )
            self._history(connection, order_id, "edited", str(order["total_cents"]), str(total), responsible, notes)
        return self.order(order_id)

    @staticmethod
    def _history(
        connection: sqlite3.Connection,
        order_id: str,
        event_type: str,
        previous: Any,
        new: Any,
        responsible: str,
        notes: str = "",
    ) -> None:
        connection.execute(
            """INSERT INTO bar_order_history (
                history_id, order_id, event_type, previous_value, new_value,
                occurred_at, responsible, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (_id("hist"), order_id, event_type, str(previous or ""), str(new or ""),
             _now(), str(responsible or "").strip(), str(notes or "").strip()),
        )

    def set_delivery_status(
        self,
        order_id: str,
        status: str,
        *,
        responsible: str = "Administrador",
        restock_returned: bool = False,
    ) -> dict[str, Any]:
        status = str(status or "").strip().casefold()
        if status not in DELIVERY_LABELS:
            raise ValueError("Estado de entrega no válido.")
        allowed = {
            "open": {"preparing", "delivered", "cancelled"},
            "preparing": {"open", "delivered", "cancelled"},
            "delivered": {"cancelled"},
            "cancelled": set(),
        }
        moment = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute("SELECT * FROM bar_orders WHERE order_id=?", (order_id,)).fetchone()
            if order is None:
                raise ValueError("El pedido no existe.")
            previous = str(order["delivery_status"])
            if status == previous:
                return self._order_with_connection(connection, order_id)
            if status not in allowed[previous]:
                raise ValueError(
                    f"No se puede pasar de {DELIVERY_LABELS[previous]} a {DELIVERY_LABELS[status]}."
                )
            if status == "delivered" and not order["stock_deducted_at"]:
                items = connection.execute(
                    "SELECT * FROM bar_order_items WHERE order_id=?", (order_id,)
                ).fetchall()
                for item in items:
                    product = connection.execute(
                        "SELECT stock, name FROM bar_products WHERE product_id=?", (item["product_id"],)
                    ).fetchone()
                    if product is None or int(product["stock"]) < int(item["quantity"]):
                        name = product["name"] if product else item["product_name"]
                        raise ValueError(f"Stock insuficiente para entregar {name}.")
                for item in items:
                    connection.execute(
                        "UPDATE bar_products SET stock=stock-?, updated_at=? WHERE product_id=?",
                        (item["quantity"], moment, item["product_id"]),
                    )
                    connection.execute(
                        """INSERT OR IGNORE INTO bar_inventory_movements (
                            movement_id, idempotency_key, product_id, order_id, operation,
                            quantity, delta, occurred_at, reason, responsible
                        ) VALUES (?, ?, ?, ?, 'sale', ?, ?, ?, 'Entrega de pedido', ?)""",
                        (_id("stock"), f"sale:{order_id}:{item['item_id']}", item["product_id"],
                         order_id, item["quantity"], -int(item["quantity"]), moment, responsible),
                    )
                connection.execute(
                    "UPDATE bar_orders SET stock_deducted_at=? WHERE order_id=?", (moment, order_id)
                )
            if status == "cancelled" and restock_returned:
                if not order["stock_deducted_at"]:
                    raise ValueError("El pedido todavía no descontó stock; no hay unidades para reponer.")
                if order["stock_restored_at"]:
                    raise ValueError("El stock de este pedido ya fue repuesto.")
                items = connection.execute(
                    "SELECT * FROM bar_order_items WHERE order_id=?", (order_id,)
                ).fetchall()
                for item in items:
                    connection.execute(
                        "UPDATE bar_products SET stock=stock+?, updated_at=? WHERE product_id=?",
                        (item["quantity"], moment, item["product_id"]),
                    )
                    connection.execute(
                        """INSERT OR IGNORE INTO bar_inventory_movements (
                            movement_id, idempotency_key, product_id, order_id, operation,
                            quantity, delta, occurred_at, reason, responsible
                        ) VALUES (?, ?, ?, ?, 'return', ?, ?, ?, 'Devolución confirmada', ?)""",
                        (_id("stock"), f"return:{order_id}:{item['item_id']}", item["product_id"],
                         order_id, item["quantity"], int(item["quantity"]), moment, responsible),
                    )
                connection.execute(
                    "UPDATE bar_orders SET stock_restored_at=? WHERE order_id=?", (moment, order_id)
                )
            connection.execute(
                "UPDATE bar_orders SET delivery_status=?, updated_at=? WHERE order_id=?",
                (status, moment, order_id),
            )
            self._history(connection, order_id, "delivery_status", previous, status, responsible)
        return self.order(order_id)

    @staticmethod
    def _net_paid(connection: sqlite3.Connection, order_id: str) -> int:
        row = connection.execute(
            """SELECT COALESCE(SUM(CASE WHEN kind='payment' THEN amount_cents ELSE -amount_cents END), 0)
               FROM bar_payments WHERE order_id=?""",
            (order_id,),
        ).fetchone()
        return max(0, int(row[0] or 0))

    @staticmethod
    def _payment_status(total: int, net_paid: int, *, had_refund: bool) -> str:
        if had_refund and net_paid <= 0:
            return "refunded"
        if net_paid <= 0:
            return "pending"
        if net_paid < total:
            return "partial"
        return "paid"

    def record_payment(
        self,
        order_id: str,
        *,
        amount: Any,
        method: str,
        responsible: str = "Administrador",
        occurred_at: str | None = None,
        notes: str = "",
        request_key: str | None = None,
    ) -> dict[str, Any]:
        amount_cents = money_to_cents(amount)
        if amount_cents <= 0:
            raise ValueError("El importe debe ser mayor que cero.")
        clean_method = self._payment_method(method)
        key = str(request_key or _id("pay-request"))
        moment = str(occurred_at or _now())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM bar_payments WHERE request_key=?", (key,)
            ).fetchone()
            if existing is not None:
                if existing["order_id"] != order_id or existing["kind"] != "payment":
                    raise ValueError("La clave de pago ya pertenece a otra operación.")
                payment = dict(existing)
            else:
                order = connection.execute("SELECT * FROM bar_orders WHERE order_id=?", (order_id,)).fetchone()
                if order is None:
                    raise ValueError("El pedido no existe.")
                if order["delivery_status"] == "cancelled":
                    raise ValueError("No se puede cobrar un pedido cancelado.")
                paid = self._net_paid(connection, order_id)
                pending = int(order["total_cents"]) - paid
                if amount_cents > pending:
                    raise ValueError(f"El importe supera el saldo pendiente de ${cents_to_pesos(pending):,.0f}.")
                payment_id = _id("pay")
                connection.execute(
                    """INSERT INTO bar_payments (
                        payment_id, request_key, order_id, kind, amount_cents,
                        method, occurred_at, responsible, notes
                    ) VALUES (?, ?, ?, 'payment', ?, ?, ?, ?, ?)""",
                    (payment_id, key, order_id, amount_cents, clean_method, moment,
                     str(responsible or "").strip(), str(notes or "").strip()),
                )
                paid += amount_cents
                status = self._payment_status(int(order["total_cents"]), paid, had_refund=False)
                connection.execute(
                    "UPDATE bar_orders SET payment_status=?, updated_at=? WHERE order_id=?",
                    (status, _now(), order_id),
                )
                self._history(connection, order_id, "payment", order["payment_status"], status, responsible, clean_method)
                payment = dict(connection.execute(
                    "SELECT * FROM bar_payments WHERE payment_id=?", (payment_id,)
                ).fetchone())
        self._sync_payment(payment)
        return self.order(order_id)

    def refund_order(
        self,
        order_id: str,
        *,
        amount: Any,
        method: str,
        responsible: str = "Administrador",
        notes: str = "",
        request_key: str | None = None,
    ) -> dict[str, Any]:
        amount_cents = money_to_cents(amount)
        if amount_cents <= 0:
            raise ValueError("El importe a reembolsar debe ser mayor que cero.")
        key = str(request_key or _id("refund-request"))
        clean_method = self._payment_method(method)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM bar_payments WHERE request_key=?", (key,)).fetchone()
            if existing is not None:
                if existing["order_id"] != order_id or existing["kind"] != "refund":
                    raise ValueError("La clave de reembolso ya pertenece a otra operación.")
                payment = dict(existing)
            else:
                order = connection.execute("SELECT * FROM bar_orders WHERE order_id=?", (order_id,)).fetchone()
                if order is None:
                    raise ValueError("El pedido no existe.")
                paid = self._net_paid(connection, order_id)
                if amount_cents > paid:
                    raise ValueError("El reembolso supera el total efectivamente cobrado.")
                payment_id = _id("refund")
                connection.execute(
                    """INSERT INTO bar_payments VALUES (?, ?, ?, 'refund', ?, ?, ?, ?, ?)""",
                    (payment_id, key, order_id, amount_cents, clean_method, _now(),
                     str(responsible or "").strip(), str(notes or "").strip()),
                )
                net = paid - amount_cents
                status = self._payment_status(int(order["total_cents"]), net, had_refund=True)
                connection.execute(
                    "UPDATE bar_orders SET payment_status=?, updated_at=? WHERE order_id=?",
                    (status, _now(), order_id),
                )
                self._history(connection, order_id, "refund", order["payment_status"], status, responsible, notes)
                payment = dict(connection.execute(
                    "SELECT * FROM bar_payments WHERE payment_id=?", (payment_id,)
                ).fetchone())
        self._sync_payment(payment)
        return self.order(order_id)

    @staticmethod
    def _payment_method(value: Any) -> str:
        text = " ".join(str(value or "").split())
        aliases = {name.casefold(): name for name in PAYMENT_METHODS}
        normalized = aliases.get(text.casefold())
        if normalized is None:
            raise ValueError("Seleccioná un método de pago válido.")
        return normalized

    def record_expense(
        self,
        *,
        amount: Any,
        category: str,
        occurred_at: str,
        method: str,
        description: str,
        supplier: str = "",
        responsible: str = "Administrador",
        request_key: str | None = None,
    ) -> dict[str, Any]:
        amount_cents = money_to_cents(amount)
        if amount_cents <= 0:
            raise ValueError("El importe debe ser mayor que cero.")
        clean_category = self._clean_name(category, "la categoría")
        clean_description = self._clean_name(description, "la descripción")
        clean_method = self._payment_method(method)
        try:
            moment = dt.datetime.fromisoformat(str(occurred_at).strip()).isoformat(timespec="seconds")
        except ValueError:
            raise ValueError("Ingresá una fecha válida en formato AAAA-MM-DD o AAAA-MM-DDTHH:MM.") from None
        key = str(request_key or _id("expense-request"))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM bar_expenses WHERE request_key=?", (key,)).fetchone()
            if existing is None:
                expense_id = _id("expense")
                connection.execute(
                    """INSERT INTO bar_expenses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (expense_id, key, amount_cents, clean_category, moment, clean_method,
                     clean_description, str(supplier or "").strip(), str(responsible or "").strip()),
                )
                existing = connection.execute(
                    "SELECT * FROM bar_expenses WHERE expense_id=?", (expense_id,)
                ).fetchone()
            expense = dict(existing)
        self._sync_expense(expense)
        return expense

    def _sync_payment(self, payment: dict[str, Any]) -> None:
        order = self.order(payment["order_id"])
        is_refund = payment["kind"] == "refund"
        self.cash_ledger.record(
            movement_type="bar_refund" if is_refund else "bar_payment",
            direction="expense" if is_refund else "income",
            amount=_money_from_cents(payment["amount_cents"]),
            occurred_at=payment["occurred_at"],
            payment_method=payment["method"],
            concept=("Reembolso Bar" if is_refund else f"Pedido Bar #{order['order_number']}"),
            client=order.get("client") or order.get("display_location") or "",
            reservation_id=order["order_id"],
            court=order.get("location") if order.get("origin") == "Cancha" else "Bar",
            origin="Bar",
            responsible=payment.get("responsible", ""),
            notes=payment.get("notes", ""),
            idempotency_key=f"bar-payment:{payment['payment_id']}",
        )

    def _sync_expense(self, expense: dict[str, Any]) -> None:
        self.cash_ledger.record(
            movement_type=f"bar_expense:{expense['category']}",
            direction="expense",
            amount=_money_from_cents(expense["amount_cents"]),
            occurred_at=expense["occurred_at"],
            payment_method=expense["method"],
            concept=f"Bar · {expense['description']}",
            client=expense.get("supplier", ""),
            registration_id=expense["expense_id"],
            court="Bar",
            origin="Bar",
            responsible=expense.get("responsible", ""),
            idempotency_key=f"bar-expense:{expense['expense_id']}",
        )

    def sync_financial_entries(self) -> None:
        """Replay the local outbox safely; Caja's unique keys make this idempotent."""
        with self._connect() as connection:
            payments = [dict(row) for row in connection.execute("SELECT * FROM bar_payments")]
            expenses = [dict(row) for row in connection.execute("SELECT * FROM bar_expenses")]
        for payment in payments:
            self._sync_payment(payment)
        for expense in expenses:
            self._sync_expense(expense)

    def _order_with_connection(self, connection: sqlite3.Connection, order_id: str) -> dict[str, Any]:
        order = connection.execute("SELECT * FROM bar_orders WHERE order_id=?", (order_id,)).fetchone()
        if order is None:
            raise ValueError("El pedido no existe.")
        result = dict(order)
        result["items"] = [dict(row) for row in connection.execute(
            "SELECT * FROM bar_order_items WHERE order_id=? ORDER BY product_name COLLATE NOCASE",
            (order_id,),
        )]
        result["payments"] = [dict(row) for row in connection.execute(
            "SELECT * FROM bar_payments WHERE order_id=? ORDER BY occurred_at", (order_id,)
        )]
        result["history"] = [dict(row) for row in connection.execute(
            "SELECT * FROM bar_order_history WHERE order_id=? ORDER BY occurred_at", (order_id,)
        )]
        return self._decorate_order(result)

    def order(self, order_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            return self._order_with_connection(connection, order_id)

    @staticmethod
    def _decorate_order(row: dict[str, Any]) -> dict[str, Any]:
        row["total"] = cents_to_pesos(row.get("total_cents"))
        paid_cents = sum(
            int(item.get("amount_cents") or 0) * (1 if item.get("kind") == "payment" else -1)
            for item in row.get("payments", [])
        )
        paid_cents = max(0, paid_cents)
        row["paid_cents"] = paid_cents
        row["balance_cents"] = max(0, int(row.get("total_cents") or 0) - paid_cents)
        row["paid"] = cents_to_pesos(paid_cents)
        row["balance"] = cents_to_pesos(row["balance_cents"])
        row["delivery_label"] = DELIVERY_LABELS.get(row.get("delivery_status"), row.get("delivery_status", ""))
        row["payment_label"] = PAYMENT_LABELS.get(row.get("payment_status"), row.get("payment_status", ""))
        row["display_location"] = row.get("location") or row.get("client") or row.get("origin") or "Mostrador"
        row["summary"] = ", ".join(
            f"{item['quantity']} {item['product_name']}" for item in row.get("items", [])
        )
        methods = [item["method"] for item in row.get("payments", []) if item.get("kind") == "payment"]
        row["payment_method"] = methods[-1] if methods else "-"
        return row

    def orders(
        self,
        *,
        start_date: str,
        end_date: str,
        category: str = "Todos",
    ) -> list[dict[str, Any]]:
        start, end = self._date_range(start_date, end_date)
        params: list[Any] = [start, end]
        clause = "date(o.created_at) BETWEEN date(?) AND date(?)"
        if str(category).casefold() not in {"", "todos", "all"}:
            clause += " AND EXISTS (SELECT 1 FROM bar_order_items f WHERE f.order_id=o.order_id AND lower(f.category_name)=lower(?))"
            params.append(category)
        with self._connect() as connection:
            ids = [row[0] for row in connection.execute(
                f"SELECT o.order_id FROM bar_orders o WHERE {clause} ORDER BY o.created_at DESC, o.order_number DESC",
                params,
            )]
            return [self._order_with_connection(connection, order_id) for order_id in ids]

    @staticmethod
    def _date_range(start_date: str, end_date: str) -> tuple[str, str]:
        try:
            start = dt.date.fromisoformat(str(start_date))
            end = dt.date.fromisoformat(str(end_date))
        except ValueError:
            raise ValueError("El período debe usar fechas AAAA-MM-DD.") from None
        if end < start:
            raise ValueError("La fecha Hasta no puede ser anterior a Desde.")
        return start.isoformat(), end.isoformat()

    def snapshot(
        self,
        *,
        start_date: str,
        end_date: str,
        category: str = "Todos",
    ) -> dict[str, Any]:
        start, end = self._date_range(start_date, end_date)
        self.sync_financial_entries()
        orders = self.orders(start_date=start, end_date=end, category=category)
        products = self.products()
        today = dt.date.today().isoformat()
        with self._connect() as connection:
            today_cents = int(connection.execute(
                """SELECT COALESCE(SUM(CASE WHEN kind='payment' THEN amount_cents ELSE -amount_cents END), 0)
                   FROM bar_payments WHERE date(occurred_at)=date(?)""",
                (today,),
            ).fetchone()[0] or 0)
        active = sum(1 for row in orders if row["delivery_status"] not in {"delivered", "cancelled"})
        low = [row for row in products if int(row["stock"]) <= int(row["minimum_stock"])]

        product_stats: dict[str, dict[str, Any]] = {}
        category_cents: dict[str, int] = {}
        for order in orders:
            if order["delivery_status"] == "cancelled" or order["paid_cents"] <= 0:
                continue
            net_cents = min(int(order["total_cents"]), int(order["paid_cents"]))
            if net_cents <= 0 or int(order["total_cents"]) <= 0:
                continue
            ratio = Decimal(net_cents) / Decimal(int(order["total_cents"]))
            for item in order["items"]:
                stat = product_stats.setdefault(item["product_id"], {
                    "product_id": item["product_id"], "name": item["product_name"], "quantity": 0,
                })
                stat["quantity"] += int(item["quantity"])
                allocated = int((Decimal(int(item["line_total_cents"])) * ratio).quantize(Decimal("1")))
                category_cents[item["category_name"]] = category_cents.get(item["category_name"], 0) + allocated
        top_products = sorted(product_stats.values(), key=lambda row: (-row["quantity"], row["name"].casefold()))
        category_total = sum(category_cents.values())
        category_stats = []
        for name, amount in sorted(category_cents.items(), key=lambda item: (-item[1], item[0].casefold())):
            percent = round((amount * 100 / category_total), 1) if category_total else 0.0
            category_stats.append({"name": name, "amount": cents_to_pesos(amount), "percent": percent})
        if category_stats:
            delta = round(100.0 - sum(row["percent"] for row in category_stats), 1)
            category_stats[0]["percent"] = round(category_stats[0]["percent"] + delta, 1)
        return {
            "start_date": start,
            "end_date": end,
            "sales_today": cents_to_pesos(max(0, today_cents)),
            "active_orders": active,
            "low_products_count": len(low),
            "orders": orders,
            "top_products": top_products,
            "category_sales": category_stats,
            "critical_stock": sorted(products, key=lambda row: (row["stock_level"] != "critical", row["stock"] - row["minimum_stock"], row["name"].casefold())),
        }
