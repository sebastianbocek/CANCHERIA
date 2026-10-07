from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple

@dataclass(frozen=True)
class AvailabilityQuery:
    day: str
    start_time: Optional[str] = None
    resource_type: Optional[str] = None
    duration_hours: float = 1.0
    court: Optional[str] = None

@dataclass
class Reservation:
    reservation_id: str
    phone: str
    day: str
    start_time: str
    court: str
    resource_type: str = ""
    duration_hours: float = 1.0
    status: str = "pending"
    total_amount: int = 0
    deposit_amount: int = 0

@dataclass
class Hold:
    reservation_id: str
    started_at: datetime
    expires_at: datetime
    resource_ids: Tuple[str, ...] = field(default_factory=tuple)
