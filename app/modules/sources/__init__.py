"""Public interface of the sources module: other modules may import only this."""

from app.modules.sessions import register_delete_hook
from app.modules.sources import tasks  # noqa: F401  (registers the Celery ingestion task)
from app.modules.sources.api import router
from app.modules.sources.service import collect_files_for_deletion

register_delete_hook(collect_files_for_deletion)

__all__ = ["router"]
