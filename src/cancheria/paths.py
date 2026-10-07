from __future__ import annotations

import os
from pathlib import Path

_configured_root = os.getenv("CANCHERIA_INSTALL_ROOT", "").strip()
PROJECT_ROOT = (
    Path(_configured_root).expanduser().resolve()
    if _configured_root
    else Path(__file__).resolve().parents[2]
)

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass


def runtime_dir(create: bool = True) -> Path:
    raw = os.getenv("CANCHERIA_RUNTIME_DIR", "").strip()
    path = Path(raw).expanduser().resolve() if raw else PROJECT_ROOT / "runtime"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_file(name: str) -> Path:
    return runtime_dir() / name


def ensure_runtime_layout() -> Path:
    root = runtime_dir()
    (root / "agent_learning" / "versions").mkdir(parents=True, exist_ok=True)
    (root / "events" / "torneos").mkdir(parents=True, exist_ok=True)
    return root
