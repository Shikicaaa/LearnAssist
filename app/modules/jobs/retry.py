from collections.abc import Callable
from typing import Any

from app.modules.jobs.celery_app import celery_app


class TransientError(Exception):
    """Temporary error (database, network): the task is retried with increasing delays."""


class PermanentError(Exception):
    """Permanent error (e.g., invalid file): retrying would not help, the task is not retried."""


def task(name: str) -> Callable[..., Any]:
    """Register a Celery task. Only TransientError triggers retries: up to 5 times, with
    exponential backoff (1s, 2s, 4s...) up to 5 minutes and random jitter."""
    return celery_app.task(
        name=name,
        autoretry_for=(TransientError,),
        retry_backoff=True,
        retry_backoff_max=300,
        retry_jitter=True,
        max_retries=5,
    )
