from cancheria.legacy_bridge import legacy_callable

def send_operational_alert(*args, **kwargs):
    return legacy_callable("enviar_aviso_admin_operativo")(*args, **kwargs)
