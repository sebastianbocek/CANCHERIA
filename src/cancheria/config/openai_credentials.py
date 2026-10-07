from __future__ import annotations

import ast
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


OPENAI_MODELS_URL = "https://api.openai.com/v1/models"


class CredentialStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    ACCOUNT_RESTRICTED = "account_restricted"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CredentialCheck:
    status: CredentialStatus
    message: str
    http_status: int | None = None

    @property
    def can_start(self) -> bool:
        return self.status == CredentialStatus.VALID


def normalize_openai_api_key(value: object) -> str:
    """Normalize common copy/paste artifacts without ever logging the secret."""
    key = str(value or "").strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in {"'", '"'}:
        key = key[1:-1].strip()
    return key


def read_openai_api_key_assignment(path: object) -> tuple[bool, str]:
    """Read an explicit config.py key without executing that Python file."""
    try:
        config_path = Path(path)
        tree = ast.parse(config_path.read_text(encoding="utf-8-sig"), filename=str(config_path))
    except (OSError, SyntaxError, TypeError, ValueError):
        return False, ""
    for node in tree.body:
        target = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            target = node.target
        if not isinstance(target, ast.Name) or target.id != "OPENAI_API_KEY":
            continue
        try:
            return True, normalize_openai_api_key(ast.literal_eval(node.value))
        except Exception:
            return True, ""
    return False, ""


def validate_openai_api_key_format(value: object) -> str:
    key = normalize_openai_api_key(value)
    if not key:
        raise ValueError("Ingresá una API key de OpenAI.")
    if not key.startswith("sk-") or len(key) < 24:
        raise ValueError(
            "La API key no tiene el formato esperado. Copiala completa desde "
            "https://platform.openai.com/api-keys."
        )
    if any(character.isspace() or ord(character) < 32 for character in key):
        raise ValueError(
            "La API key contiene espacios o saltos de línea internos. "
            "Volvé a copiarla completa."
        )
    return key


def _openai_error_code(body: bytes) -> str:
    """Extract only the public error code; never propagate the API response text."""
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
        return str((payload.get("error") or {}).get("code") or "").strip()
    except Exception:
        return ""


def verify_openai_api_key(value: object, *, timeout: float = 12.0) -> CredentialCheck:
    """Verify a key with OpenAI's authenticated models endpoint.

    Listing models does not create a completion or consume model tokens.  The
    result deliberately excludes response messages because they may contain a
    masked fragment of the credential.
    """
    try:
        key = validate_openai_api_key_format(value)
    except ValueError as exc:
        return CredentialCheck(CredentialStatus.INVALID, str(exc))

    request = urllib.request.Request(
        OPENAI_MODELS_URL,
        method="GET",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "CANCHERIA/0.1.8 credential-check",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            if 200 <= status < 300:
                return CredentialCheck(
                    CredentialStatus.VALID,
                    "API key verificada correctamente con OpenAI.",
                    status,
                )
            return CredentialCheck(
                CredentialStatus.UNAVAILABLE,
                "OpenAI respondió de una forma inesperada. Intentá nuevamente.",
                status,
            )
    except urllib.error.HTTPError as exc:
        status = int(exc.code or 0)
        body = exc.read(16_384)
        error_code = _openai_error_code(body)
        if status == 401 or error_code == "invalid_api_key":
            return CredentialCheck(
                CredentialStatus.INVALID,
                "OpenAI rechazó esta API key. Generá una nueva y volvé a pegarla.",
                status,
            )
        if status in {403, 429}:
            return CredentialCheck(
                CredentialStatus.ACCOUNT_RESTRICTED,
                "La API key fue recibida, pero la cuenta o el proyecto no pueden usar la API. "
                "Revisá proyecto, créditos y facturación en la plataforma de OpenAI.",
                status,
            )
        return CredentialCheck(
            CredentialStatus.UNAVAILABLE,
            "OpenAI no pudo validar la API key en este momento. Intentá nuevamente.",
            status,
        )
    except (urllib.error.URLError, TimeoutError, OSError):
        return CredentialCheck(
            CredentialStatus.UNAVAILABLE,
            "No se pudo conectar con OpenAI. Revisá Internet y volvé a intentar.",
        )

