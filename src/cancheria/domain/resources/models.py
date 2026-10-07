from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Resource:
    name: str
    resource_type: str
    price_per_hour: int = 0
    parallel_group: Optional[str] = None
