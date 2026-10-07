from cancheria.legacy_bridge import legacy_callable

def send_file_to_current_chat(*args, **kwargs):
    return legacy_callable("send_file_to_current_chat")(*args, **kwargs)
