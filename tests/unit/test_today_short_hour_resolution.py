from __future__ import annotations

import datetime
import asyncio
import sys
from pathlib import Path


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


def test_exact_time_without_day_defaults_to_today_and_queries_only_16(
    monkeypatch,
) -> None:
    """Reproduce el chat real de las 12:22 sin API ni escritura persistente."""
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
    state["active_flow"] = "booking"
    state["booking"].update({
        "day": "Miércoles 07/10",
        "time": "18:00",
        "duration_hours": 1.0,
    })
    decision = {
        "operation": "query_availability",
        "confidence": 0.99,
        "booking": {
            "day": "Miércoles 07/10",
            "time": "16:00",
            "time_specificity": "exact",
            "time_source": "current_turn",
            "time_evidence": "las 4",
            "references_previous_time": False,
            "resource_type": None,
            "duration_hours": 1.0,
        },
        "context_resolution": {
            "relation": "continue_previous_availability",
            "inherit_fields": ["day", "duration_hours"],
            "replace_fields": ["time"],
        },
        "missing_fields": [],
        "_v213_current_turn_day_receipt": {
            "mode": "no_day_context",
            # Reproduce el log real del 08/10 13:48: no había fecha explícita,
            # pero la confianza del adjudicador quedó debajo del umbral.
            "validated": False,
            "prior_day": "Miércoles 07/10",
        },
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
    assert data["dia"] == "Jueves 08/10"
    assert data["hora"] == "16:00"
    assert "16" in result["response"]
    assert "Qué día" not in result["response"]


def test_resource_choice_question_uses_or_between_options() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    question = legacy._canonical_v183_missing_question("resource_type")

    assert " o " in question
    assert " y " not in question


def test_answering_today_keeps_exact_time_from_pending_day_question() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    state = legacy._canonical_v183_default_state("artificial-test")
    state["active_flow"] = "booking"
    state["booking"].update({
        "time": "16:00",
        "time_specificity": "exact",
        "resource_type": "Futbol 5",
        "duration_hours": 1.0,
    })
    state["pending"] = {
        "field": "dia",
        "time": "16:00",
        "time_specificity": "exact",
        "resource_type": "Futbol 5",
        "duration_hours": 1.0,
    }
    decision = {
        "operation": "query_availability",
        "booking": {
            "day": "Jueves 08/10",
            "time": None,
            "time_specificity": "none",
        },
        "context_resolution": {
            "relation": "continue_previous_availability",
            "inherit_fields": [],
            "replace_fields": ["day", "time"],
        },
        "_v213_current_turn_day_receipt": {
            "mode": "current_turn_explicit_day",
            "validated": True,
            "resolved_day": "Jueves 08/10",
            "evidence": "Hoy",
        },
        "_v188_actions": [{
            "operation": "query_availability",
            "booking": {"day": "Jueves 08/10", "time": None},
            "context_resolution": {"replace_fields": ["day", "time"]},
        }],
    }

    fixed = legacy._canonical_v223_restore_pending_time_after_day(decision, state)

    assert fixed["booking"]["time"] == "16:00"
    assert fixed["booking"]["time_specificity"] == "exact"
    assert fixed["booking"]["references_previous_time"] is True
    assert "time" not in fixed["context_resolution"]["replace_fields"]
    assert "time" in fixed["context_resolution"]["inherit_fields"]
    assert fixed["_v188_actions"][0]["booking"]["time"] == "16:00"


def test_explicit_future_day_is_never_replaced_by_implicit_today() -> None:
    from cancheria.legacy_bridge import load_legacy_module

    legacy = load_legacy_module()
    decision = {
        "operation": "query_availability",
        "booking": {
            "day": "Viernes 09/10",
            "time": "16:00",
            "time_specificity": "exact",
            "time_source": "current_turn",
            "time_evidence": "mañana a las 4",
        },
    }

    untouched = legacy._canonical_v223_apply_implicit_today_for_exact_time(
        decision,
        {"mode": "not_required", "validated": False},
        prior_day="",
    )

    assert untouched is decision
    assert untouched["booking"]["day"] == "Viernes 09/10"


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


def test_answering_only_sport_completes_hold_and_requests_receipt(monkeypatch) -> None:
    """Reproduce los dos turnos del 08/10 sin API, WhatsApp ni archivos reales."""
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
    decision = {
        "operation": "query_availability",
        "confidence": 0.9,
        "booking": {
            "day": "Jueves 08/10",
            "time": None,
            "resource_type": "Futbol 5",
            "resource_type_source": "current_turn",
            "resource_type_evidence": "Futbol",
            "duration_hours": 1.0,
        },
        "missing_fields": [],
        "context_resolution": {
            "relation": "continue_previous_availability",
            "inherit_fields": [],
            "replace_fields": ["resource_type"],
        },
        "_v205_current_turn_resource_receipt": {
            "explicit": True,
            "resource_type": "Futbol 5",
            "evidence": "Futbol",
        },
        "_v213_current_turn_day_receipt": {
            "mode": "references_previous_day",
            "validated": False,
        },
        "_v188_actions": [{
            "operation": "query_availability",
            "confidence": 0.9,
            "booking": {"day": "Jueves 08/10", "time": None},
        }],
    }

    fixed = legacy._canonical_v225_complete_pending_booking_resource(decision, state)
    assert fixed["operation"] == "create_booking"
    assert fixed["booking"]["day"] == "Jueves 08/10"
    assert fixed["booking"]["time"] == "16:00"
    assert fixed["booking"]["resource_type"] == "Futbol 5"
    assert fixed["_v188_actions"][0]["operation"] == "create_booking"

    async def fake_tool(name, args, *unused_args, **unused_kwargs):
        if name == "consultar_disponibilidad":
            return {
                "observation_id": "availability-test",
                "tool": name,
                "ok": True,
                "status": "success",
                "data": {
                    "dia": "Jueves 08/10",
                    "hora": "16:00",
                    "canchas_libres": ["Cancha 1", "Cancha 2"],
                    "auto_assigned_court": "Cancha 1",
                },
            }
        return {
            "observation_id": "booking-test",
            "tool": name,
            "ok": True,
            "status": "success",
            "data": {
                "reservation_id": "R-ARTIFICIAL",
                "dia": "Jueves 08/10",
                "hora": "16:00",
                "cancha": "Cancha 1",
                "duracion_horas": 1.0,
                "precio_total": 20000,
                "senia_monto": 10000,
                "monto_pendiente": 10000,
            },
        }

    monkeypatch.setattr(legacy, "ejecutar_tool_agent_v2", fake_tool)
    monkeypatch.setattr(legacy, "_canonical_v183_save", lambda *args, **kwargs: None)
    monkeypatch.setattr(legacy, "get_conversation_state", lambda *args, **kwargs: {})
    monkeypatch.setattr(legacy, "aplicar_observation_agent_v2", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        legacy,
        "construir_world_state_agent_v2",
        lambda *args, **kwargs: {"message": "Futbol", "facts": {}},
    )

    result = asyncio.run(
        legacy._canonical_v183_execute_booking(
            "Futbol",
            ["Futbol"],
            state,
            fixed,
            {"nombre": "Sebastian"},
            "artificial-test",
        )
    )

    assert result["handled"] is True
    assert [item["tool"] for item in result["observations"]] == [
        "consultar_disponibilidad",
        "crear_reserva",
    ]
    assert result["plan"]["steps"][1]["args"]["hora"] == "16:00"
    assert "16hs-17hs" in result["response"]
    assert "comprobante" in result["response"].casefold()
