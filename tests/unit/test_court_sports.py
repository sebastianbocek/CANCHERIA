from pathlib import Path

from cancheria.config.court_sports import sport_icon, sport_menu_options


def test_configured_sports_have_deterministic_icons() -> None:
    assert sport_icon("Futbol 5") == "⚽"
    assert sport_icon("Pádel") == "🎾"
    assert sport_icon("Tenis") == "🎾"
    assert sport_icon("Básquet") == "🏀"
    assert sport_icon("Vóley") == "🏐"
    assert sport_icon("Tenis de mesa") == "🏓"
    assert sport_icon("deporte personalizado") == "🏟️"
    assert any(option["type"] == "Pádel" for option in sport_menu_options())


def test_whatsapp_and_desktop_use_the_same_sport_icon_source() -> None:
    root = Path(__file__).resolve().parents[2]
    legacy = (root / "legacy" / "WPSetter_legacy.py").read_text(encoding="utf-8")
    service = (root / "src" / "cancheria" / "admin" / "desktop_service.py").read_text(
        encoding="utf-8"
    )
    panel = (root / "src" / "cancheria" / "desktop" / "admin_panel.py").read_text(
        encoding="utf-8"
    )

    assert "_configured_court_sport_icon(court_type)" in legacy
    assert '"icon": sport_icon(court_type)' in service
    assert "actualizar_canchas_config" in service
    assert '"Fecha del torneo"' in panel
