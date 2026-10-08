from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_inno_installer_is_per_user_and_creates_shortcuts():
    text = (ROOT / "installer" / "cancheria.iss").read_text(encoding="utf-8")
    assert "{localappdata}\\Programs\\CANCHERIA" in text
    assert "PrivilegesRequired=lowest" in text
    assert 'Name: "{group}\\CANCHERIA"' in text
    assert 'Name: "{autodesktop}\\CANCHERIA"' in text
    assert "onlyifdoesntexist" in text
    assert "OutputBaseFilename=InstaladorCancheria" in text
    assert "AppId={#MyAppId}" in text
    assert "DefaultDirName={#MyAppDefaultDir}" in text
    assert "Configurar mi negocio ahora (recomendado)" in text


def test_installer_builder_uses_clean_config_and_empty_runtime():
    text = (ROOT / "scripts" / "build_fresh_installer.ps1").read_text(encoding="utf-8")
    assert "config_20261006_213845.py" in text
    assert "sk-[A-Za-z0-9_-]{16,}" in text
    assert '"runtime"' in text
    assert "--self-test" in text
    assert "InstaladorCancheria.exe" in text


def test_installer_creates_zip_backup_before_an_update():
    installer = (ROOT / "installer" / "cancheria.iss").read_text(encoding="utf-8")
    backup_script = (ROOT / "scripts" / "backup_before_update.ps1").read_text(encoding="utf-8")
    assert 'Source: "..\\scripts\\backup_before_update.ps1"' in installer
    assert "Flags: dontcopy" in installer
    assert "function PrepareToInstall" in installer
    assert "ExistingCancheriaInstallation" in installer
    assert "BackupDir := ExpandConstant('{app}\\Backups')" in installer
    assert 'Name: "{app}\\Backups"; Flags: uninsneveruninstall' in installer
    assert "La actualización no modificó los archivos instalados" in installer
    assert "CreateFromDirectory" in backup_script
    assert "CANCHERIA_BACKUP_ANTES_ACTUALIZAR_" in backup_script
    assert '"runtime"' in backup_script
    assert '"wa_profile"' in backup_script
    assert "legacy_config.py" in backup_script


def test_windows_update_explicitly_restores_both_configuration_files():
    installer = (ROOT / "installer" / "cancheria.iss").read_text(encoding="utf-8")
    assert '#define MyAppVersion "0.2.0"' in installer
    assert "uninsneveruninstall" in installer
    assert "PreservedLegacyConfig" in installer
    assert "PreservedRootConfig" in installer
    assert "HasPreservedLegacyConfig" in installer
    assert "HasPreservedRootConfig" in installer
    assert "CopyFile(InstalledLegacyConfig, PreservedLegacyConfig, False)" in installer
    assert "CopyFile(InstalledRootConfig, PreservedRootConfig, False)" in installer
    assert "procedure CurStepChanged(CurStep: TSetupStep)" in installer
    assert "CopyFile(PreservedLegacyConfig, DestinationLegacyConfig, False)" in installer
    assert "CopyFile(PreservedRootConfig, DestinationRootConfig, False)" in installer
    assert installer.index("CopyFile(InstalledLegacyConfig") < installer.index("Exec(PowerShellExe")

