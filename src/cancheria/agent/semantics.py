from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SemanticFrame:
    intents: list[str] = field(default_factory=list)
    entities: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0

@dataclass
class ToolObservation:
    ok: bool
    status: str = ""
    facts: dict[str, Any] = field(default_factory=dict)
    raw: Any = None
