from pathlib import Path
import ast
import runpy


def test_public_config_has_blank_editable_openai_key():
    root = Path(__file__).resolve().parents[2]
    from cancheria.config.openai_credentials import read_openai_api_key_assignment
    found, key = read_openai_api_key_assignment(root / "config.py")
    assert found is True
    assert key == ""


def test_visual_configurator_persists_openai_key():
    root = Path(__file__).resolve().parents[2]
    text = (root / "legacy" / "configurador_cancheria_legacy.py").read_text(encoding="utf-8")
    assert "openai_key = validate_openai_api_key_format(self.openai_key.get())" in text
    assert '"OPENAI_API_KEY": openai_key' in text
    assert "credential_check = verify_openai_api_key" in text
    assert "save_config_and_root_key" in text
    assert "API key guardada en" in text


def test_visual_configurator_persists_admin_recipients_and_requires_model():
    root = Path(__file__).resolve().parents[2]
    text = (root / "legacy" / "configurador_cancheria_legacy.py").read_text(encoding="utf-8")
    assert '"AUTHORIZED_NUMBER": auth_number' in text
    assert '"AUTHORIZED_NUMBERS": auth_numbers' in text
    assert '"AUTHORIZED_NAMES": auth_names' in text
    assert 'or "gpt-4o-mini"' in text
    assert "Modelo OpenAI obligatorio" in text


def test_app_settings_falls_back_to_legacy_key_for_old_root_config(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from cancheria.config import legacy_config
    from cancheria.config import settings
    (tmp_path / "config.py").write_text("# v0.1.7 compatibility bridge\n", encoding="utf-8")
    monkeypatch.setattr(settings, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(legacy_config, "OPENAI_API_KEY", "test-local-key")
    assert settings.AppSettings.from_env().openai_api_key == "test-local-key"


def test_app_settings_reads_and_normalizes_root_config_key(monkeypatch, tmp_path):
    from cancheria.config import settings
    example_key = "sk" + "-example-local-key-1234567890"
    monkeypatch.setenv("OPENAI_API_KEY", "environment-value-must-not-override-config")
    (tmp_path / "config.py").write_text(
        f'OPENAI_API_KEY = "  {example_key}  "\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "PROJECT_ROOT", tmp_path)
    assert settings.AppSettings.from_env().openai_api_key == example_key


def test_configurator_migrates_key_to_root_config_and_blanks_legacy_copy(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    namespace = runpy.run_path(str(project_root / "legacy" / "configurador_cancheria_legacy.py"))
    config_source_type = namespace["ConfigSource"]
    save_pair = namespace["save_config_and_root_key"]

    root_config = tmp_path / "config.py"
    root_config.write_text(
        "from cancheria.config.legacy_config import *\n",
        encoding="utf-8",
    )
    nested_config = tmp_path / "legacy_config.py"
    nested_config.write_text("OPENAI_API_KEY = 'old-value'\n", encoding="utf-8")
    example_key = "sk" + "-proj-example-not-a-real-key-1234567890"

    save_pair.__globals__["ROOT_CONFIG"] = root_config
    source = config_source_type(nested_config)
    save_pair(source, {"OPENAI_API_KEY": example_key}, example_key)

    root_tree = ast.parse(root_config.read_text(encoding="utf-8"))
    nested_tree = ast.parse(nested_config.read_text(encoding="utf-8"))
    root_value = next(
        ast.literal_eval(node.value)
        for node in root_tree.body
        if isinstance(node, ast.Assign) and node.targets[0].id == "OPENAI_API_KEY"
    )
    nested_value = next(
        ast.literal_eval(node.value)
        for node in nested_tree.body
        if isinstance(node, ast.Assign) and node.targets[0].id == "OPENAI_API_KEY"
    )
    assert root_value == example_key
    assert nested_value == ""
