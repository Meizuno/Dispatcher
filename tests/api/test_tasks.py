import uuid
from collections.abc import Awaitable, Callable

import httpx

from tests.api.conftest import Registered

Register = Callable[[str], Awaitable[Registered]]


async def test_submit_then_get_task(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/tasks", json={"name": "compute", "payload": {"x": 1}}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["payload"] == {"x": 1}

    fetched = await client.get(f"/tasks/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "compute"


async def test_get_missing_task_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/tasks/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_submit_empty_name_returns_400(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/tasks", json={"name": "   "})
    assert response.status_code == 400


async def test_list_pending_tasks(client: httpx.AsyncClient) -> None:
    await client.post("/tasks", json={"name": "a"})
    response = await client.get("/tasks/pending")
    assert response.status_code == 200
    assert [t["name"] for t in response.json()] == ["a"]


async def test_claim_requires_authentication(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.post("/tasks/claim")).status_code == 401


async def test_unknown_token_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/tasks/claim", headers={"Authorization": "Bearer nope"}
    )
    assert response.status_code == 401


async def test_claim_marks_service_busy(
    client: httpx.AsyncClient, register: Register
) -> None:
    service, headers = await register("w")
    task = (await client.post("/tasks", json={"name": "compute"})).json()

    claimed = await client.post("/tasks/claim", headers=headers)
    assert claimed.status_code == 200
    assert claimed.json()["id"] == task["id"]

    busy = (await client.get(f"/services/{service['id']}")).json()
    assert busy["busy"] is True


async def test_claim_empty_queue_returns_null(
    client: httpx.AsyncClient, register: Register
) -> None:
    _service, headers = await register("w")
    claimed = await client.post("/tasks/claim", headers=headers)
    assert claimed.status_code == 200
    assert claimed.json() is None


async def test_claim_heartbeat_complete_lifecycle(
    client: httpx.AsyncClient, register: Register
) -> None:
    service, headers = await register("w")
    task = (await client.post("/tasks", json={"name": "compute"})).json()
    await client.post("/tasks/claim", headers=headers)

    beat = await client.post(f"/tasks/{task['id']}/heartbeat", headers=headers)
    assert beat.status_code == 204

    completed = await client.post(
        f"/tasks/{task['id']}/complete",
        json={"result": {"value": 42}},
        headers=headers,
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "succeeded"
    assert body["result"] == {"value": 42}

    freed = (await client.get(f"/services/{service['id']}")).json()
    assert freed["busy"] is False


async def test_fail_requeues_under_budget(
    client: httpx.AsyncClient, register: Register
) -> None:
    _service, headers = await register("w")
    task = (await client.post("/tasks", json={"name": "compute"})).json()
    await client.post("/tasks/claim", headers=headers)

    failed = await client.post(
        f"/tasks/{task['id']}/fail",
        json={"error": "boom"},
        headers=headers,
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "pending"  # attempt 1 of 3

    reclaim = (await client.post("/tasks/claim", headers=headers)).json()
    assert reclaim["id"] == task["id"]


async def test_cannot_complete_another_services_task(
    client: httpx.AsyncClient, register: Register
) -> None:
    _owner, owner_headers = await register("owner")
    _intruder, intruder_headers = await register("intruder")
    task = (await client.post("/tasks", json={"name": "compute"})).json()
    await client.post("/tasks/claim", headers=owner_headers)  # owner claims

    stolen = await client.post(
        f"/tasks/{task['id']}/complete",
        json={},
        headers=intruder_headers,
    )
    assert stolen.status_code == 400


async def test_complete_unclaimed_task_returns_400(
    client: httpx.AsyncClient, register: Register
) -> None:
    _service, headers = await register("w")
    task = (await client.post("/tasks", json={"name": "compute"})).json()
    # never claimed -> caller does not own it
    response = await client.post(
        f"/tasks/{task['id']}/complete", json={}, headers=headers
    )
    assert response.status_code == 400
