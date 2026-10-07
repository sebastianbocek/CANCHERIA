from pathlib import Path


def test_public_config_has_blank_editable_openai_key():
    from cancheria.config import legacy_config
    assert hasattr(legacy_config, "OPENAI_API_KEY")
    assert not str(legacy_config.OPENAI_API_KEY).startswith("sk-")


def test_visual_configurator_persists_openai_key():
    root = Path(__file__).resolve().parents[2]
    text = (root / "legacy" / "configurador_cancheria_legacy.py").read_text(encoding="utf-8")
    assert '"OPENAI_API_KEY": self.openai_key.get().strip()' in text


def test_visual_configurator_persists_admin_recipients_and_requires_model():
    root = Path(__file__).resolve().parents[2]
    text = (root / "legacy" / "configurador_cancheria_legacy.py").read_text(encoding="utf-8")
    assert '"AUTHORIZED_NUMBER": auth_number' in text
    assert '"AUTHORIZED_NUMBERS": auth_numbers' in text
    assert '"AUTHORIZED_NAMES": auth_names' in text
    assert 'or "gpt-4o-mini"' in text
    assert "Modelo OpenAI obligatorio" in text


def test_app_settings_falls_back_to_configured_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from cancheria.config import legacy_config
    from cancheria.config.settings import AppSettings
    monkeypatch.setattr(legacy_config, "OPENAI_API_KEY", "test-local-key")
    assert AppSettings.from_env().openai_api_key == "test-local-key"
