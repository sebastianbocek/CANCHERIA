from cancheria.legacy_bridge import legacy_callable

def build_world_state(*args, **kwargs):
    """Compatibility facade for ``construir_world_state_agent_v2``."""
    return legacy_callable("construir_world_state_agent_v2")(*args, **kwargs)
