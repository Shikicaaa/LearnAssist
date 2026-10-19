"""Public interface of the artifacts module: other modules may import only this."""

from app.modules.artifacts import tasks  # noqa: F401  (registers the Celery quiz task)
from app.modules.artifacts.api import router

__all__ = ["router"]
