from cancheria.legacy_bridge import legacy_callable

def infer_goals(*args, **kwargs):
    """Compatibility facade for ``inferir_goals_agent_v2``."""
    return legacy_callable("inferir_goals_agent_v2")(*args, **kwargs)
