from cancheria.legacy_bridge import legacy_callable

def mark_reactive_handoff(*args, **kwargs):
    return legacy_callable("_mark_reactive_handoff")(*args, **kwargs)
