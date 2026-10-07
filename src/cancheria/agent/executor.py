from cancheria.legacy_bridge import legacy_callable

def execute_tool(*args, **kwargs):
    """Compatibility facade for ``ejecutar_tool_agent_v2``."""
    return legacy_callable("ejecutar_tool_agent_v2")(*args, **kwargs)
