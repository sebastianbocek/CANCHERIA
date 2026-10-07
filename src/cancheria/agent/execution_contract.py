from cancheria.legacy_bridge import legacy_callable

def build_execution_contract(*args, **kwargs):
    """Compatibility facade for ``_agent_v2_build_execution_contract``."""
    return legacy_callable("_agent_v2_build_execution_contract")(*args, **kwargs)
