from cancheria.legacy_bridge import legacy_callable

def format_whatsapp_response(*args, **kwargs):
    return legacy_callable("formatear_respuesta_whatsapp_con_ia")(*args, **kwargs)
