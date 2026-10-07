from pathlib import Path
from cancheria.desktop.session_manager import ensure_profile, reset_profile


def test_ensure_profile_creates_directory(tmp_path: Path):
    profile = tmp_path / "wa_profile"
    result = ensure_profile(profile)
    assert result == profile
    assert profile.is_dir()


def test_reset_profile_removes_old_session_but_not_siblings(tmp_path: Path):
    profile = tmp_path / "wa_profile"
    runtime = tmp_path / "runtime"
    profile.mkdir()
    runtime.mkdir()
    (profile / "Cookies").write_text("secret", encoding="utf-8")
    (runtime / "bookings.json").write_text("keep", encoding="utf-8")

    reset_profile(profile)

    assert profile.is_dir()
    assert not (profile / "Cookies").exists()
    assert (runtime / "bookings.json").read_text(encoding="utf-8") == "keep"
