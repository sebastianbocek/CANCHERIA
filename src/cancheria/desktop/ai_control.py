from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cancheria.paths import runtime_file


AI_CONTROL_FILENAME = "ai_control.json"


def ai_control_path(root_dir: Path | None = None) -> Path:
    """Return the shared GUI/worker control file for AI response state."""
    if root_dir is not None:
        return Path(root_dir).resolve() / "runtime" / AI_CONTROL_FILENAME
    return runtime_file(AI_CONTROL_FILENAME)


def read_ai_control(
    root_dir: Path | None = None,
    *,
    default_paused: bool = False,
) -> dict[str, Any]:
    path = ai_control_path(root_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("paused"), bool):
            return data
    except (FileNotFoundError, OSError, ValueError, TypeError):
        pass
    return {
        "paused": bool(default_paused),
        "updated_at": "",
        "source": "default",
    }


def write_ai_paused(
    paused: bool,
    root_dir: Path | None = None,
    *,
    source: str = "desktop_gui",
) -> dict[str, Any]:
    """Atomically publish whether automatic AI replies are paused."""
    path = ai_control_path(root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "paused": bool(paused),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source or "unknown"),
    }
    fd, temporary_name = tempfile.mkstemp(
        prefix="ai_control_",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return payload


def ensure_ai_control(
    root_dir: Path | None = None,
    *,
    default_paused: bool = False,
) -> dict[str, Any]:
    path = ai_control_path(root_dir)
    if path.is_file():
        return read_ai_control(root_dir, default_paused=default_paused)
    return write_ai_paused(
        default_paused,
        root_dir,
        source="initial_state",
    )
