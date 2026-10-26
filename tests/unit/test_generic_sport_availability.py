from __future__ import annotations

import copy
from pathlib import Path

import legacy.WPSetter_legacy as agent


def test_generic_sport_receipt_preserves_all_compatible_configured_modalities(monkeypatch):
    monkeypatch.setattr(agent, "COURTS", [
        {"name": "Cancha 1", "type": "Futbol 5"},
        {"name": "Cancha 2", "type": "Futbol 7"},
        {"name": "Cancha 3", "type": "Tenis"},
    ])
    decision = {
        "operation": "query_availability",
        "booking": {"day": "Lunes 26/10", "resource_type": "Futbol 5"},
        "actions": [{
            "operation": "query_availability",
            "booking": {"day": "Lunes 26/10", "resource_type": "Futbol 5"},
        }],
    }
    receipt = {
        "explicit": True,
        "resource_type": None,
        "resource_types": ["Futbol 5", "Futbol 7"],
        "evidence": "futbol",
    }

    patched = agent._canonical_v205_apply_current_turn_resource(
        copy.deepcopy(decision), receipt
    )
    merged = agent._canonical_v183_merge_booking_decision(
        {"booking": {}}, patched
    )

    assert patched["booking"]["resource_type"] is None
    assert patched["booking"]["resource_types"] == ["Futbol 5", "Futbol 7"]
    assert patched["actions"][0]["booking"]["resource_types"] == ["Futbol 5", "Futbol 7"]
    assert merged["resource_types"] == ["Futbol 5", "Futbol 7"]
    assert agent._court_names_compatible_with_resource_types(
        merged["resource_types"]
    ) == ["Cancha 1", "Cancha 2"]

    source = (Path(__file__).resolve().parents[2] / "legacy/WPSetter_legacy.py").read_text(
        encoding="utf-8"
    )
    assert 'Un deporte genérico (por ejemplo "fútbol") devuelve TODAS' in source


def test_specific_modality_still_filters_to_its_exact_courts(monkeypatch):
    monkeypatch.setattr(agent, "COURTS", [
        {"name": "Cancha 1", "type": "Futbol 5"},
        {"name": "Cancha 2", "type": "Futbol 7"},
    ])
    decision = {"operation": "query_availability", "booking": {}}
    patched = agent._canonical_v205_apply_current_turn_resource(decision, {
        "explicit": True,
        "resource_type": "Futbol 7",
        "resource_types": ["Futbol 7"],
        "evidence": "futbol 7",
    })

    assert patched["booking"]["resource_type"] == "Futbol 7"
    assert patched["booking"]["resource_types"] == ["Futbol 7"]
    assert agent._court_names_compatible_with_resource_types(
        patched["booking"]["resource_types"]
    ) == ["Cancha 2"]
