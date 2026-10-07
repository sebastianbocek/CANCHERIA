import importlib


def test_event_registration_transaction_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("CANCHERIA_RUNTIME_DIR", str(tmp_path))
    from cancheria.domain.events import registration
    importlib.reload(registration)

    configured = registration.configure_business_event(
        "Demo Cup", 10000, 4, "2030-01-20", payment_alias="DEMO.ALIAS"
    )
    event = configured["event"]
    hold = registration.create_event_registration_hold(
        event, "Demo Team", "Demo Contact", "+15550000002"
    )
    assert hold["registration"]["status"] == "pending_payment"
    assert registration.get_event_capacity_state(event)["active_holds"] == 1

    paid = registration.register_event_payment(
        event, hold["registration"]["registration_id"], 10000,
        receipt_fingerprint="fixture-receipt-001",
    )
    assert paid["registration"]["status"] == "confirmed"
    assert paid["registration"]["remaining_amount"] == 0
