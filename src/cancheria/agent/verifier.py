from cancheria.legacy_bridge import legacy_callable

def verify_semantic_effects(*args, **kwargs):
    """Compatibility facade for ``_agent_v2_verify_semantic_effects``."""
    return legacy_callable("_agent_v2_verify_semantic_effects")(*args, **kwargs)
