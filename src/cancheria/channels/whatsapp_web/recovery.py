from cancheria.legacy_bridge import legacy_callable

def browser_session_restart_policy(*args, **kwargs):
    return legacy_callable("_browser_session_restart_policy")(*args, **kwargs)
