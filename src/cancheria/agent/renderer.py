from cancheria.legacy_bridge import legacy_callable

def render_response(*args, **kwargs):
    """Compatibility facade for ``componer_respuesta_agent_v2``."""
    return legacy_callable("componer_respuesta_agent_v2")(*args, **kwargs)
