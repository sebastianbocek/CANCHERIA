from cancheria.legacy_bridge import load_legacy_module

def scenario_runner_class():
    return getattr(load_legacy_module(), "AgentScenarioRunner")
