from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from cancheria.paths import runtime_dir


def _csv_env(name: str) -> Tuple[str, ...]:
    return tuple(x.strip() for x in os.getenv(name, "").split(",") if x.strip())


@dataclass(frozen=True)
class AppSettings:
    runtime_dir: Path
    openai_api_key: str
    openai_model: str
    local_timezone: str
    email_sender: str
    email_password: str
    email_receiver: str
    authorized_number: str
    authorized_numbers: Tuple[str, ...]
    authorized_names: Tuple[str, ...]

    @classmethod
    def from_env(cls) -> "AppSettings":
        primary = os.getenv("AUTHORIZED_NUMBER", "").strip()
        numbers = _csv_env("AUTHORIZED_NUMBERS")
        if primary and primary not in numbers:
            numbers = (primary, *numbers)
        # Environment variables may override local configuration, but the
        # desktop configurator stores the user's key in legacy_config.py.
        from cancheria.config import legacy_config

        return cls(
            runtime_dir=runtime_dir(),
            openai_api_key=(
                os.getenv("OPENAI_API_KEY", "").strip()
                or str(getattr(legacy_config, "OPENAI_API_KEY", "")).strip()
            ),
            openai_model=(
                os.getenv("OPENAI_MODEL", "").strip()
                or str(getattr(legacy_config, "OPENAI_MODEL", "gpt-4.1-mini")).strip()
            ),
            local_timezone=os.getenv("LOCAL_TIMEZONE", "America/Argentina/Cordoba").strip(),
            email_sender=os.getenv("EMAIL_SENDER", "").strip(),
            email_password=os.getenv("EMAIL_PASSWORD", "").strip(),
            email_receiver=os.getenv("EMAIL_RECEIVER", "").strip(),
            authorized_number=primary,
            authorized_numbers=numbers,
            authorized_names=_csv_env("AUTHORIZED_NAMES"),
        )


@dataclass(frozen=True)
class BusinessSettings:
    name: str
    agent_name: str
    address: str
    timezone: str = "America/Argentina/Cordoba"


@dataclass(frozen=True)
class PaymentSettings:
    requires_deposit: bool
    deposit_mode: str
    deposit_percentage: float
    payment_alias: str
