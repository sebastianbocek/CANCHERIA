from cancheria.legacy_bridge import legacy_callable

def reduce_state(*args, **kwargs):
    """Compatibility facade for ``agent_v2_reduce``."""
    return legacy_callable("agent_v2_reduce")(*args, **kwargs)
