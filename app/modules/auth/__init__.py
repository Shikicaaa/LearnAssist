"""Public interface of the auth module: other modules may import only this."""

from app.modules.auth.api import get_current_user, router
from app.modules.auth.schemas import UserOut

__all__ = ["UserOut", "get_current_user", "router"]
