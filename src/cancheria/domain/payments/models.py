from dataclasses import dataclass
from typing import Optional

@dataclass
class Payment:
    amount: int
    method: str = "transfer"
    receipt_fingerprint: Optional[str] = None
    status: str = "pending"

@dataclass
class Deposit:
    required_amount: int
    paid_amount: int = 0
    status: str = "pending"

    @property
    def remaining_amount(self) -> int:
        return max(0, self.required_amount - self.paid_amount)
