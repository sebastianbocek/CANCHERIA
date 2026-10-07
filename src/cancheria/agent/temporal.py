from cancheria.legacy_bridge import legacy_callable

def resolve_current_turn_date(*args, **kwargs):
    """Compatibility facade for ``_agent_v2_resolve_current_turn_date_with_ai``."""
    return legacy_callable("_agent_v2_resolve_current_turn_date_with_ai")(*args, **kwargs)
