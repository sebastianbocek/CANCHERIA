#!/usr/bin/env python3
"""Legacy-compatible CANCHERIA entrypoint.

The historical implementation lives in ``legacy/WPSetter_legacy.py`` while
new public APIs live under ``src/cancheria``.
"""
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from cancheria.legacy_bridge import load_legacy_module, run_legacy_cli

def __getattr__(name):
    return getattr(load_legacy_module(), name)

if __name__ == "__main__":
    raise SystemExit(run_legacy_cli(sys.argv[1:]))
