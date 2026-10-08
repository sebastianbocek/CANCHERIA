from __future__ import annotations

import unicodedata
from typing import Final


SPORT_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("⚽", "Futbol 5"),
    ("⚽", "Futbol 7"),
    ("⚽", "Futbol 11"),
    ("🎾", "Tenis"),
    ("🎾", "Pádel"),
    ("🏀", "Básquet"),
    ("🏐", "Vóley"),
    ("🏑", "Hockey"),
    ("🏉", "Rugby"),
    ("🏓", "Tenis de mesa"),
    ("🏸", "Bádminton"),
    ("⚾", "Béisbol"),
    ("🥎", "Softball"),
    ("⛳", "Golf"),
)


def _normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in text if not unicodedata.combining(char)).strip()


def sport_icon(court_type: object) -> str:
    """Return the presentation icon for an already configured court type."""
    normalized = _normalized(court_type)
    if not normalized:
        return "🏟️"
    if "tenis de mesa" in normalized or "ping pong" in normalized or "ping-pong" in normalized:
        return "🏓"
    if "badminton" in normalized:
        return "🏸"
    if "basquet" in normalized or "basket" in normalized:
        return "🏀"
    if "voley" in normalized or "volley" in normalized or "voleibol" in normalized:
        return "🏐"
    if "rugby" in normalized:
        return "🏉"
    if "hockey" in normalized:
        return "🏑"
    if "softball" in normalized:
        return "🥎"
    if "baseball" in normalized or "beisbol" in normalized:
        return "⚾"
    if "golf" in normalized:
        return "⛳"
    if "futbol" in normalized or "futsal" in normalized:
        return "⚽"
    if "tenis" in normalized or "padel" in normalized or "squash" in normalized:
        return "🎾"
    return "🏟️"


def sport_menu_options() -> list[dict[str, str]]:
    return [
        {"icon": icon, "type": court_type, "label": f"{icon}  {court_type}"}
        for icon, court_type in SPORT_OPTIONS
    ]
