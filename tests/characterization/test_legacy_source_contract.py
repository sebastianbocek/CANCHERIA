from pathlib import Path

def test_legacy_core_retains_critical_agent_v2_markers():
    root=Path(__file__).resolve().parents[2]
    text=(root/"legacy"/"WPSetter_legacy.py").read_text(encoding="utf-8")
    for token in [
        "CANONICAL V200", "CANONICAL V218", "run_agent_v2_invariant_evals",
        "run_agent_v2_e2e_evals", "AGENT_LEARNING_MANAGER",
        "acquire_profile_instance_lock", "event_registration",
    ]:
        assert token in text
