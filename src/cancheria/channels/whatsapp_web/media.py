from cancheria.legacy_bridge import legacy_callable

def read_user_messages_with_pending_media(*args, **kwargs):
    return legacy_callable("read_user_messages_with_pending_media")(*args, **kwargs)

def last_message_media_handler(*args, **kwargs):
    return legacy_callable("last_message_media_handler")(*args, **kwargs)
