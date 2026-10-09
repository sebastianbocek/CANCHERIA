from __future__ import annotations

import datetime
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_late_today_short_hour_uses_only_future_12h_equivalent() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    reference = legacy.TIMEZONE.localize(datetime.datetime(2026, 10, 6, 22, 45))

    resolved = legacy._agent_v2_resolve_short_clock_operationally(
        "hay cancha de fútbol para hoy a las 11",
        "Martes 06/10",
        reference_now=reference,
    )
    explicit_morning = legacy._agent_v2_resolve_short_clock_operationally(
        "hay cancha de fútbol para hoy a las 11 de la mañana",
        "Martes 06/10",
        reference_now=reference,
    )
    future_day = legacy._agent_v2_resolve_short_clock_operationally(
        "hay cancha de fútbol mañana a las 11",
        "Miércoles 07/10",
        reference_now=reference,
    )

    assert resolved == {
        "detectada": True,
        "requiere_aclaracion": False,
        "hora": "23:00",
        "opciones": ["23:00"],
        "source": "short_hour_operational_feasibility",
        "day_hint": "Martes 06/10",
    }
    assert explicit_morning["detectada"] is False
    assert future_day["hora"] == "11:00"


def test_canonical_fast_path_resolves_late_today_before_tool_execution() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    reference = legacy.TIMEZONE.localize(datetime.datetime(2026, 10, 6, 22, 55))

    resolved = legacy._canonical_v219_resolve_current_exact_hour(
        "Hola, ¿hay cancha de fútbol para hoy a las 11?",
        "Martes 06/10",
        "11:00",
        specificity="exact",
        time_source="current_turn",
        reference_now=reference,
    )
    explicit_morning = legacy._canonical_v219_resolve_current_exact_hour(
        "Hola, ¿hay cancha de fútbol para hoy a las 11 de la mañana?",
        "Martes 06/10",
        "11:00",
        specificity="exact",
        time_source="current_turn",
        reference_now=reference,
    )

    assert resolved["hour"] == "23:00"
    assert resolved["changed"] is True
    assert resolved["source"] == "short_hour_operational_feasibility"
    assert explicit_morning["hour"] == "11:00"
    assert explicit_morning["changed"] is False


def test_artificial_2255_canonical_flow_queries_real_calendar_tool_at_23(
    monkeypatch,
) -> None:
    """Recorre V184/V186 hasta la tool real sin escribir estado ni reservas."""
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    real_datetime = datetime.datetime
    real_date = datetime.date

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            value = real_datetime(2026, 10, 6, 22, 55)
            if tz is None:
                return value
            if hasattr(tz, "localize"):
                return tz.localize(value)
            return value.replace(tzinfo=tz)

    class FrozenDate(real_date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 6)

    monkeypatch.setattr(legacy.datetime, "datetime", FrozenDateTime)
    monkeypatch.setattr(legacy.datetime, "date", FrozenDate)
    monkeypatch.setattr(legacy.calendario, "_esta_reservado", lambda *args, **kwargs: False)
    monkeypatch.setattr(legacy, "_canonical_v183_save", lambda *args, **kwargs: None)
    monkeypatch.setattr(legacy, "get_conversation_state", lambda *args, **kwargs: {})
    monkeypatch.setattr(legacy, "aplicar_observation_agent_v2", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        legacy,
        "construir_world_state_agent_v2",
        lambda telefono, prospecto, state, message, image_path="": {
            "message": message,
            "facts": {"reservas_reales": []},
            "active_goals": [],
            "current_scope_id": "artificial-2255",
        },
    )

    message = "Hola, ¿hay cancha de fútbol para hoy a las 11?"
    state = legacy._canonical_v183_default_state("artificial-test")
    decision = {
        "operation": "query_availability",
        "confidence": 0.99,
        "booking": {
            "day": "Martes 06/10",
            "time": "11:00",
            "time_specificity": "exact",
            "time_source": "current_turn",
            "time_evidence": "a las 11",
            "references_previous_time": False,
            "resource_type": "Futbol 5",
            "duration_hours": 1.0,
        },
        "missing_fields": [],
    }

    result = asyncio.run(
        legacy._canonical_v184_execute_availability(
            message,
            [message],
            state,
            decision,
            {"nombre": "Prueba artificial"},
            "artificial-test",
        )
    )

    observation = result["observations"][0]
    data = observation["data"]
    assert result["handled"] is True
    assert observation["tool"] == "consultar_disponibilidad"
    assert observation["ok"] is True
    assert data["dia"] == "Martes 06/10"
    assert data["hora"] == "23:00"
    assert data["canchas_libres"] == ["Cancha 1", "Cancha 2"]
    assert decision["booking"]["time"] == "23:00"
    assert "23" in result["response"]


def test_exact_time_without_day_defaults_to_today_and_asks_only_sport(
    monkeypatch,
) -> None:
    """Ejecuta el goal completo que reconstruyó la IA, sin parche de campos."""
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    real_datetime = datetime.datetime
    real_date = datetime.date

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            value = real_datetime(2026, 10, 8, 12, 22)
            if tz is None:
                return value
            if hasattr(tz, "localize"):
                return tz.localize(value)
            return value.replace(tzinfo=tz)

    class FrozenDate(real_date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 8)

    monkeypatch.setattr(legacy.datetime, "datetime", FrozenDateTime)
    monkeypatch.setattr(legacy.datetime, "date", FrozenDate)
    monkeypatch.setattr(legacy.calendario, "_esta_reservado", lambda *args, **kwargs: False)
    monkeypatch.setattr(legacy, "_canonical_v183_save", lambda *args, **kwargs: None)
    monkeypatch.setattr(legacy, "get_conversation_state", lambda *args, **kwargs: {})
    monkeypatch.setattr(legacy, "aplicar_observation_agent_v2", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        legacy,
        "construir_world_state_agent_v2",
        lambda telefono, prospecto, state, message, image_path="": {
            "message": message,
            "facts": {"reservas_reales": []},
            "active_goals": [],
            "current_scope_id": "artificial-1222",
        },
    )

    message = "Hola tenes cancha para las 4"
    state = legacy._canonical_v183_default_state("artificial-test")
    decision = {
        "operation": "create_booking",
        "confidence": 0.99,
        "intent_mode": "transaction",
        "booking": {
            "day": "Jueves 08/10",
            "time": "16:00",
            "time_specificity": "exact",
            "time_source": "current_turn",
            "time_evidence": "las 4",
            "references_previous_time": False,
            "resource_type": None,
            "duration_hours": 1.0,
        },
        "context_resolution": {
            "relation": "new_request",
            "inherit_fields": [],
            "replace_fields": [],
        },
        "goal_reconstruction": {
            "goal": "crear_reserva",
            "known_fields": {"day": "Jueves 08/10", "time": "16:00"},
            "missing_fields": ["resource_type"],
            "ready_for_execution": False,
        },
        "missing_fields": ["resource_type"],
    }

    result = asyncio.run(
        legacy._canonical_v184_execute_booking(
            message,
            [message],
            state,
            decision,
            {"nombre": "Prueba artificial"},
            "artificial-test",
        )
    )

    assert result["handled"] is True
    assert result["status"] == "waiting_user"
    assert result["observations"] == []
    assert "Qué querés reservar" in result["response"]
    assert "Qué día" not in result["response"]
    assert decision.get("_v223_implicit_today") is None
    assert decision.get("_v228_exact_slot_booking_goal") is None


def test_resource_choice_question_uses_or_between_options() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    question = legacy._canonical_v183_missing_question("resource_type")

    assert " o " in question
    assert " y " not in question


def test_canonical_pending_booking_wins_over_stale_legacy_draft(monkeypatch) -> None:
    """El draft viejo no puede reemplazar el slot que acaba de preguntar V183."""
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    state = legacy._canonical_v183_default_state("artificial-test")
    state["active_flow"] = "booking"
    state["booking"].update({
        "day": "Jueves 08/10",
        "time": "16:00",
        "time_specificity": "exact",
        "duration_hours": 1.0,
    })
    state["pending"] = {
        "type": "booking_question",
        "field": "resource_type",
        "day": "Jueves 08/10",
        "time": "16:00",
        "time_specificity": "exact",
        "duration_hours": 1.0,
        "operation": "create_booking",
        "source": "canonical_v225_booking_question",
        "goal_context": ["crear_reserva"],
    }
    stale_agent_state = {
        "availability_context": {},
        "desires": {
            "booking_draft": {
                "dia": "Miércoles 07/10",
                "hora": "18:00",
            }
        },
        "open_questions": [],
    }

    monkeypatch.setattr(legacy, "_canonical_v183_load", lambda owner: state)
    monkeypatch.setattr(legacy, "_canonical_v183_save", lambda owner, value: value)
    monkeypatch.setattr(legacy, "_agent_v2_state", lambda conv: stale_agent_state)

    hydrated = legacy._canonical_v183_hydrate_from_legacy(
        "artificial-test", {"historial": []}
    )

    assert hydrated["booking"]["day"] == "Jueves 08/10"
    assert hydrated["booking"]["time"] == "16:00"
    assert hydrated["pending"]["field"] == "resource_type"


def test_expired_hold_ai_recovery_rebuilds_exact_slot_and_asks_only_sport(
    monkeypatch,
) -> None:
    """Reproduce el incidente real 08/10 19:51 sin red ni calendario."""
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    real_datetime = datetime.datetime
    captured_payloads = []

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            value = real_datetime(2026, 10, 8, 19, 51)
            if tz is None:
                return value
            if hasattr(tz, "localize"):
                return tz.localize(value)
            return value.replace(tzinfo=tz)

    async def fake_openai(*_args, **kwargs):
        captured_payloads.append(json.loads(kwargs["messages"][1]["content"]))
        content = json.dumps({
            "operation": "create_booking",
            "confidence": 0.96,
            "intent_mode": "transaction",
            "booking": {
                "day": "Jueves 08/10",
                "time": "21:00",
                "daypart": None,
                "time_specificity": "exact",
                "time_source": "current_turn",
                "time_evidence": "las 21",
                "references_previous_time": False,
                "resource_type": None,
                "duration_hours": 1.0,
            },
            "context_resolution": {
                "relation": "new_request",
                "effective_operation": "create_booking",
                "inherit_fields": [],
                "replace_fields": ["time"],
            },
            "goal_reconstruction": {
                "goal": "crear_reserva",
                "known_fields": {"day": "Jueves 08/10", "time": "21:00"},
                "missing_fields": ["resource_type"],
                "ready_for_execution": False,
            },
            "missing_fields": ["resource_type"],
            "actions": [],
        })
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )],
            usage=None,
        )

    async def no_day_context(*_args, **_kwargs):
        return {
            "mode": "no_day_context",
            "validated": True,
            "resolved_day": None,
            "evidence": None,
        }

    monkeypatch.setattr(legacy.datetime, "datetime", FrozenDateTime)
    monkeypatch.setattr(legacy, "call_openai_async", fake_openai)
    monkeypatch.setattr(legacy, "register_cost", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        legacy, "_canonical_v200_adjudicate_current_turn_day", no_day_context
    )

    state = legacy._canonical_v183_default_state("artificial-test")
    state["recent_messages"] = [
        {"role": "user", "content": "Necesito cambiar un turno viejo"},
        {"role": "assistant", "content": "Ese hold ya venció."},
    ]
    state["last_decision"] = {"operation": "replace_pending_booking"}
    recovered = asyncio.run(
        legacy._canonical_v204_recover_without_active_pending_hold(
            "Hola tenes cancha para las 21",
            ["Hola tenes cancha para las 21"],
            state,
        )
    )

    assert recovered["operation"] == "create_booking"
    assert recovered["booking"]["day"] == "Jueves 08/10"
    assert recovered["booking"]["time"] == "21:00"
    assert recovered["missing_fields"] == ["resource_type"]
    assert captured_payloads[0]["recent_messages"] == state["recent_messages"]
    assert captured_payloads[0]["operational_history"]["last_decision"] == {
        "operation": "replace_pending_booking"
    }

    saved_states = []
    monkeypatch.setattr(
        legacy,
        "_canonical_v183_save",
        lambda _owner, value: saved_states.append(value) or value,
    )
    result = asyncio.run(
        legacy._canonical_v184_execute_booking(
            "Hola tenes cancha para las 21",
            ["Hola tenes cancha para las 21"],
            state,
            recovered,
            {"nombre": "Sebastian"},
            "artificial-test",
        )
    )
    assert result["status"] == "waiting_user"
    assert "Qué querés reservar" in result["response"]
    assert "Qué día" not in result["response"]
    saved_pending = next(
        item["pending"]
        for item in reversed(saved_states)
        if isinstance(item.get("pending"), dict)
    )
    assert saved_pending["field"] == "resource_type"
    assert saved_pending["time"] == "21:00"


def test_ai_reconstructs_complete_goal_when_hour_arrives_last(monkeypatch) -> None:
    """La IA reúne el historial completo; Python no promueve campos por orden."""
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    captured = {}
    ai_decision = {
        "operation": "create_booking",
        "confidence": 0.98,
        "intent_mode": "continuation",
        "booking": {
            "day": "Viernes 09/10",
            "time": "21:00",
            "daypart": None,
            "time_specificity": "exact",
            "time_source": "current_turn",
            "time_evidence": "21",
            "references_previous_time": False,
            "resource_type": "Futbol 5",
            "duration_hours": 1.0,
        },
        "context_resolution": {
            "relation": "continue_previous_availability",
            "effective_operation": "create_booking",
            "inherit_fields": ["day", "resource_type", "duration_hours"],
            "replace_fields": ["time"],
            "evidence": "21",
        },
        "goal_reconstruction": {
            "goal": "crear_reserva",
            "known_fields": {
                "day": "Viernes 09/10",
                "time": "21:00",
                "resource_type": "Futbol 5",
            },
            "missing_fields": [],
            "ready_for_execution": True,
            "summary": "Reserva lista para validar",
        },
        "missing_fields": [],
        "actions": [],
    }

    async def fake_openai(*_args, **kwargs):
        captured["system"] = kwargs["messages"][0]["content"]
        captured["payload"] = json.loads(kwargs["messages"][1]["content"])
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(ai_decision)),
                finish_reason="stop",
            )],
            usage=None,
        )

    async def no_resource(*_args, **_kwargs):
        return {"explicit": False, "resource_type": None, "evidence": None}

    async def references_prior_day(*_args, **_kwargs):
        return {
            "mode": "references_previous_day",
            "validated": True,
            "resolved_day": "Viernes 09/10",
            "evidence": None,
        }

    monkeypatch.setattr(legacy, "call_openai_async", fake_openai)
    monkeypatch.setattr(legacy, "register_cost", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(legacy, "_canonical_v205_current_turn_resource_receipt", no_resource)
    monkeypatch.setattr(legacy, "_canonical_v200_adjudicate_current_turn_day", references_prior_day)

    state = legacy._canonical_v183_default_state("artificial-test")
    state["booking"].update({
        "day": "Viernes 09/10",
        "resource_type": "Futbol 5",
        "duration_hours": 1.0,
    })
    state["pending"] = {"field": "hora", "type": "booking_question"}
    state["recent_messages"] = [
        {"role": "user", "content": "Quiero fútbol mañana"},
        {"role": "assistant", "content": "¿Qué hora te sirve?"},
    ]

    decision = asyncio.run(
        legacy._canonical_v184_orchestrate("21", ["21"], state)
    )

    assert decision["operation"] == "create_booking"
    assert decision["booking"]["day"] == "Viernes 09/10"
    assert decision["booking"]["time"] == "21:00"
    assert decision["booking"]["resource_type"] == "Futbol 5"
    assert decision["goal_reconstruction"]["ready_for_execution"] is True
    assert decision.get("_v229_pending_field_completed") is None
    assert captured["payload"]["recent_messages"] == state["recent_messages"]
    assert captured["payload"]["operational_history"]["pending_action"]["field"] == "hora"
    assert "no existe una secuencia programada" in captured["system"].casefold()


def test_ai_reconstructs_complete_goal_when_day_arrives_last(monkeypatch) -> None:
    """La misma reconstrucción funciona sin codificar una secuencia inversa."""
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    ai_decision = {
        "operation": "create_booking",
        "confidence": 0.98,
        "intent_mode": "continuation",
        "booking": {
            "day": "Viernes 09/10",
            "time": "21:00",
            "daypart": None,
            "time_specificity": "exact",
            "time_source": "canonical_state",
            "time_evidence": None,
            "references_previous_time": True,
            "resource_type": "Futbol 5",
            "duration_hours": 1.0,
        },
        "context_resolution": {
            "relation": "continue_previous_availability",
            "effective_operation": "create_booking",
            "inherit_fields": ["time", "resource_type", "duration_hours"],
            "replace_fields": ["day"],
            "evidence": "Mañana",
        },
        "goal_reconstruction": {
            "goal": "crear_reserva",
            "known_fields": {
                "day": "Viernes 09/10",
                "time": "21:00",
                "resource_type": "Futbol 5",
            },
            "missing_fields": [],
            "ready_for_execution": True,
            "summary": "Reserva lista para validar",
        },
        "missing_fields": [],
        "actions": [],
    }

    async def fake_openai(*_args, **_kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(ai_decision)),
                finish_reason="stop",
            )],
            usage=None,
        )

    async def no_resource(*_args, **_kwargs):
        return {"explicit": False, "resource_type": None, "evidence": None}

    monkeypatch.setattr(legacy, "call_openai_async", fake_openai)
    monkeypatch.setattr(legacy, "register_cost", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(legacy, "_canonical_v205_current_turn_resource_receipt", no_resource)

    state = legacy._canonical_v183_default_state("artificial-test")
    state["booking"].update({
        "time": "21:00",
        "time_specificity": "exact",
        "resource_type": "Futbol 5",
        "duration_hours": 1.0,
    })
    state["pending"] = {"field": "dia", "type": "booking_question"}
    state["recent_messages"] = [
        {"role": "user", "content": "Quiero fútbol a las 21"},
        {"role": "assistant", "content": "¿Qué día te gustaría reservar?"},
    ]

    decision = asyncio.run(
        legacy._canonical_v184_orchestrate("Mañana", ["Mañana"], state)
    )

    assert decision["operation"] == "create_booking"
    assert decision["booking"]["day"] == "Viernes 09/10"
    assert decision["booking"]["time"] == "21:00"
    assert decision["booking"]["resource_type"] == "Futbol 5"
    assert decision["missing_fields"] == []
    assert decision.get("_v229_pending_field_completed") is None
