"""Use cases for reading tasks."""

from __future__ import annotations

import uuid

from docket.domain import Task, TaskRepository


class GetTask:
    """Fetch a single task by id (None if it does not exist)."""

    def __init__(self, tasks: TaskRepository) -> None:
        self._tasks = tasks

    def execute(self, task_id: uuid.UUID) -> Task | None:
        return self._tasks.get(task_id)


class ListPendingTasks:
    """List tasks awaiting assignment, highest priority first."""

    def __init__(self, tasks: TaskRepository) -> None:
        self._tasks = tasks

    def execute(self) -> list[Task]:
        return self._tasks.list_pending()
