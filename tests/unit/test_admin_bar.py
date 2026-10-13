from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import pytest

from cancheria.domain.bar import BarService
from cancheria.domain.finance.ledger import FinancialLedger, cents_to_pesos


def build_bar(tmp_path, courts=("Cancha 1", "Cancha 2")) -> BarService:
    runtime = tmp_path / "runtime"
    return BarService(
        runtime / "bar.db",
        FinancialLedger(runtime / "caja.db"),
        courts_provider=lambda: list(courts),
    )


def product(bar: BarService, *, name="Agua", category="Bebidas", price=2000, stock=10, minimum=3):
    return bar.create_product(
        name=name,
        category=category,
        sale_price=price,
        cost_price=1000,
        stock=stock,
        minimum_stock=minimum,
        unit="unidades",
    )


def order(bar: BarService, item, quantity=1, **overrides):
    values = {
        "items": [{"product_id": item["product_id"], "quantity": quantity}],
        "client": "Juan",
        "origin": "Cancha",
        "location": "Cancha 1",
        "notes": "Sin hielo",
    }
    values.update(overrides)
    return bar.create_order(**values)


def today_snapshot(bar: BarService):
    today = dt.date.today().isoformat()
    return bar.snapshot(start_date=today, end_date=today)


def test_product_create_edit_categories_and_restart_persistence(tmp_path):
    bar = build_bar(tmp_path)
    created = product(bar)
    assert created["name"] == "Agua"
    assert created["sale_price"] == 2000
    assert created["cost_price"] == 1000
    assert created["stock"] == 10
    assert {row["name"] for row in bar.categories()} >= {"Bebidas", "Comidas", "Snacks"}

    edited = bar.update_product(
        created["product_id"], name="Agua 500 ml", category="Sin alcohol",
        sale_price="2.500", cost_price="1.200", minimum_stock=4, unit="botellas", active=False,
    )
    assert edited["name"] == "Agua 500 ml"
    assert edited["category"] == "Sin alcohol"
    assert edited["sale_price"] == 2500
    assert edited["active"] is False
    assert bar.products() == []

    reopened = build_bar(tmp_path)
    persisted = reopened.product(created["product_id"])
    assert persisted["name"] == "Agua 500 ml"
    assert persisted["stock"] == 10


def test_manual_stock_movements_critical_detection_and_negative_guard(tmp_path):
    bar = build_bar(tmp_path)
    item = product(bar, stock=5, minimum=3)
    bar.adjust_stock(product_id=item["product_id"], quantity=2, operation="remove", reason="Rotura")
    critical = bar.product(item["product_id"])
    assert critical["stock"] == 3
    assert critical["stock_level"] == "critical"
    assert today_snapshot(bar)["low_products_count"] == 1

    bar.adjust_stock(product_id=item["product_id"], quantity=7, operation="add", reason="Recepción")
    assert bar.product(item["product_id"])["stock"] == 10
    history = bar.inventory_history(item["product_id"])
    assert {row["operation"] for row in history} >= {"add", "remove"}
    with pytest.raises(ValueError, match="stock suficiente"):
        bar.adjust_stock(product_id=item["product_id"], quantity=99, operation="remove", reason="Error")


def test_create_and_edit_order_uses_real_courts_and_reserves_stock(tmp_path):
    bar = build_bar(tmp_path)
    water = product(bar, stock=5)
    food = product(bar, name="Pancho", category="Comidas", price=3000, stock=4)
    created = bar.create_order(
        items=[{"product_id": water["product_id"], "quantity": 2}],
        client="Ana", origin="Cancha", location="Cancha 2", notes="",
    )
    assert created["total"] == 4000
    assert created["delivery_status"] == "open"
    assert created["payment_status"] == "pending"

    edited = bar.update_order(
        created["order_id"],
        items=[
            {"product_id": water["product_id"], "quantity": 1},
            {"product_id": food["product_id"], "quantity": 1},
        ],
        client="Ana", origin="Mesa", location="Mesa 3", notes="Con mostaza",
    )
    assert edited["total"] == 5000
    assert edited["display_location"] == "Mesa 3"
    assert len(edited["items"]) == 2
    with pytest.raises(ValueError, match="cancha configurada"):
        order(bar, water, origin="Cancha", location="Cancha inexistente")
    with pytest.raises(ValueError, match="Stock insuficiente"):
        order(bar, water, quantity=5)


def test_delivery_deducts_stock_once_even_with_concurrent_confirmation(tmp_path):
    bar = build_bar(tmp_path)
    item = product(bar, stock=8)
    created = order(bar, item, quantity=3)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _index: bar.set_delivery_status(created["order_id"], "delivered"),
            range(2),
        ))

    assert all(result["delivery_status"] == "delivered" for result in results)
    assert bar.product(item["product_id"])["stock"] == 5
    sales = [row for row in bar.inventory_history(item["product_id"]) if row["operation"] == "sale"]
    assert len(sales) == 1
    with pytest.raises(ValueError, match="Solo se pueden editar"):
        bar.update_order(
            created["order_id"], items=[{"product_id": item["product_id"], "quantity": 1}],
            client="", origin="Mostrador", location="", notes="",
        )


def test_partial_full_and_duplicate_payment_integrate_once_with_cash(tmp_path):
    bar = build_bar(tmp_path)
    item = product(bar, price=3500)
    created = order(bar, item, quantity=2)
    first = bar.record_payment(
        created["order_id"], amount=3000, method="Efectivo", request_key="terminal-1",
    )
    assert first["payment_status"] == "partial"
    assert first["balance"] == 4000

    duplicate = bar.record_payment(
        created["order_id"], amount=3000, method="Efectivo", request_key="terminal-1",
    )
    assert duplicate["paid"] == 3000
    paid = bar.record_payment(
        created["order_id"], amount=4000, method="Mercado Pago", request_key="terminal-2",
    )
    assert paid["payment_status"] == "paid"
    assert paid["balance"] == 0
    with pytest.raises(ValueError, match="saldo pendiente"):
        bar.record_payment(created["order_id"], amount=1, method="Efectivo")

    rows = bar.cash_ledger.list_movements(
        start_date=dt.date.today().isoformat(), end_date=dt.date.today().isoformat()
    )
    bar_rows = [row for row in rows if row["origin"] == "Bar"]
    assert len(bar_rows) == 2
    assert sum(cents_to_pesos(row["amount_cents"]) for row in bar_rows) == 7000
    assert {row["payment_method"] for row in bar_rows} == {"Efectivo", "Mercado Pago"}


def test_idempotency_keys_cannot_be_reused_for_another_entity(tmp_path):
    bar = build_bar(tmp_path)
    first_product = product(bar, name="Agua", stock=10)
    second_product = product(bar, name="Gaseosa", stock=10)
    bar.adjust_stock(
        product_id=first_product["product_id"], quantity=1, operation="add",
        reason="Recepción", idempotency_key="stock-terminal-1",
    )
    with pytest.raises(ValueError, match="otro producto"):
        bar.adjust_stock(
            product_id=second_product["product_id"], quantity=1, operation="add",
            reason="Recepción", idempotency_key="stock-terminal-1",
        )

    first_order = order(bar, first_product, quantity=1)
    second_order = order(bar, second_product, quantity=1)
    bar.record_payment(
        first_order["order_id"], amount=2000, method="Efectivo", request_key="pay-terminal-1",
    )
    with pytest.raises(ValueError, match="otra operación"):
        bar.record_payment(
            second_order["order_id"], amount=2000, method="Efectivo", request_key="pay-terminal-1",
        )


def test_cancel_and_return_only_restock_when_goods_really_return(tmp_path):
    bar = build_bar(tmp_path)
    item = product(bar, stock=10)
    no_return = order(bar, item, quantity=2)
    bar.set_delivery_status(no_return["order_id"], "delivered")
    bar.set_delivery_status(no_return["order_id"], "cancelled", restock_returned=False)
    assert bar.product(item["product_id"])["stock"] == 8

    returned = order(bar, item, quantity=3)
    bar.set_delivery_status(returned["order_id"], "delivered")
    bar.set_delivery_status(returned["order_id"], "cancelled", restock_returned=True)
    assert bar.product(item["product_id"])["stock"] == 8
    movements = bar.inventory_history(item["product_id"])
    assert len([row for row in movements if row["operation"] == "return"]) == 1


def test_refund_updates_payment_state_and_cash_without_implicit_stock_change(tmp_path):
    bar = build_bar(tmp_path)
    item = product(bar, stock=5, price=2000)
    created = order(bar, item, quantity=2)
    bar.set_delivery_status(created["order_id"], "delivered")
    bar.record_payment(created["order_id"], amount=4000, method="Tarjeta")
    refunded = bar.refund_order(created["order_id"], amount=4000, method="Tarjeta")
    assert refunded["payment_status"] == "refunded"
    assert bar.product(item["product_id"])["stock"] == 3
    rows = bar.cash_ledger.list_movements(
        start_date=dt.date.today().isoformat(), end_date=dt.date.today().isoformat()
    )
    assert {(row["direction"], row["movement_type"]) for row in rows} == {
        ("income", "bar_payment"), ("expense", "bar_refund")
    }


def test_bar_expense_integrates_with_cash_but_does_not_receive_stock(tmp_path):
    bar = build_bar(tmp_path)
    item = product(bar, stock=4)
    now = dt.datetime.now().isoformat(timespec="seconds")
    bar.record_expense(
        amount=9000, category="Compra de mercadería", occurred_at=now,
        method="Transferencia", description="Proveedor de bebidas", supplier="Distribuidora",
        request_key="invoice-55",
    )
    bar.record_expense(
        amount=9000, category="Compra de mercadería", occurred_at=now,
        method="Transferencia", description="Proveedor de bebidas", supplier="Distribuidora",
        request_key="invoice-55",
    )
    assert bar.product(item["product_id"])["stock"] == 4
    rows = bar.cash_ledger.list_movements(start_date=now[:10], end_date=now[:10])
    assert len(rows) == 1
    assert rows[0]["direction"] == "expense"
    assert rows[0]["origin"] == "Bar"


def test_rankings_category_percentages_and_empty_state_are_real(tmp_path):
    bar = build_bar(tmp_path)
    empty = today_snapshot(bar)
    assert empty["sales_today"] == 0
    assert empty["orders"] == []
    assert empty["top_products"] == []
    assert empty["category_sales"] == []

    water = product(bar, name="Agua", category="Bebidas", price=1000, stock=20)
    food = product(bar, name="Pancho", category="Comidas", price=3000, stock=20)
    first = bar.create_order(
        items=[{"product_id": water["product_id"], "quantity": 3}, {"product_id": food["product_id"], "quantity": 1}],
        origin="Mostrador", location="Mostrador",
    )
    bar.record_payment(first["order_id"], amount=6000, method="Efectivo")
    second = order(bar, water, quantity=2, origin="Mesa", location="Mesa 1")
    bar.record_payment(second["order_id"], amount=2000, method="Transferencia")

    snapshot = today_snapshot(bar)
    assert snapshot["sales_today"] == 8000
    assert snapshot["top_products"][0]["name"] == "Agua"
    assert snapshot["top_products"][0]["quantity"] == 5
    assert round(sum(row["percent"] for row in snapshot["category_sales"]), 1) == 100.0
    assert {row["name"] for row in snapshot["category_sales"]} == {"Bebidas", "Comidas"}


def test_ui_contract_places_bar_after_cash_and_keeps_inventory_actions_inside_panel():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src/cancheria/desktop/admin_panel.py").read_text(encoding="utf-8")
    assert source.index('self.notebook.add(self.cash_tab, text="Caja")') < source.index('self.notebook.add(self.bar_tab, text="Bar")') < source.index('self.notebook.add(self.operation_tab, text="Operación")')
    assert '"Bar": "☕"' in source
    assert 'ACTIVE_BG = "#1673FF"' in source
    assert "class BarButton(tk.Canvas)" in source
    assert '"Ventas de hoy"' in source
    assert '"Pedidos activos"' in source
    assert '"Productos bajos"' in source
    assert '"Pedidos del bar"' in source
    assert '"▥  Top productos"' in source
    assert '"◔  Ventas por categoría"' in source
    assert '"▲  Stock crítico / Inventario"' in source
    assert '"＋ Stock"' in source
    assert '"− Stock"' in source
    assert '"＋ Nuevo producto"' in source
    assert '"⊕  Nuevo pedido"' in source
    assert '"▣  Cobrar pedido"' in source
    assert '"▣  Registrar gasto"' in source


def test_bar_module_is_importable_for_windows_and_pyinstaller_collection():
    from cancheria.domain.bar import BarService as ImportedBarService
    from pathlib import Path

    assert ImportedBarService is BarService
    build_script = (Path(__file__).resolve().parents[2] / "build_windows.bat").read_text(encoding="utf-8")
    assert "--hidden-import cancheria.domain.bar.service" in build_script
    assert "--hidden-import cancheria.domain.finance.ledger" in build_script
