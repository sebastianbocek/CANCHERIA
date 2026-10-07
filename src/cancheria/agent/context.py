from cancheria.legacy_bridge import legacy_callable

def authorize_context(*args, **kwargs):
    """Compatibility facade for ``_agent_v2_context_authorization``."""
    return legacy_callable("_agent_v2_context_authorization")(*args, **kwargs)

def resolve_context_reference(*args, **kwargs):
    """Compatibility facade for ``_agent_v2_resolve_context_reference``."""
    return legacy_callable("_agent_v2_resolve_context_reference")(*args, **kwargs)
