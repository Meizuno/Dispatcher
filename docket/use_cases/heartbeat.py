"""Use case: a running worker renews its lease."""

from __future__ import annotations

import uuid

from docket.domain import Broker


class Heartbeat:
    """Renew the lease on a task the service is running.

    Only the current lease owner can renew; the broker rejects a stale or
    foreign lease, signalling the worker it has lost the task.
    """

    def __init__(self, broker: Broker) -> None:
        self._broker = broker

    async def execute(self, service_id: uuid.UUID, task_id: uuid.UUID) -> None:
        await self._broker.extend(service_id, task_id)
