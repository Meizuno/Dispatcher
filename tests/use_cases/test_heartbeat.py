import uuid
from datetime import UTC, datetime, timedelta

import pytest
from docket.domain import DomainError, Service, Task
from docket.infrastructure import (
    SqlAssignmentRepository,
    SqlBroker,
    SqlServiceRepository,
    SqlTaskRepository,
)
from docket.use_cases import ClaimTask, Heartbeat
from sqlalchemy.ext.asyncio import AsyncConnection


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


async def _claim(
    conn: AsyncConnection, broker: SqlBroker
) -> tuple[Task, uuid.UUID]:
    tasks = SqlTaskRepository(conn)
    services = SqlServiceRepository(conn)
    assignments = SqlAssignmentRepository(conn)
    service = Service(name="worker")
    await services.add(service)
    task = Task(name="compute")
    await broker.enqueue(task)
    claimed = await ClaimTask(broker, tasks, services, assignments).execute(
        service.id
    )
    assert claimed is not None
    return task, service.id


async def test_heartbeat_renews_the_lease(conn: AsyncConnection) -> None:
    clock = FakeClock()
    broker = SqlBroker(conn, lease_timeout=10.0, clock=clock)
    task, service_id = await _claim(conn, broker)  # lease -> t+10

    clock.advance(8.0)
    await Heartbeat(broker).execute(service_id, task.id)  # renew -> t+18
    clock.advance(5.0)  # t+13: past the original deadline

    assert await broker.reclaim_expired() == []  # still held


async def test_heartbeat_by_non_owner_raises(conn: AsyncConnection) -> None:
    broker = SqlBroker(conn)
    task, _service_id = await _claim(conn, broker)
    with pytest.raises(DomainError):
        await Heartbeat(broker).execute(uuid.uuid4(), task.id)
