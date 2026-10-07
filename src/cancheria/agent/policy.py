from cancheria.legacy_bridge import legacy_callable

def validate_tool(*args, **kwargs):
    """Compatibility facade for ``validar_tool_agent_v2``."""
    return legacy_callable("validar_tool_agent_v2")(*args, **kwargs)

def apply_safe_exit(*args, **kwargs):
    """Compatibility facade for ``aplicar_regla_universal_salida_segura_agent_v2``."""
    return legacy_callable("aplicar_regla_universal_salida_segura_agent_v2")(*args, **kwargs)
