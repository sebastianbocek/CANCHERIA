from cancheria.legacy_bridge import legacy_callable

def send_message(*args, **kwargs):
    return legacy_callable("send_message")(*args, **kwargs)

def has_unread_user_messages(*args, **kwargs):
    return legacy_callable("has_unread_user_messages")(*args, **kwargs)

def click_first_chat(*args, **kwargs):
    return legacy_callable("click_first_chat")(*args, **kwargs)
