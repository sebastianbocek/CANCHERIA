from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _booking_partial_state():
    return {
        "reservations": [
            {
                "reservation_id": "3",
                "deposit_status": "parcial",
                "deposit_required": 10000,
                "deposit_paid": 7500,
                "deposit_pending": 2500,
            }
        ],
        "event_registration": {},
    }


def _event_partial_state():
    return {
        "reservations": [],
        "event_registration": {
            "event_id": "event-1",
            "event_name": "Copa CANCHERIA",
            "event_date": "2026-10-20",
            "team_name": "Los QA",
            "registration_id": "registration-1",
            "status": "pending_payment",
            "paid_amount": 7500,
            "remaining_amount": 2500,
        },
    }


def test_cash_remainder_is_bound_to_real_partial_booking() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    decision = {
        "operation": "choose_event_cash",
        "confidence": 1.0,
        "event": {},
        "reservation": {},
        "context_resolution": {
            "relation": "continue_previous_booking",
            "effective_operation": "choose_event_cash",
        },
        "actions": [{"operation": "choose_event_cash", "event": {}}],
        "_v188_actions": [{"operation": "choose_event_cash", "event": {}}],
    }

    fixed = legacy._canonical_v227_bind_cash_to_partial_obligation(
        decision, _booking_partial_state()
    )

    assert fixed["operation"] == "choose_booking_cash"
    assert fixed["reservation"]["reservation_id"] == "3"
    assert fixed["context_resolution"]["effective_operation"] == "choose_booking_cash"
    assert fixed["actions"][0]["operation"] == "choose_booking_cash"
    assert fixed["actions"][0]["reservation"]["reservation_id"] == "3"
    assert fixed["_v188_actions"][0]["operation"] == "choose_booking_cash"
    assert decision["operation"] == "choose_event_cash"


def test_cash_remainder_is_bound_to_real_partial_event_registration() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    fixed = legacy._canonical_v227_bind_cash_to_partial_obligation(
        {
            "operation": "choose_booking_cash",
            "confidence": 0.9,
            "event": {},
            "reservation": {},
            "actions": [{"operation": "choose_booking_cash"}],
        },
        _event_partial_state(),
    )

    assert fixed["operation"] == "choose_event_cash"
    assert fixed["event"]["event_id"] == "event-1"
    assert fixed["event"]["registration_id"] == "registration-1"
    assert fixed["actions"][0]["operation"] == "choose_event_cash"
    assert fixed["actions"][0]["event"]["registration_id"] == "registration-1"


def test_cash_binding_fails_closed_when_both_domains_have_partial_balances() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    state = _booking_partial_state()
    state["event_registration"] = _event_partial_state()["event_registration"]
    decision = {"operation": "choose_event_cash", "confidence": 1.0}

    assert (
        legacy._canonical_v227_bind_cash_to_partial_obligation(decision, state)
        == decision
    )


def test_final_orchestrator_repairs_the_exact_production_misroute(monkeypatch) -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()

    async def wrong_domain(*_args, **_kwargs):
        return {
            "operation": "choose_event_cash",
            "confidence": 1.0,
            "event": {},
            "reservation": {},
            "actions": [{"operation": "choose_event_cash", "event": {}}],
            "_v188_actions": [{"operation": "choose_event_cash", "event": {}}],
            "missing_fields": [],
        }

    monkeypatch.setattr(legacy, "_canonical_v184_orchestrate_v227_base", wrong_domain)
    result = asyncio.run(
        legacy._canonical_v184_orchestrate(
            "Pago el resto en efectivo",
            ["Pago el resto en efectivo"],
            _booking_partial_state(),
        )
    )

    assert result["operation"] == "choose_booking_cash"
    assert result["reservation"]["reservation_id"] == "3"
    assert all(
        action["operation"] == "choose_booking_cash"
        for action in result["_v188_actions"]
    )


def test_invalid_event_cash_never_asks_generic_tournament_question(monkeypatch) -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    captured = {}

    async def silent_failure(**kwargs):
        captured.update(kwargs)
        return {
            "handled": True,
            "response": "",
            "silent_handoff": True,
            "status": "complete",
            "observations": [],
        }

    monkeypatch.setattr(legacy, "_canonical_v184_silent_failure", silent_failure)
    result = asyncio.run(
        legacy._canonical_v184_execute_event(
            "choose_event_cash",
            "Pago el resto en efectivo",
            ["Pago el resto en efectivo"],
            {"event_registration": {}},
            {"operation": "choose_event_cash", "event": {}},
            {"nombre": "QA"},
            "+5491100000000",
        )
    )

    assert result["silent_handoff"] is True
    assert result["response"] == ""
    assert captured["source"] == "event_cash_without_grounded_registration"


def test_canonical_cash_tool_contract_is_frozen_and_explicit() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    perception = legacy._canonical_v184_tool_perception(
        "choose_booking_cash",
        "registrar_pago_presencial",
        {"reservation_id": "3"},
        _booking_partial_state(),
        "Pago el resto en efectivo",
    )

    contract = perception["execution_contract"]
    act = contract["acts"][0]
    assert contract["frozen"] is True
    assert contract["authoritative"] is True
    assert act["operation"] == "choose_payment_method"
    assert act["changes"] == [
        {
            "field": "payment_method",
            "value": "cash",
            "operation": "set",
            "source": "current_user_turn",
            "evidence": "Pago el resto en efectivo",
        }
    ]
