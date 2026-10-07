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
