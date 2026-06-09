"""Use case: a service claims the next task from the queue."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from docket.domain import (
    Assignment,
    AssignmentRepository,
    Broker,
    DomainError,
    ServiceRepository,
    ServiceStatus,
    Task,
    TaskRepository,
    TaskStatus,
)


class ClaimTask:
    """Claim the next pending task for a service (PENDING -> RUNNING).

    Pulls the highest-priority task — which leases it to the service — then
    sets it RUNNING, records an Assignment, and marks the service busy. The
    lease is held for the whole execution (renewed via heartbeat) and released
    only on complete/fail; a crashed worker's lease lapses and is reclaimed.
    """

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
        self, service_id: uuid.UUID
    ) -> tuple[Task, Assignment] | None:
        service = await self._services.get(service_id)
        if service is None:
            raise DomainError(f"service {service_id} is not registered")
        if service.status is not ServiceStatus.ONLINE:
            raise DomainError(f"service {service_id} is not online")
        if service.busy:
            raise DomainError(f"service {service_id} is already busy")

        task = await self._broker.pull(service_id)
        if task is None:
            return None

        task.status = TaskStatus.RUNNING
        task.attempts += 1
        task.updated_at = datetime.now(UTC)
        await self._tasks.update(task)

        assignment = Assignment(task_id=task.id, service_id=service_id)
        await self._assignments.add(assignment)

        service.busy = True
        await self._services.update(service)

        return task, assignment
