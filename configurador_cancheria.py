#!/usr/bin/env python3
"""CANCHERIA visual configurator launcher.

When frozen as ``configurador_cancheria.exe`` this launcher edits the external
configuration that lives beside the executable, so changes persist after the
program closes. In source mode it behaves like the historical Python launcher.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

# The historical configurator is executed from an external source file.
# Bundle the stdlib modules it imports (json/ast/pprint/etc.) in the frozen EXE.
from cancheria.desktop.frozen_runtime_support import stdlib_self_test

# Imported explicitly so PyInstaller detects and bundles the Tk runtime even
# though the full UI implementation is loaded from the external legacy module.
import tkinter as _tkinter_for_packaging  # noqa: F401
from tkinter import filedialog as _filedialog_for_packaging  # noqa: F401
from tkinter import messagebox as _messagebox_for_packaging  # noqa: F401
from tkinter import ttk as _ttk_for_packaging  # noqa: F401


def _is_install_root(path: Path) -> bool:
    path = Path(path)
    return (
        (path / "config.py").is_file()
        and (path / "legacy" / "configurador_cancheria_legacy.py").is_file()
    )


def install_root() -> Path:
    """Locate the external CANCHERIA tree beside the desktop executables.

    New builds emit this EXE directly in the installation root.  The parent
    fallback keeps older ``dist/configurador_cancheria.exe`` builds usable.
    """
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
        try:
            package_path.insert(0, external_package)
        except AttributeError:
            package.__path__ = [external_package, *list(package_path)]


def main() -> int:
    root = install_root()
    configure_paths(root)
    os.environ["CANCHERIA_INSTALL_ROOT"] = str(root)

    if sys.argv[1:] and sys.argv[1] == "--self-test":
        failures = stdlib_self_test()
        report = root / "build" / "runtime-selftest-configurador.txt"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("OK\n" if not failures else "\n".join(failures) + "\n", encoding="utf-8")
        return 0 if not failures else 1

    script = root / "legacy" / "configurador_cancheria_legacy.py"
    if not script.exists():
        raise FileNotFoundError(
            f"No se encontró el configurador de CANCHERIA en: {script}"
        )

    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
