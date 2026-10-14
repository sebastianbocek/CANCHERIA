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


def test_live_canonical_entry_routes_fast_path_inventory_to_canonical_objectives(
    monkeypatch,
) -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    calls = {}
    messages = [
        "Hola, ¿tenés cancha de fútbol para hoy?",
        "¿Cuáles son los horarios de atención?",
        "¿Hace falta llevar pelota o prestan ustedes? Gracias",
    ]
    physical_turn = "\n".join(messages)

    async def fake_detector(message):
        calls["detected_message"] = message
        return [
            {"intencion": "pedir_horarios", "fragmento": messages[0]},
            {"intencion": "consulta_informativa", "fragmento": messages[1]},
            {"intencion": "consulta_informativa", "fragmento": messages[2]},
        ]

    async def fake_unified(**kwargs):
        calls["unified"] = kwargs
        return {
            "handled": True,
            "response": "disponibilidad\n\nhorarios de atención\n\npréstamo de pelota",
            "multi_subintent_bridge": {
                "version": "v235_canonical_objective_ledger",
                "subintent_count": 3,
            },
        }

    async def legacy_must_not_run(*_args, **_kwargs):
        raise AssertionError("El FAST PATH legacy no debe ejecutar este lote")

    monkeypatch.setattr(legacy, "detectar_multiples_intenciones", fake_detector)
    monkeypatch.setattr(
        legacy,
        "_ejecutar_agente_real_v2_turno_v184_legacy",
        legacy_must_not_run,
    )
    monkeypatch.setattr(
        legacy,
        "_canonical_v235_execute_objective_ledger",
        fake_unified,
    )

    result = asyncio.run(
        legacy.ejecutar_agente_real_v2_turno(
            physical_turn,
            {},
            {"nombre": "Sebastian"},
            "+5493513441882",
            user_messages=messages,
        )
    )

    assert calls["detected_message"] == physical_turn
    assert calls["unified"]["physical_turn"] == physical_turn
    assert calls["unified"]["subintents"] == [
        {"intencion": "pedir_horarios", "fragmento": messages[0]},
        {"intencion": "consulta_informativa", "fragmento": messages[1]},
        {"intencion": "consulta_informativa", "fragmento": messages[2]},
    ]
    assert result["handled"] is True
    assert result["multi_subintent_bridge"]["version"] == "v235_canonical_objective_ledger"
    assert result["multi_subintent_bridge"]["subintent_count"] == 3
    assert "disponibilidad" in result["response"]
    assert "horarios de atención" in result["response"]
    assert "préstamo de pelota" in result["response"]


def test_unified_objective_list_canonicalizes_executes_and_audits_every_request(
    monkeypatch,
) -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    fragments = [
        "Hola, ¿tenés cancha de fútbol para hoy?",
        "¿Cuáles son los horarios de atención?",
        "¿Hace falta llevar pelota o prestan ustedes? Gracias",
    ]
    subintents = [
        {"intencion": "pedir_horarios", "fragmento": fragments[0]},
        {"intencion": "consulta_informativa", "fragmento": fragments[1]},
        {"intencion": "consulta_informativa", "fragmento": fragments[2]},
    ]
    orchestrated = []
    executed = []

    async def fake_orchestrator(message, user_messages, state, image_path=""):
        orchestrated.append((message, list(user_messages), dict(state)))
        if message == fragments[0]:
            return _availability_action()
        fact = (
            "business.opening_hours"
            if message == fragments[1]
            else "service.loan_available"
        )
        action = _business_info_action()
        action["info"]["requested_facts"] = [fact]
        return action

    async def fake_executor(
        message,
        user_messages,
        state,
        decision,
        prospecto,
        telefono,
        page=None,
        image_path="",
    ):
        executed.append((message, decision["operation"], list(user_messages)))
        responses = {
            fragments[0]: "Disponibilidad confirmada.",
            fragments[1]: "Atendemos de 10:00 a 00:00.",
            fragments[2]: "Prestamos pelota sin cargo.",
        }
        return {
            "handled": True,
            "response": responses[message],
            "status": "complete",
            "observations": [],
        }

    monkeypatch.setattr(legacy, "_canonical_v184_orchestrate", fake_orchestrator)
    monkeypatch.setattr(legacy, "_canonical_v184_accept_decision", lambda _row: True)
    monkeypatch.setattr(
        legacy,
        "_canonical_v184_execute_decision_v212_base",
        fake_executor,
    )
    monkeypatch.setattr(legacy, "_canonical_v183_record_decision", lambda *_a, **_k: None)
    monkeypatch.setattr(legacy, "_canonical_v183_save", lambda *_a, **_k: None)
    monkeypatch.setattr(legacy, "get_conversation_state", lambda _phone: {})
    monkeypatch.setattr(
        legacy,
        "_canonical_v184_hydrate",
        lambda _phone, state, _prospect: dict(state),
    )

    result = asyncio.run(
        legacy._canonical_v235_execute_objective_ledger(
            physical_turn="\n".join(fragments),
            subintents=subintents,
            state={"shared_context": "preserved"},
            prospecto={"nombre": "Sebastian"},
            telefono="+5493513441882",
        )
    )

    assert [row[0] for row in orchestrated] == fragments
    assert all(row[1] == [row[0]] for row in orchestrated)
    assert all(row[2]["shared_context"] == "preserved" for row in orchestrated)
    assert [row[0] for row in executed] == fragments
    assert [row[1] for row in executed] == [
        "query_availability",
        "business_info",
        "business_info",
    ]
    assert result["objective_coverage"]["complete"] is True
    assert result["objective_coverage"]["missing_objective_ids"] == []
    assert len(result["canonical_objectives"]) == 3
    assert result["multi_subintent_bridge"] == {
        "version": "v235_canonical_objective_ledger",
        "subintent_count": 3,
        "canonical_objective_count": 3,
        "canonical_action_count": 3,
        "partial_response_count": 3,
        "all_subintent_responses_preserved": True,
    }
    assert result["response"] == (
        "Disponibilidad confirmada.\n\n"
        "Atendemos de 10:00 a 00:00.\n\n"
        "Prestamos pelota sin cargo."
    )


def test_unified_objective_list_does_not_emit_incomplete_response(monkeypatch) -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    subintents = [
        {"intencion": "consulta_informativa", "fragmento": "horarios"},
        {"intencion": "consulta_informativa", "fragmento": "pelota"},
    ]

    async def fake_orchestrator(message, user_messages, state, image_path=""):
        action = _business_info_action()
        action["info"]["requested_facts"] = [message]
        return action

    async def fake_executor(message, *_args, **_kwargs):
        return {
            "handled": True,
            "response": "Atendemos todos los días." if message == "horarios" else "",
            "status": "complete",
            "observations": [],
        }

    monkeypatch.setattr(legacy, "_canonical_v184_orchestrate", fake_orchestrator)
    monkeypatch.setattr(legacy, "_canonical_v184_accept_decision", lambda _row: True)
    monkeypatch.setattr(
        legacy,
        "_canonical_v184_execute_decision_v212_base",
        fake_executor,
    )
    monkeypatch.setattr(legacy, "_canonical_v183_record_decision", lambda *_a, **_k: None)
    monkeypatch.setattr(legacy, "_canonical_v183_save", lambda *_a, **_k: None)
    monkeypatch.setattr(legacy, "get_conversation_state", lambda _phone: {})
    monkeypatch.setattr(
        legacy,
        "_canonical_v184_hydrate",
        lambda _phone, state, _prospect: dict(state),
    )

    result = asyncio.run(
        legacy._canonical_v235_execute_objective_ledger(
            physical_turn="horarios y pelota",
            subintents=subintents,
            state={},
            prospecto={},
            telefono="+5493513441882",
        )
    )

    assert result is None


def test_live_entry_never_falls_back_to_legacy_executor_for_multi_intent(
    monkeypatch,
) -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    messages = ["consultá disponibilidad", "y decime si prestan pelota"]

    async def fake_detector(_message):
        return [
            {"intencion": "pedir_horarios", "fragmento": messages[0]},
            {"intencion": "consulta_informativa", "fragmento": messages[1]},
        ]

    async def incomplete_unified(**_kwargs):
        return None

    async def legacy_must_not_run(*_args, **_kwargs):
        raise AssertionError("FAST PATH no debe volver a ejecutar objetivos")

    async def fake_safe_failure(**kwargs):
        return {
            "handled": True,
            "silent_handoff": True,
            "source": kwargs["source"],
        }

    monkeypatch.setattr(legacy, "detectar_multiples_intenciones", fake_detector)
    monkeypatch.setattr(
        legacy,
        "_canonical_v235_execute_objective_ledger",
        incomplete_unified,
    )
    monkeypatch.setattr(
        legacy,
        "_ejecutar_agente_real_v2_turno_v184_legacy",
        legacy_must_not_run,
    )
    monkeypatch.setattr(legacy, "_canonical_v184_silent_failure", fake_safe_failure)

    result = asyncio.run(
        legacy.ejecutar_agente_real_v2_turno(
            "\n".join(messages),
            {},
            {},
            "+5493513441882",
            user_messages=messages,
        )
    )

    assert result["handled"] is True
    assert result["silent_handoff"] is True
    assert result["source"] == "canonical_v235_objective_planning_incomplete"


def test_semantic_review_cannot_delete_a_fast_path_obligation(monkeypatch) -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    message = (
        "Hola tenes cancha de futbol para hoy? y cuales horarios de atencion tienen?\n"
        "hace falta llevar pelota o prestan ustedes?\n"
        "se puede reservar 2 canchas 3 horas?"
    )
    initial = [
        {
            "intencion": "pedir_horarios",
            "fragmento": "Hola tenes cancha de futbol para hoy? y cuales horarios de atencion tienen?",
        },
        {
            "intencion": "consulta_informativa",
            "fragmento": "hace falta llevar pelota o prestan ustedes?",
        },
        {
            "intencion": "reservar_cancha",
            "fragmento": "se puede reservar 2 canchas 3 horas?",
        },
    ]
    destructive_review = {
        "intenciones": [
            {
                "intencion": "consulta_informativa",
                "fragmento": "cuales horarios de atencion tienen?",
            },
            initial[1],
            initial[2],
        ],
        "reason": "review perdió disponibilidad",
    }

    async def fake_openai(*_args, **_kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(destructive_review)),
                finish_reason="stop",
            )],
            usage=None,
        )

    monkeypatch.setattr(legacy, "call_openai_async", fake_openai)
    monkeypatch.setattr(legacy, "register_cost", lambda *_args, **_kwargs: None)

    ledger = asyncio.run(
        legacy._agent_v2_v126r5_audit_subintent_coverage(message, initial)
    )

    fragments = [row["fragmento"] for row in ledger]
    assert initial[0]["fragmento"] in fragments
    assert "cuales horarios de atencion tienen?" in fragments
    assert len(ledger) == 4
    assert all(row.get("discovery_id") for row in ledger)


def test_semantic_review_can_expand_a_single_compressed_fast_path_row(
    monkeypatch,
) -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    message = "tenes cancha para hoy y cuales son los horarios de atencion?"
    initial = [{"intencion": "pedir_horarios", "fragmento": message}]
    review = {
        "intenciones": [
            {
                "intencion": "pedir_horarios",
                "fragmento": "tenes cancha para hoy",
            },
            {
                "intencion": "consulta_informativa",
                "fragmento": "cuales son los horarios de atencion?",
            },
        ]
    }

    async def fake_openai(*_args, **_kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(review)),
                finish_reason="stop",
            )],
            usage=None,
        )

    monkeypatch.setattr(legacy, "call_openai_async", fake_openai)
    monkeypatch.setattr(legacy, "register_cost", lambda *_args, **_kwargs: None)

    ledger = asyncio.run(
        legacy._agent_v2_v126r5_audit_subintent_coverage(message, initial)
    )

    assert [row["intencion"] for row in ledger] == [
        "pedir_horarios",
        "pedir_horarios",
        "consulta_informativa",
    ]
    assert ledger[0]["fragmento"] == message
    assert ledger[1]["discovery_source"] == "semantic_review"


def test_objective_ledger_keeps_availability_when_duration_is_invalid(
    monkeypatch,
) -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    combined = "Hola tenes cancha de futbol para hoy? y cuales horarios de atencion tienen?"
    hours = "cuales horarios de atencion tienen?"
    ball = "hace falta llevar pelota o prestan ustedes?"
    duration = "se puede reservar 2 canchas 3 horas?"
    physical_turn = "\n".join([combined, ball, duration])
    subintents = [
        {"intencion": "pedir_horarios", "fragmento": combined},
        {"intencion": "consulta_informativa", "fragmento": ball},
        {"intencion": "reservar_cancha", "fragmento": duration},
        {"intencion": "consulta_informativa", "fragmento": hours},
    ]

    availability = _availability_action()
    combined_info = _business_info_action()
    combined_info["info"]["requested_facts"] = [
        "business.opening_hours",
        "service.loan_available",
    ]

    def info_action(fact, domain, *, requested_durations=None):
        action = _business_info_action()
        action["info"]["requested_facts"] = [fact]
        action["info"]["question_domains"] = [domain]
        action["info"]["target_labels"] = []
        if requested_durations:
            action["info"]["requested_durations"] = requested_durations
        return action

    async def fake_orchestrator(message, _user_messages, _state, image_path=""):
        if message == combined:
            return {
                **availability,
                "_v188_actions": [availability, combined_info],
            }
        if message == hours:
            return info_action("business.opening_hours", "attention_schedule")
        if message == ball:
            return info_action("service.loan_available", "service_policy")
        return info_action(
            "booking.allowed_durations",
            "duration_policy",
            requested_durations=[3],
        )

    executed = []

    async def fake_executor(
        message,
        _user_messages,
        _state,
        decision,
        *_args,
        **_kwargs,
    ):
        operation = decision["operation"]
        executed.append(operation)
        if operation == "query_availability":
            response = "Disponibilidad: 19:00, 20:00 y 21:00."
        elif "booking.allowed_durations" in (decision.get("info") or {}).get("requested_facts", []):
            response = "No, 3 horas no está habilitada."
        else:
            response = "Atendemos de 10:00 a 00:00 y prestamos pelota."
        return {
            "handled": True,
            "response": response,
            "status": "complete",
            "observations": [],
        }

    monkeypatch.setattr(legacy, "_canonical_v184_orchestrate", fake_orchestrator)
    monkeypatch.setattr(legacy, "_canonical_v184_accept_decision", lambda _row: True)
    monkeypatch.setattr(legacy, "_canonical_v184_execute_decision_v212_base", fake_executor)
    monkeypatch.setattr(legacy, "_canonical_v183_record_decision", lambda *_a, **_k: None)
    monkeypatch.setattr(legacy, "_canonical_v183_save", lambda *_a, **_k: None)
    monkeypatch.setattr(legacy, "get_conversation_state", lambda _phone: {})
    monkeypatch.setattr(
        legacy,
        "_canonical_v184_hydrate",
        lambda _phone, state, _prospect: dict(state),
    )

    result = asyncio.run(
        legacy._canonical_v235_execute_objective_ledger(
            physical_turn=physical_turn,
            subintents=subintents,
            state={},
            prospecto={},
            telefono="+5493513441882",
        )
    )

    assert executed == ["query_availability", "business_info", "business_info"]
    assert "Disponibilidad" in result["response"]
    assert "prestamos pelota" in result["response"]
    assert "3 horas no está habilitada" in result["response"]
    assert result["objective_coverage"]["complete"] is True
    assert result["objective_coverage"]["missing_action_ids"] == []
    assert len(result["objective_coverage"]["response_objective_ids"]) == 4
