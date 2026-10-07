from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "create_fresh_client_zip.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("create_fresh_client_zip", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backup_creator_excludes_installer_and_private_runtime() -> None:
    module = _load_module()
    assert "installer" not in module.SOURCE_DIRECTORIES
    assert "runtime" not in module.SOURCE_DIRECTORIES
    assert "wa_profile" not in module.SOURCE_DIRECTORIES
    assert "sessions" not in module.SOURCE_DIRECTORIES
    assert "release" not in module.SOURCE_DIRECTORIES


def test_backup_creator_uses_allowlist_and_clean_config(tmp_path: Path) -> None:
    module = _load_module()
    source_root = tmp_path / "source"
    clean_config = module.copy_fresh_source(ROOT, source_root)

    assert clean_config.is_file()
    text = clean_config.read_text(encoding="utf-8")
    assert module.OPENAI_KEY_PATTERN.search(text.encode()) is None
    assert 'or "gpt-4o-mini"' in text
    assert not (source_root / "installer").exists()
    assert not (source_root / "src" / "cancheria" / "config" / "config_backups").exists()


def test_zip_has_single_cancheria_root_and_no_installer(tmp_path: Path) -> None:
    module = _load_module()
    payload = tmp_path / "payload"
    (payload / "runtime").mkdir(parents=True)
    (payload / "README.md").write_text("fresh", encoding="utf-8")

    zip_path, digest = module.create_zip(payload, tmp_path / "out")

    assert len(digest) == 64
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    assert names == ["CANCHERIA/README.md"]
    assert all("installer" not in name.lower() for name in names)
