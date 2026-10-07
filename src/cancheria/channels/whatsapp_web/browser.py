from cancheria.legacy_bridge import legacy_callable

def acquire_profile_instance_lock(*args, **kwargs):
    return legacy_callable("acquire_profile_instance_lock")(*args, **kwargs)

def release_profile_instance_lock(*args, **kwargs):
    return legacy_callable("release_profile_instance_lock")(*args, **kwargs)
