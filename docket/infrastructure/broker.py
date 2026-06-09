"""Pull-based broker over the tasks table (SQL, dialect-agnostic)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from docket.domain import DomainError, Task, TaskStatus
from docket.infrastructure.repositories import dump_task, load_task
from docket.infrastructure.tables import tasks

DEFAULT_LEASE_TIMEOUT = 30.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlBroker:
    """A pull-based broker over the tasks table (Postgres in production).

    The queue is the set of PENDING tasks not currently leased. ``pull``
    claims the highest-priority one with ``SELECT ... FOR UPDATE SKIP LOCKED``
    (concurrency-safe on Postgres; a no-op clause on sqlite) and leases it via
    the locked_by / lease_expires_at columns. The lease is held through
    execution and renewed with ``extend``; ``ack`` and ``nack`` release it
    (the use case has already set the terminal/requeued status). The broker
    never writes task status. ``requeue_service`` releases all of a crashed
    consumer's leases, and ``reclaim_expired`` releases every lapsed lease.
    """

    def __init__(
        self,
        conn: AsyncConnection,
        lease_timeout: float = DEFAULT_LEASE_TIMEOUT,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._conn = conn
        self._lease_timeout = lease_timeout
        self._clock = clock

    async def enqueue(self, task: Task) -> None:
        await self._conn.execute(insert(tasks).values(dump_task(task)))

    async def pull(self, service_id: uuid.UUID) -> Task | None:
        now = self._clock()
        row = (
            (
                await self._conn.execute(
                    select(tasks)
                    .where(
                        tasks.c.status == TaskStatus.PENDING.value,
                        (tasks.c.locked_by.is_(None))
                        | (tasks.c.lease_expires_at <= now),
                    )
                    .order_by(
                        tasks.c.priority.desc(), tasks.c.created_at.asc()
                    )
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        expires = now + timedelta(seconds=self._lease_timeout)
        await self._conn.execute(
            update(tasks)
            .where(tasks.c.id == row["id"])
            .values(locked_by=service_id, lease_expires_at=expires)
        )
        return load_task(row)

    async def extend(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        now = self._clock()
        expires = now + timedelta(seconds=self._lease_timeout)
        result = await self._conn.execute(
            update(tasks)
            .where(
                tasks.c.id == task_id,
                tasks.c.locked_by == service_id,
                tasks.c.lease_expires_at > now,
            )
            .values(lease_expires_at=expires)
        )
        if result.rowcount == 0:
            raise DomainError(
                f"task {task_id} is not leased to service {service_id}"
            )

    async def ack(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        await self._release(service_id, task_id)

    async def nack(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        await self._release(service_id, task_id)

    async def requeue_service(self, service_id: uuid.UUID) -> None:
        await self._conn.execute(
            update(tasks)
            .where(tasks.c.locked_by == service_id)
            .values(locked_by=None, lease_expires_at=None)
        )

    async def reclaim_expired(self) -> list[uuid.UUID]:
        """Release every lapsed lease; return the affected task ids.

        A single atomic UPDATE so concurrent pulls cannot double-claim.
        """
        result = await self._conn.execute(
            update(tasks)
            .where(
                tasks.c.locked_by.is_not(None),
                tasks.c.lease_expires_at <= self._clock(),
            )
            .values(locked_by=None, lease_expires_at=None)
            .returning(tasks.c.id)
        )
        return [row.id for row in result.all()]

    async def _release(
        self, service_id: uuid.UUID, task_id: uuid.UUID
    ) -> None:
        """Clear the lease, but only for the current live-lease holder."""
        result = await self._conn.execute(
            update(tasks)
            .where(
                tasks.c.id == task_id,
                tasks.c.locked_by == service_id,
                tasks.c.lease_expires_at > self._clock(),
            )
            .values(locked_by=None, lease_expires_at=None)
        )
        if result.rowcount == 0:
            raise DomainError(
                f"task {task_id} is not leased to service {service_id}"
            )
