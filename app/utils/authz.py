from functools import wraps
from flask import abort
from flask_login import current_user, login_required

# Jerarquía: mientras más alto, más permisos.
ROLE_LEVEL = {
    "USER": 1,
    "ADMIN": 2,
    "SUPERADMIN": 3,
}

def role_level(role: str) -> int:
    return ROLE_LEVEL.get((role or "").upper(), 0)

def min_role_required(min_role: str):
    """
    Permite min_role o superior.
    Uso:
      @min_role_required("USER")
      @min_role_required("ADMIN")
      @min_role_required("SUPERADMIN")
    """
    min_level = role_level(min_role)

    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            current_level = role_level(getattr(current_user, "role", None))
            if current_level < min_level:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper

    return decorator
