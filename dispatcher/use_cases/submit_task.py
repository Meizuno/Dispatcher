"""Use case: submit a new task."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dispatcher.domain import DomainError, Task, TaskPriority, TaskRepository


class SubmitTask:
    """Submit a new task into the queue (created as PENDING)."""

    def __init__(self, tasks: TaskRepository) -> None:
        self._tasks = tasks

    def execute(
        self,
        name: str,
        payload: Mapping[str, Any] | None = None,
        *,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> Task:
        if not name.strip():
            raise DomainError("task name must not be empty")
        task = Task(
            name=name,
            payload=dict(payload or {}),
            priority=priority,
        )
        self._tasks.add(task)
        return task
