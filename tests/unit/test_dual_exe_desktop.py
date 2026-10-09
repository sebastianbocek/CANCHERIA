from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_configurator_launcher_is_frozen_aware():
    text = (ROOT / "configurador_cancheria.py").read_text(encoding="utf-8")
    assert 'getattr(sys, "frozen", False)' in text
    assert 'CANCHERIA_INSTALL_ROOT' in text
    assert 'configurador_cancheria_legacy.py' in text


def test_main_gui_exposes_configurator_button_and_exe():
    text = (ROOT / "src" / "cancheria" / "desktop" / "gui.py").read_text(encoding="utf-8")
    assert 'text="CONFIGURACIÓN"' in text
    assert 'configurador_cancheria.exe' in text
    assert 'def open_configurator' in text


def test_main_gui_exposes_integrated_admin_panel():
    text = (ROOT / "src" / "cancheria" / "desktop" / "gui.py").read_text(encoding="utf-8")
    assert 'text="ADMINISTRACIÓN"' in text
    assert "def open_admin_panel" in text
    assert "DesktopAdminService" in text


def test_frozen_worker_bundles_shared_ai_pause_control():
    launcher = (ROOT / "cancheria_desktop.py").read_text(encoding="utf-8")
    build = (ROOT / "scripts" / "build_fresh_installer.ps1").read_text(
        encoding="utf-8"
    )
    assert '"cancheria.desktop.ai_control"' in launcher
    assert '"--hidden-import", "cancheria.desktop.ai_control"' in build


def test_admin_panel_reuses_whatsapp_admin_operations():
    service = (ROOT / "src" / "cancheria" / "admin" / "desktop_service.py").read_text(encoding="utf-8")
    assert 'legacy_callable("marcar_senia_pagada_admin")' in service
    assert 'legacy_callable("cancelar_reserva_por_id_admin")' in service
    assert 'legacy_callable("liberar_reserva_por_id_admin")' in service
    assert 'legacy_callable("resolver_caso_humano")' in service


def test_windows_build_produces_all_desktop_executables():
    text = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    assert '--name cancheria' in text
    assert '--name configurador_cancheria' in text
    assert '--name CancheriaUpdater' in text
    assert '--distpath "."' in text
    assert 'dist\\configurador_cancheria.exe' not in text


def test_release_assembler_copies_all_executables():
    text = (ROOT / "scripts" / "assemble_windows_release.py").read_text(encoding="utf-8")
    assert '("cancheria.exe", "configurador_cancheria.exe", "CancheriaUpdater.exe")' in text


def test_launchers_can_recover_project_root_from_old_dist_location():
    gui = (ROOT / "src" / "cancheria" / "desktop" / "gui.py").read_text(encoding="utf-8")
    desktop = (ROOT / "cancheria_desktop.py").read_text(encoding="utf-8")
    configurator = (ROOT / "configurador_cancheria.py").read_text(encoding="utf-8")
    for text in (gui, desktop, configurator):
        assert "exe_dir.parent" in text
    assert '(path / "WPSetter.py").is_file()' in gui
    assert 'configurador_cancheria_legacy.py' in configurator


def test_release_assembler_prefers_root_executables():
    text = (ROOT / "scripts" / "assemble_windows_release.py").read_text(encoding="utf-8")
    assert 'ROOT / exe_name' in text
    assert 'ROOT / "dist" / exe_name' in text
