from typing import Any, Protocol

from app.modules.jobs.celery_app import celery_app


class TaskQueue(Protocol):
    def enqueue(self, name: str, payload: dict[str, Any]) -> str:
        """Enqueue a task by name and payload. Returns the task ID."""
        ...


class CeleryTaskQueue:
    def enqueue(self, name: str, payload: dict[str, Any]) -> str:
        # By name, not by import: the sender doesn't need to know where the task is defined.
        return celery_app.send_task(name, kwargs=payload).id


class InlineTaskQueue:
    """Executes task immediately in the same process. For testing: without broker and workers."""

    def enqueue(self, name: str, payload: dict[str, Any]) -> str:
        return celery_app.tasks[name].apply(kwargs=payload).id


def get_task_queue() -> TaskQueue:
    return CeleryTaskQueue()
