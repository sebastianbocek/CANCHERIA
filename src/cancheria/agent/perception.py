from cancheria.legacy_bridge import legacy_callable

def perceive_turn(*args, **kwargs):
    """Compatibility facade for ``percibir_turno_agent_v2``."""
    return legacy_callable("percibir_turno_agent_v2")(*args, **kwargs)
