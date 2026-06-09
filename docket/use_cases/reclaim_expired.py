"""Use case: reclaim tasks whose worker lease has lapsed (crash recovery)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from docket.domain import (
    AssignmentRepository,
    Broker,
    ServiceRepository,
    TaskRepository,
    TaskStatus,
)
from docket.use_cases.resolve_task import MAX_ATTEMPTS


class ReclaimExpiredTasks:
    """Recover work abandoned by crashed workers.

    Releases every lapsed lease, then applies the failure policy to each
    reclaimed RUNNING task: requeue to PENDING while under ``max_attempts``,
    else dead-letter to FAILED. The Assignment is released and the service
    freed. Run as a single periodic sweep. (A task still PENDING with a lapsed
    lease — a worker that died mid-claim — needs no status change; releasing
    the lease already makes it pullable again.)
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

    async def execute(self) -> list[uuid.UUID]:
        reclaimed = await self._broker.reclaim_expired()
        for task_id in reclaimed:
            task = await self._tasks.get(task_id)
            if task is None or task.status is not TaskStatus.RUNNING:
                continue

            task.error = "lease expired (worker presumed crashed)"
            task.updated_at = datetime.now(UTC)
            if task.attempts < self._max_attempts:
                task.status = TaskStatus.PENDING
            else:
                task.status = TaskStatus.FAILED
            await self._tasks.update(task)

            assignment = await self._assignments.get_active(task_id)
            if assignment is not None:
                service = await self._services.get(assignment.service_id)
                if service is not None:
                    service.busy = False
                    await self._services.update(service)
                assignment.released_at = datetime.now(UTC)
                await self._assignments.update(assignment)
        return reclaimed
