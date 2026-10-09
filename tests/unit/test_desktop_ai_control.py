from __future__ import annotations

from pathlib import Path

from cancheria.desktop.ai_control import (
    ai_control_path,
    ensure_ai_control,
    read_ai_control,
    write_ai_paused,
)


ROOT = Path(__file__).resolve().parents[2]


def test_ai_control_round_trip_is_persistent_and_install_local(tmp_path: Path):
    assert ai_control_path(tmp_path) == tmp_path / "runtime" / "ai_control.json"

    initial = ensure_ai_control(tmp_path, default_paused=False)
    assert initial["paused"] is False

    paused = write_ai_paused(True, tmp_path, source="test_gui")
    assert paused["paused"] is True
    assert paused["source"] == "test_gui"
    assert read_ai_control(tmp_path)["paused"] is True

    resumed = write_ai_paused(False, tmp_path, source="test_gui")
    assert resumed["paused"] is False
    assert read_ai_control(tmp_path)["paused"] is False


def test_invalid_ai_control_falls_back_without_crashing(tmp_path: Path):
    path = ai_control_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("not-json", encoding="utf-8")

    assert read_ai_control(tmp_path, default_paused=True)["paused"] is True


def test_desktop_exposes_separate_power_and_ai_pause_controls():
    text = (ROOT / "src" / "cancheria" / "desktop" / "gui.py").read_text(
        encoding="utf-8"
    )
    assert '"APAGAR", self.stop_agent' in text
    assert '"PAUSAR IA"' in text
    assert '"REANUDAR IA"' in text
    assert "def toggle_ai_pause" in text
    assert "def _verify_api_in_background" in text


def test_api_verification_no_longer_blocks_worker_startup():
    text = (ROOT / "src" / "cancheria" / "desktop" / "gui.py").read_text(
        encoding="utf-8"
    )
    start_body = text.split("    def start_agent", 1)[1].split(
        "    def _verify_api_in_background", 1
    )[0]
    assert "subprocess.Popen" in start_body
    assert "verify_openai_api_key" not in start_body
    assert "_verify_api_in_background" in start_body


def test_start_agent_launches_worker_before_any_api_verification(tmp_path, monkeypatch):
    from cancheria.desktop import gui

    (tmp_path / "WPSetter.py").write_text("", encoding="utf-8")
    desktop = gui.CancheriaDesktop.__new__(gui.CancheriaDesktop)
    desktop.root_dir = tmp_path
    desktop.profile_dir = tmp_path / "wa_profile"
    desktop.process = None
    desktop.ai_paused = False
    desktop._worker_command = lambda: ["fake-worker"]
    desktop._set_status = lambda *_args: None
    desktop._append_log = lambda *_args: None
    desktop._refresh_ai_pause_state = lambda: None
    desktop._set_running_status = lambda: None

    launched: list[list[str]] = []

    class FakeProcess:
        stdout = None

        def poll(self):
            return None

    def fake_popen(command, **_kwargs):
        launched.append(command)
        return FakeProcess()

    class FakeThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(gui.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(gui.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        gui,
        "verify_openai_api_key",
        lambda *_args: (_ for _ in ()).throw(AssertionError("verification blocked startup")),
    )

    gui.CancheriaDesktop.start_agent(desktop)

    assert launched == [["fake-worker"]]
    assert desktop.process is not None


def test_worker_syncs_desktop_pause_and_whatsapp_admin_state():
    text = (ROOT / "legacy" / "WPSetter_legacy.py").read_text(encoding="utf-8")
    assert "def sync_ai_control_state" in text
    assert "sync_ai_control_state()" in text
    assert 'write_ai_paused(True, source="whatsapp_admin")' in text
    assert 'write_ai_paused(False, source="whatsapp_admin")' in text
