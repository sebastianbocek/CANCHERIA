from __future__ import annotations
import importlib.util
import runpy
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from cancheria.paths import PROJECT_ROOT

LEGACY_WPSETTER = PROJECT_ROOT / "legacy" / "WPSetter_legacy.py"

@lru_cache(maxsize=1)
def load_legacy_module():
    spec = importlib.util.spec_from_file_location("cancheria._legacy_wpsetter", LEGACY_WPSETTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load legacy core: {LEGACY_WPSETTER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def legacy_callable(name: str):
    fn = getattr(load_legacy_module(), name)
    if not callable(fn):
        raise TypeError(f"Legacy attribute {name!r} is not callable")
    return fn

def run_legacy_cli(argv: list[str] | None = None) -> int:
    old_argv = sys.argv[:]
    try:
        sys.argv = [str(LEGACY_WPSETTER), *(argv or [])]
        try:
            runpy.run_path(str(LEGACY_WPSETTER), run_name="__main__")
        except SystemExit as exc:
            return int(exc.code or 0)
        return 0
    finally:
        sys.argv = old_argv
