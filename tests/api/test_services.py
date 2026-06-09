import uuid
from collections.abc import Awaitable, Callable

import httpx

from tests.api.conftest import Registered


async def test_register_returns_a_token_once(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post("/services", json={"name": "worker-1"})
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "online"
    assert body["busy"] is False
    assert body["token"]  # plaintext token, shown only here


async def test_token_hash_is_never_exposed(
    client: httpx.AsyncClient,
) -> None:
    created = (await client.post("/services", json={"name": "w"})).json()
    fetched = (await client.get(f"/services/{created['id']}")).json()
    assert "token" not in fetched
    assert "token_hash" not in fetched
    listed = (await client.get("/services")).json()
    assert all("token" not in s and "token_hash" not in s for s in listed)


async def test_get_missing_service_returns_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(f"/services/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_register_empty_name_returns_400(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/services", json={"name": "   "})
    assert response.status_code == 400


async def test_list_services(
    register: Callable[[str], Awaitable[Registered]],
    client: httpx.AsyncClient,
) -> None:
    await register("a")
    await register("b")
    response = await client.get("/services")
    assert response.status_code == 200
    assert {s["name"] for s in response.json()} == {"a", "b"}
