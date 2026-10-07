from cancheria.legacy_bridge import legacy_callable

def plan_turn(*args, **kwargs):
    """Compatibility facade for ``planificar_agent_v2``."""
    return legacy_callable("planificar_agent_v2")(*args, **kwargs)
