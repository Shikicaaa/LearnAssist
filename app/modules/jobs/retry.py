from collections.abc import Callable
from typing import Any

from celery import current_task

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


def is_last_attempt() -> bool:
    """True when the running task has used up its retries, so the next failure is final.

    Outside of a task (e.g. a direct call in a test) there is nothing to retry, so it is True.
    """
    if not current_task:
        return True
    running = current_task._get_current_object()
    return running.request.retries >= running.max_retries
