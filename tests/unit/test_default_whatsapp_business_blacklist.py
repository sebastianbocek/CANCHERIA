from __future__ import annotations

import ast
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEGACY_PATH = ROOT / "legacy" / "WPSetter_legacy.py"


def _load_blacklist_functions(tmp_path: Path) -> dict:
    source = LEGACY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        "_normalizar_nombre_blacklist",
        "_blacklist_entry_from_target",
        "cargar_blacklist",
        "guardar_blacklist",
        "telefono_en_blacklist",
        "desbloquear_numero",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    namespace = {
        "List": list,
        "os": __import__("os"),
        "json": json,
        "re": re,
        "unicodedata": unicodedata,
        "BLACKLIST_FILE": str(tmp_path / "blacklist_numbers.json"),
        "DEFAULT_BLACKLIST_ENTRIES": frozenset({"name:whatsapp business"}),
        "normalize_phone": lambda value: str(value or "").strip(),
        "es_numero_autorizado": lambda _value: False,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(LEGACY_PATH), "exec"), namespace)
    return namespace


def test_whatsapp_business_is_always_in_default_blacklist(tmp_path):
    functions = _load_blacklist_functions(tmp_path)

    assert functions["cargar_blacklist"]() == ["name:whatsapp business"]
    assert functions["telefono_en_blacklist"]("NOMBRE:WhatsApp Business") is True

    functions["guardar_blacklist"]([])
    stored = json.loads((tmp_path / "blacklist_numbers.json").read_text(encoding="utf-8"))
    assert stored == ["name:whatsapp business"]
    assert functions["desbloquear_numero"]("WhatsApp Business") is False
    assert functions["telefono_en_blacklist"]("NOMBRE:WhatsApp Business") is True


def test_blacklisted_chat_escapes_and_returns_to_all_filter():
    source = LEGACY_PATH.read_text(encoding="utf-8")
    early_branch = source.split('if telefono_en_blacklist(telefono or ""):', 1)[1].split(
        "if await omitir_chat_pausado_por_humano", 1
    )[0]
    default_name_branch = source.split(
        'if _normalizar_nombre_blacklist(prospecto.get("nombre")) == "whatsapp business":',
        1,
    )[1].split("if user_messages and await manejar_comando_autorizado", 1)[0]

    for branch in (early_branch, default_name_branch):
        assert "await escape_chat(page)" in branch
        assert "await click_todos(page)" in branch
        assert branch.index("await escape_chat(page)") < branch.index("await click_todos(page)")
