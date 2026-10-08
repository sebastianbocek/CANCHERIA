from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_linux_installer_targets_a_per_user_graphical_install():
    text = (ROOT / "installer" / "cancheria-linux-installer.sh").read_text(
        encoding="utf-8"
    )

    assert 'INSTALL_DIR="$INSTALL_BASE/CANCHERIA"' in text
    assert "python3-tk" in text
    assert "chromium" in text
    assert "cancheria.desktop" in text
    assert "configurar-cancheria.desktop" in text
    assert "Terminal=false" in text
    assert "CANCHERIA_INSTALL_ROOT" in text


def test_linux_updates_create_a_zip_and_preserve_private_data():
    text = (ROOT / "installer" / "cancheria-linux-installer.sh").read_text(
        encoding="utf-8"
    )

    assert "CANCHERIA_BACKUP_ANTES_ACTUALIZAR_" in text
    assert 'BACKUP_DIR="$INSTALL_DIR/Backups"' in text
    assert "legacy_config.py" in text
    assert "runtime wa_profile sessions" in text
    assert 'cp -a "$PRESERVED_CONFIG" "$INSTALL_DIR/$CONFIG_REL"' in text
    assert 'cp -a "$PRESERVED_ROOT_CONFIG" "$INSTALL_DIR/config.py"' in text
    assert 'cmp -s "$PRESERVED_CONFIG" "$INSTALL_DIR/$CONFIG_REL"' in text
    assert 'cmp -s "$PRESERVED_ROOT_CONFIG" "$INSTALL_DIR/config.py"' in text
    assert text.index('cp -a "$INSTALL_DIR/$CONFIG_REL" "$PRESERVED_CONFIG"') < text.index(
        'cp -a "$TEMP_DIR/payload/." "$INSTALL_DIR/"'
    )
    assert text.index('cp -a "$INSTALL_DIR/config.py" "$PRESERVED_ROOT_CONFIG"') < text.index(
        'cp -a "$TEMP_DIR/payload/." "$INSTALL_DIR/"'
    )
    assert "La actualización fue cancelada sin modificar CANCHERIA" in text


def test_linux_builder_uses_the_clean_client_payload():
    text = (ROOT / "scripts" / "build_linux_installer.py").read_text(encoding="utf-8")

    assert "copy_fresh_source" in text
    assert "scan_payload" in text
    assert "write_manifest" in text
    assert "InstaladorCancheriaLinux.run" in text
    assert "tarfile.open" in text
    assert "create_update_archive" in text
    assert 'UPDATE_ASSETS["linux"]' in text
