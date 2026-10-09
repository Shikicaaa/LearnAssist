from celery import Celery

from app.shared.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "rag",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Task is confirmed only when it is completed: if a worker crashes in the middle of a task,
    # the task is returned to the queue. It is safe to do so because our tasks are idempotent.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)
