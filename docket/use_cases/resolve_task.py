"""Use cases: complete or fail a running task."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from docket.domain import (
    AssignmentRepository,
    Broker,
    DomainError,
    ServiceRepository,
    Task,
    TaskRepository,
    TaskStatus,
)

MAX_ATTEMPTS = 3
"""Default dispatch budget before a task is dead-lettered (see task 4)."""


async def _owned_running_task(
    tasks: TaskRepository,
    assignments: AssignmentRepository,
    service_id: uuid.UUID,
    task_id: uuid.UUID,
) -> Task:
    """Load a task the service currently owns and is running, or raise.

    Ownership is the active Assignment for ``task_id``: only the service that
    claimed the task may resolve it.
    """
    assignment = await assignments.get_active(task_id)
    if assignment is None or assignment.service_id != service_id:
        raise DomainError(
            f"task {task_id} is not owned by service {service_id}"
        )
    task = await tasks.get(task_id)
    if task is None or task.status is not TaskStatus.RUNNING:
        raise DomainError(f"task {task_id} is not running")
    return task


async def _free_service(
    services: ServiceRepository, service_id: uuid.UUID
) -> None:
    service = await services.get(service_id)
    if service is not None:
        service.busy = False
        await services.update(service)


async def _release_assignment(
    assignments: AssignmentRepository, task_id: uuid.UUID
) -> None:
    assignment = await assignments.get_active(task_id)
    if assignment is not None:
        assignment.released_at = datetime.now(UTC)
        await assignments.update(assignment)


class CompleteTask:
    """Mark a running task SUCCEEDED, release its lease and its service."""

    def __init__(
        self,
        broker: Broker,
        tasks: TaskRepository,
        services: ServiceRepository,
        assignments: AssignmentRepository,
    ) -> None:
        self._broker = broker
        self._tasks = tasks
        self._services = services
        self._assignments = assignments

    async def execute(
        self,
        service_id: uuid.UUID,
        task_id: uuid.UUID,
        result: dict[str, Any] | None = None,
    ) -> Task:
        task = await _owned_running_task(
            self._tasks, self._assignments, service_id, task_id
        )
        task.status = TaskStatus.SUCCEEDED
        task.result = result
        task.updated_at = datetime.now(UTC)
        await self._tasks.update(task)

        await self._broker.ack(service_id, task_id)
        await _release_assignment(self._assignments, task_id)
        await _free_service(self._services, service_id)
        return task


class FailTask:
    """Fail a running task: requeue under the budget, else dead-letter.

    Under ``max_attempts`` the task returns to PENDING (the lease is released
    so it is pullable again); at the limit it becomes FAILED. Either way the
    Assignment is released and the service freed.
    """

    def __init__(
        self,
        broker: Broker,
        tasks: TaskRepository,
        services: ServiceRepository,
        assignments: AssignmentRepository,
        *,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._broker = broker
        self._tasks = tasks
        self._services = services
        self._assignments = assignments
        self._max_attempts = max_attempts

    async def execute(
        self,
        service_id: uuid.UUID,
        task_id: uuid.UUID,
        error: str,
    ) -> Task:
        task = await _owned_running_task(
            self._tasks, self._assignments, service_id, task_id
        )
        task.error = error
        task.updated_at = datetime.now(UTC)
        if task.attempts < self._max_attempts:
            task.status = TaskStatus.PENDING
        else:
            task.status = TaskStatus.FAILED
        await self._tasks.update(task)

        await self._broker.nack(service_id, task_id)
        await _release_assignment(self._assignments, task_id)
        await _free_service(self._services, service_id)
        return task
