"""Worker entry point: celery -A app.worker worker.

Every module that defines tasks is imported here so its tasks get registered in the worker.
"""

from app.modules import sources  # noqa: F401
from app.modules.jobs import celery_app

__all__ = ["celery_app"]
