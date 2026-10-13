from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _availability_action() -> dict:
    return {
        "operation": "query_availability",
        "confidence": 0.98,
        "intent_mode": "information",
        "booking": {
            "day": "Martes 13/10",
            "day_source": "current_turn",
            "day_evidence": "hoy",
            "time": None,
            "daypart": None,
            "time_specificity": "none",
            "time_source": "none",
            "time_evidence": None,
            "references_previous_time": False,
            "resource_type": "Futbol 5",
            "duration_hours": 1.0,
        },
        "missing_fields": [],
    }


def _business_info_action() -> dict:
    return {
        "operation": "business_info",
        "confidence": 0.97,
        "intent_mode": "information",
        "info": {
            "requested_facts": [
                "business.opening_hours",
                "service.loan_available",
            ],
            "target_resources": ["business", "service"],
            "target_labels": ["pelota"],
            "question_domains": ["attention_schedule", "service_policy"],
        },
        "missing_fields": [],
    }


def test_review_merge_preserves_independent_information_sibling() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    availability = _availability_action()
    business_info = _business_info_action()
    draft = {
        **business_info,
        "actions": [business_info, availability],
        "conversation_style": {
            "greeting_present": True,
            "greeting_evidence": "Hola",
        },
    }
    reviewed = {
        **availability,
        "actions": [],
        "conversation_style": {"greeting_present": False},
    }

    merged = legacy._canonical_v232_merge_review_coverage(reviewed, draft)

    assert merged["operation"] == "query_availability"
    assert [row["operation"] for row in merged["actions"]] == ["business_info"]
    assert merged["actions"][0]["info"]["question_domains"] == [
        "attention_schedule",
        "service_policy",
    ]
    assert merged["conversation_style"]["greeting_present"] is True
    assert merged["conversation_style"]["greeting_evidence"] == "Hola"


def test_two_pass_orchestrator_keeps_all_requests_from_multiple_messages(
    monkeypatch,
) -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    availability = _availability_action()
    business_info = _business_info_action()
    draft = {
        **business_info,
        "actions": [business_info, availability],
        "conversation_style": {
            "greeting_present": True,
            "greeting_evidence": "Hola",
        },
    }
    reviewed = {
        **availability,
        "actions": [],
        "conversation_style": {"greeting_present": True, "greeting_evidence": "Hola"},
    }
    payloads = []

    async def fake_openai(*_args, **kwargs):
        payloads.append(json.loads(kwargs["messages"][1]["content"]))
        content = draft if len(payloads) == 1 else reviewed
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(content)),
                finish_reason="stop",
            )],
            usage=None,
        )

    async def explicit_resource(*_args, **_kwargs):
        return {
            "explicit": True,
            "resource_type": "Futbol 5",
            "evidence": "cancha de futbol",
        }

    monkeypatch.setattr(legacy, "call_openai_async", fake_openai)
    monkeypatch.setattr(legacy, "register_cost", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        legacy,
        "_canonical_v205_current_turn_resource_receipt",
        explicit_resource,
    )

    messages = [
        "Hola, ¿tenés cancha de fútbol para hoy?",
        "¿Cuáles son los horarios de atención?",
        "¿Hace falta llevar pelota o prestan ustedes? Gracias",
    ]
    decision = asyncio.run(
        legacy._canonical_v184_orchestrate(
            "\n".join(messages),
            messages,
            legacy._canonical_v183_default_state("multi-intent-review"),
        )
    )

    assert len(payloads) == 2
    assert payloads[0]["latest_user_messages"] == messages
    assert payloads[1]["latest_user_messages"] == messages
    assert [row["operation"] for row in decision["_v188_actions"]] == [
        "query_availability",
        "business_info",
    ]
    info = decision["_v188_actions"][1]["info"]
    assert "attention_schedule" in info["question_domains"]
    assert "service_policy" in info["question_domains"]
    assert "business.opening_hours" in info["requested_facts"]
    assert "service.loan_available" in info["requested_facts"]
    assert decision["_v232_review_coverage_merged"] is True
