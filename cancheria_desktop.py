#!/usr/bin/env python3
"""CANCHERIA desktop launcher and frozen worker dispatcher."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

# Freeze support: WPSetter/calendario are executed from external source files.
# Importing this module forces PyInstaller to bundle the stdlib modules those
# dynamic scripts need (notably sqlite3/json).
from cancheria.desktop.frozen_runtime_support import stdlib_self_test

# Build-time dependency anchors. WPSetter.py is executed with runpy in frozen
# worker mode, so PyInstaller cannot discover these imports by following the
# external script. Keeping the imports here makes the frozen runtime include
# exactly the third-party packages WPSetter needs without --collect-all.
try:  # pragma: no cover - packaging anchor
    from openai import OpenAI as _OpenAI_for_packaging  # noqa: F401
    from playwright.async_api import async_playwright as _async_playwright_for_packaging  # noqa: F401
    import pytz as _pytz_for_packaging  # noqa: F401
    from dotenv import load_dotenv as _dotenv_for_packaging  # noqa: F401
except Exception:
    # Source checkouts can still show a useful GUI error if dependencies have
    # not been installed yet. The Windows build installs them before freezing.
    pass


def _is_install_root(path: Path) -> bool:
    path = Path(path)
    return (
        (path / "WPSetter.py").is_file()
        and (path / "src" / "cancheria").is_dir()
        and (path / "legacy").is_dir()
    )


def root_dir() -> Path:
    """Locate the external CANCHERIA tree for GUI and worker modes."""
    candidates: list[Path] = []
    configured = os.environ.get("CANCHERIA_INSTALL_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser().resolve())

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir, exe_dir.parent])
    else:
        candidates.append(Path(__file__).resolve().parent)

    candidates.append(Path.cwd().resolve())
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if _is_install_root(candidate):
            return candidate

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def configure_paths(root: Path) -> None:
    """Expose the external open-source tree to the frozen interpreter.

    PyInstaller imports ``cancheria.desktop`` from its internal archive before
    the GUI knows the installation root.  That means the already-loaded
    ``cancheria`` package would otherwise search only inside the frozen archive
    and fail to see external modules such as ``cancheria.legacy_bridge``.
    Extend the package search path explicitly and publish the installation root
    for modules (notably ``cancheria.paths``) that need stable filesystem paths.
    """
    root = Path(root).resolve()
    src = root / "src"
    os.environ["CANCHERIA_INSTALL_ROOT"] = str(root)

    for path in (src, root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)

    package = sys.modules.get("cancheria")
    external_package = str((src / "cancheria").resolve())
    package_path = getattr(package, "__path__", None) if package is not None else None
    if package_path is not None and external_package not in package_path:
        # Put the editable/open-source tree first.  This makes dynamic modules
        # executed with runpy behave the same in source and frozen modes.
        try:
            package_path.insert(0, external_package)
        except AttributeError:
            package.__path__ = [external_package, *list(package_path)]


def run_script(script: Path, argv: list[str]) -> int:
    old_argv = sys.argv[:]
    try:
        sys.argv = [str(script), *argv]
        try:
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit as exc:
            return int(exc.code or 0)
        return 0
    finally:
        sys.argv = old_argv


def main() -> int:
    root = root_dir()
    configure_paths(root)
    args = sys.argv[1:]

    # WPSetter starts calendario.py through sys.executable. In the frozen build
    # sys.executable is cancheria.exe, so dispatch that script explicitly.
    if args and args[0].lower().endswith(".py"):
        script = Path(args[0])
        if script.exists():
            return run_script(script, args[1:])

    if args and args[0] == "--self-test":
        failures = stdlib_self_test()
        # Third-party imports used by WPSetter are anchored above; verify them
        # explicitly in the frozen executable before a release is assembled.
        for module_name in ("openai", "playwright.async_api", "pytz", "dotenv"):
            try:
                __import__(module_name)
            except Exception as exc:
                failures.append(f"{module_name}: {type(exc).__name__}: {exc}")

        # Regression guard for the exact failure seen in the Windows frozen
        # worker: the external src/cancheria tree must remain importable even
        # though ``cancheria.desktop`` was loaded from the PyInstaller archive.
        for module_name in (
            "cancheria.legacy_bridge",
            "cancheria.paths",
            "cancheria.config.legacy_config",
            "cancheria.domain.events.registration",
            "cancheria.domain.reservations.calendar",
            "cancheria.desktop.update_service",
            "cancheria.desktop.update_helper",
            "cancheria.desktop.ai_control",
        ):
            try:
                __import__(module_name)
            except Exception as exc:
                failures.append(f"{module_name}: {type(exc).__name__}: {exc}")
        try:
            from cancheria.paths import PROJECT_ROOT as _project_root
            if Path(_project_root).resolve() != root.resolve():
                failures.append(
                    f"cancheria.paths.PROJECT_ROOT: expected {root}, got {_project_root}"
                )
        except Exception as exc:
            failures.append(f"cancheria.paths.PROJECT_ROOT: {type(exc).__name__}: {exc}")

        report = root / "build" / "runtime-selftest-cancheria.txt"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("OK\n" if not failures else "\n".join(failures) + "\n", encoding="utf-8")
        return 0 if not failures else 1

    if args and args[0] == "--worker":
        return run_script(root / "WPSetter.py", args[1:])

    if args and args[0] == "--update-finished":
        os.environ["CANCHERIA_UPDATE_FINISHED"] = args[1] if len(args) > 1 else ""

    from cancheria.desktop.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
