# Importar todos los modelos aquí asegura que SQLAlchemy los registre
# en la metadata antes de correr migraciones.

from .user import User  # noqa: F401
from .lab import Lab  # noqa: F401
from .material import Material  # noqa: F401
from .logbook import LogbookEvent  # noqa: F401
from .debt import Debt  # noqa: F401
from .reservation import Reservation  # noqa: F401
from .lost_found import LostFound  # noqa: F401
from .software import Software  # noqa: F401

