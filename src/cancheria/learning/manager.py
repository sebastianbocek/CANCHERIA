from cancheria.legacy_bridge import load_legacy_module

def get_learning_manager():
    return getattr(load_legacy_module(), "AGENT_LEARNING_MANAGER")
