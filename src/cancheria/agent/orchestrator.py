from cancheria.legacy_bridge import legacy_callable

def execute_turn(*args, **kwargs):
    """Compatibility facade for ``ejecutar_agente_real_v2_turno``."""
    return legacy_callable("ejecutar_agente_real_v2_turno")(*args, **kwargs)
