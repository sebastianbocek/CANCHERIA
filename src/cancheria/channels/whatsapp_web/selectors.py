from cancheria.legacy_bridge import legacy_callable

def ensure_selector_health(*args, **kwargs):
    return legacy_callable("ensure_selector_health")(*args, **kwargs)

def get_best_bubble_selector(*args, **kwargs):
    return legacy_callable("get_best_bubble_selector")(*args, **kwargs)
