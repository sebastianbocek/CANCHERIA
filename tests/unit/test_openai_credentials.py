from __future__ import annotations

import io
import urllib.error

import pytest

from cancheria.config import openai_credentials
from cancheria.config.openai_credentials import (
    CredentialStatus,
    normalize_openai_api_key,
    read_openai_api_key_assignment,
    validate_openai_api_key_format,
    verify_openai_api_key,
)


EXAMPLE_KEY = "sk" + "-proj-example-not-a-real-key-1234567890"


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_normalize_removes_outer_spaces_and_quotes():
    assert normalize_openai_api_key(f'  "{EXAMPLE_KEY}"\n') == EXAMPLE_KEY
    assert normalize_openai_api_key(f"  '{EXAMPLE_KEY}'  ") == EXAMPLE_KEY


def test_reads_explicit_root_config_assignment_without_executing(tmp_path):
    marker = tmp_path / "must-not-exist"
    config = tmp_path / "config.py"
    config.write_text(
        f'OPENAI_API_KEY = "{EXAMPLE_KEY}"\n'
        f'Path({str(marker)!r}).touch()\n',
        encoding="utf-8",
    )
    found, key = read_openai_api_key_assignment(config)
    assert found is True
    assert key == EXAMPLE_KEY
    assert not marker.exists()


def test_old_root_config_without_assignment_uses_migration_fallback(tmp_path):
    config = tmp_path / "config.py"
    config.write_text("from cancheria.config.legacy_config import *\n", encoding="utf-8")
    assert read_openai_api_key_assignment(config) == (False, "")


def test_format_rejects_missing_or_broken_keys():
    with pytest.raises(ValueError, match="Ingresá"):
        validate_openai_api_key_format("   ")
    with pytest.raises(ValueError, match="formato"):
        validate_openai_api_key_format("not-a-key")
    with pytest.raises(ValueError, match="espacios"):
        validate_openai_api_key_format("sk-proj-example key-with-space-123456")


def test_verify_accepts_authenticated_response(monkeypatch):
    monkeypatch.setattr(openai_credentials.urllib.request, "urlopen", lambda *_a, **_kw: _Response())
    result = verify_openai_api_key(EXAMPLE_KEY)
    assert result.status == CredentialStatus.VALID
    assert result.can_start is True


def test_verify_maps_401_without_echoing_secret(monkeypatch):
    def reject(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":{"code":"invalid_api_key"}}'),
        )

    monkeypatch.setattr(openai_credentials.urllib.request, "urlopen", reject)
    result = verify_openai_api_key(EXAMPLE_KEY)
    assert result.status == CredentialStatus.INVALID
    assert result.can_start is False
    assert EXAMPLE_KEY not in result.message


def test_verify_maps_network_failure_to_unavailable(monkeypatch):
    def offline(*_args, **_kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(openai_credentials.urllib.request, "urlopen", offline)
    result = verify_openai_api_key(EXAMPLE_KEY)
    assert result.status == CredentialStatus.UNAVAILABLE
    assert "Internet" in result.message
