from cancheria.legacy_bridge import legacy_callable

def click_unread(*args, **kwargs):
    return legacy_callable("click_no_leidos")(*args, **kwargs)

def get_phone_from_chat(*args, **kwargs):
    return legacy_callable("get_phone_from_chat")(*args, **kwargs)
