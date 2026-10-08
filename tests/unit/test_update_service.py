from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from cancheria.desktop import update_helper, update_service
from cancheria.desktop.update_helper import apply_staged_update
from cancheria.desktop.update_service import (
    UpdateError,
    create_data_backup,
    create_update_archive,
    extract_and_validate_update,
    is_newer_version,
    release_from_payload,
)


def test_version_comparison_handles_v_prefix_and_numeric_parts() -> None:
    assert is_newer_version("v0.2.0", "0.1.9")
    assert not is_newer_version("0.2.0", "0.2")
    with pytest.raises(UpdateError):
        is_newer_version("latest", "0.2.0")


def test_release_requires_the_platform_asset_and_github_digest() -> None:
    payload = {
        "tag_name": "v0.2.0",
        "name": "CANCHERIA v0.2.0",
        "body": "Actualización desde la GUI",
        "html_url": "https://github.com/sebastianbocek/CANCHERIA/releases/tag/v0.2.0",
        "assets": [
            {
                "name": "CANCHERIA-update-windows.zip",
                "browser_download_url": "https://github.com/sebastianbocek/CANCHERIA/releases/download/v0.2.0/CANCHERIA-update-windows.zip",
                "size": 123,
                "digest": "sha256:" + "a" * 64,
            }
        ],
    }
    release = release_from_payload(payload, "windows")
    assert release.version == "0.2.0"
    assert release.asset.sha256 == "a" * 64
    with pytest.raises(UpdateError):
        release_from_payload(payload, "linux")


def test_current_version_does_not_require_an_update_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        update_service,
        "_request_json",
        lambda _url: {"tag_name": "v0.2.0", "assets": []},
    )
    assert update_service.check_for_update("0.2.0", "windows") is None


def test_update_archive_excludes_private_data_and_validates_manifest(tmp_path: Path) -> None:
    payload = tmp_path / "payload"
    (payload / "src" / "cancheria").mkdir(parents=True)
    (payload / "WPSetter.py").write_text("new agent", encoding="utf-8")
    (payload / "src" / "cancheria" / "feature.py").write_text("new feature", encoding="utf-8")
    (payload / "config.py").write_text("PRIVATE = True", encoding="utf-8")
    (payload / "wa_profile").mkdir()
    (payload / "wa_profile" / "session.bin").write_bytes(b"private")

    archive, _ = create_update_archive(
        payload,
        tmp_path / "CANCHERIA-update-windows.zip",
        "0.2.0",
        "windows",
    )
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
    assert "update-manifest.json" in names
    assert "WPSetter.py" in names
    assert "config.py" not in names
    assert "wa_profile/session.bin" not in names

    staged = extract_and_validate_update(archive, tmp_path / "staged", "0.2.0", "windows")
    assert (staged / "src" / "cancheria" / "feature.py").read_text() == "new feature"


def test_update_helper_replaces_program_and_preserves_configuration(tmp_path: Path) -> None:
    install = tmp_path / "install"
    (install / "src" / "cancheria" / "config").mkdir(parents=True)
    (install / "WPSetter.py").write_text("old agent", encoding="utf-8")
    (install / "src" / "cancheria" / "old.py").write_text("old", encoding="utf-8")
    config = install / "config.py"
    legacy = install / "src" / "cancheria" / "config" / "legacy_config.py"
    config.write_text("API = 'client-value'", encoding="utf-8")
    legacy.write_text("BUSINESS = 'client-value'", encoding="utf-8")

    payload = tmp_path / "payload"
    (payload / "src" / "cancheria").mkdir(parents=True)
    (payload / "WPSetter.py").write_text("new agent", encoding="utf-8")
    (payload / "src" / "cancheria" / "old.py").write_text("new", encoding="utf-8")
    (payload / "config.py").write_text("template", encoding="utf-8")
    archive, _ = create_update_archive(
        payload,
        tmp_path / "update.zip",
        "0.2.0",
        "windows",
    )
    staged = extract_and_validate_update(archive, tmp_path / "staged", "0.2.0", "windows")

    apply_staged_update(
        install,
        staged,
        "0.2.0",
        "windows",
        reinstall_linux_dependencies=False,
    )

    assert (install / "WPSetter.py").read_text() == "new agent"
    assert (install / "src" / "cancheria" / "old.py").read_text() == "new"
    assert config.read_text() == "API = 'client-value'"
    assert legacy.read_text() == "BUSINESS = 'client-value'"


def test_backup_contains_private_data_but_skips_browser_cache(tmp_path: Path) -> None:
    install = tmp_path / "CANCHERIA"
    (install / "runtime").mkdir(parents=True)
    (install / "runtime" / "reservations.json").write_text("[]", encoding="utf-8")
    (install / "wa_profile" / "Default" / "Cache").mkdir(parents=True)
    (install / "wa_profile" / "Default" / "Cookies").mkdir(parents=True)
    (install / "wa_profile" / "Default" / "Cache" / "discard.bin").write_bytes(b"cache")
    (install / "wa_profile" / "Default" / "Cookies" / "keep.bin").write_bytes(b"session")
    (install / "config.py").write_text("client settings", encoding="utf-8")

    backup = create_data_backup(install)
    with zipfile.ZipFile(backup) as archive:
        names = set(archive.namelist())
    assert "config.py" in names
    assert "runtime/reservations.json" in names
    assert "wa_profile/Default/Cookies/keep.bin" in names
    assert "wa_profile/Default/Cache/discard.bin" not in names


def test_update_helper_rolls_back_program_files_when_replacement_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install = tmp_path / "install"
    (install / "src" / "cancheria").mkdir(parents=True)
    (install / "WPSetter.py").write_text("old main", encoding="utf-8")
    (install / "src" / "cancheria" / "feature.py").write_text("old feature", encoding="utf-8")

    payload = tmp_path / "payload"
    (payload / "src" / "cancheria").mkdir(parents=True)
    (payload / "WPSetter.py").write_text("new main", encoding="utf-8")
    (payload / "src" / "cancheria" / "feature.py").write_text("new feature", encoding="utf-8")
    archive, _ = create_update_archive(payload, tmp_path / "update.zip", "0.2.0", "windows")
    staged = extract_and_validate_update(archive, tmp_path / "staged", "0.2.0", "windows")

    real_replace = update_helper.os.replace
    calls = 0

    def fail_second_replace(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated locked file")
        real_replace(source, destination)

    monkeypatch.setattr(update_helper.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="simulated locked file"):
        apply_staged_update(
            install,
            staged,
            "0.2.0",
            "windows",
            reinstall_linux_dependencies=False,
        )

    assert (install / "WPSetter.py").read_text() == "old main"
    assert (install / "src" / "cancheria" / "feature.py").read_text() == "old feature"


def test_gui_exposes_settings_and_update_action() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "src" / "cancheria" / "desktop" / "gui.py").read_text(encoding="utf-8")
    assert 'text="⚙ AJUSTES"' in text
    assert 'text="ACTUALIZAR VERSIÓN"' in text
    assert "check_for_update(__version__)" in text
    assert "launch_update_helper" in text
