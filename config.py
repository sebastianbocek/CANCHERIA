"""Compatibility import for legacy CANCHERIA code.

New code should import from ``cancheria.config`` or
``cancheria.config.legacy_config`` directly.
"""
from pathlib import Path
import sys
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from cancheria.config.legacy_config import *  # noqa: F401,F403

# Credencial operativa editable por el configurador gráfico. Se mantiene en
# este config.py por compatibilidad con el funcionamiento histórico.
OPENAI_API_KEY = ""
