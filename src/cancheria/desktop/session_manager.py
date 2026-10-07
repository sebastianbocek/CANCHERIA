from __future__ import annotations

import shutil
import time
from pathlib import Path


class SessionResetError(RuntimeError):
    """Raised when the local WhatsApp profile cannot be reset safely."""


def ensure_profile(profile_dir: Path) -> Path:
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def reset_profile(profile_dir: Path, *, attempts: int = 6, delay: float = 0.35) -> Path:
    """Remove the local WhatsApp/Chrome profile and recreate it empty.

    This affects only the local browser profile. Runtime booking/business data lives
    elsewhere and is intentionally preserved.
    """
    profile_dir = Path(profile_dir)
    last_error: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            if profile_dir.exists():
                shutil.rmtree(profile_dir)
            profile_dir.mkdir(parents=True, exist_ok=True)
            return profile_dir
        except Exception as exc:  # Windows may release Chrome locks a little later.
            last_error = exc
            time.sleep(max(0.0, delay))
    raise SessionResetError(
        f"No se pudo limpiar el perfil local {profile_dir}: {last_error}"
    )
