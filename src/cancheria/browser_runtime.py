from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any


BROWSER_EXECUTABLE_ENV = "CANCHERIA_BROWSER_EXECUTABLE"
LINUX_BROWSER_COMMANDS = (
    "google-chrome-stable",
    "google-chrome",
    "chromium",
    "chromium-browser",
)


def _configured_browser_executable() -> str | None:
    """Resolve an optional browser override from the environment."""
    configured = os.getenv(BROWSER_EXECUTABLE_ENV, "").strip()
    if not configured:
        return None

    expanded = Path(configured).expanduser()
    if expanded.is_file():
        return str(expanded.resolve())

    discovered = shutil.which(configured)
    if discovered:
        return discovered

    raise FileNotFoundError(
        f"{BROWSER_EXECUTABLE_ENV} apunta a un navegador inexistente: {configured}"
    )


def discover_browser_executable(*, platform: str | None = None) -> str | None:
    """Find Chrome/Chromium on Linux while preserving Chrome on Windows."""
    configured = _configured_browser_executable()
    if configured:
        return configured

    current_platform = platform or sys.platform
    if not current_platform.startswith("linux"):
        return None

    for command in LINUX_BROWSER_COMMANDS:
        discovered = shutil.which(command)
        if discovered:
            return discovered
    return None


def persistent_context_options(
    user_data_dir: str | Path,
    *,
    platform: str | None = None,
) -> dict[str, Any]:
    """Return Playwright options suitable for the current desktop platform."""
    current_platform = platform or sys.platform
    arguments = [
        "--start-maximized",
        "--disable-notifications",
        "--disable-features=DownloadBubble,DownloadBubbleV2",
    ]
    if current_platform.startswith("linux"):
        # Small cloud desktops often mount /dev/shm with only 64 MB.
        arguments.append("--disable-dev-shm-usage")

    options: dict[str, Any] = {
        "user_data_dir": str(user_data_dir),
        "headless": False,
        "args": arguments,
        "accept_downloads": True,
        "viewport": {"width": 1366, "height": 768},
        "locale": "es-AR",
        "timezone_id": "America/Argentina/Cordoba",
    }

    executable = discover_browser_executable(platform=current_platform)
    if executable:
        options["executable_path"] = executable
    else:
        # The Windows distribution has historically used installed Chrome.
        # Keeping the channel also supports macOS and manual Linux installs.
        options["channel"] = "chrome"
    return options
