from cancheria.legacy_bridge import legacy_callable

def build_help_message(*args, **kwargs):
    return legacy_callable("build_mensaje_ayuda_admin")(*args, **kwargs)
