from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from docket.api.dependencies import get_engine
from docket.api.main import app
from docket.infrastructure import metadata
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine

# (service json, auth headers) for a freshly registered service.
Registered = tuple[dict[str, object], dict[str, str]]


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    app.dependency_overrides[get_engine] = lambda: engine
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def register(
    client: httpx.AsyncClient,
) -> Callable[[str], Awaitable[Registered]]:
    """Register a service and return its json plus bearer-auth headers."""

    async def _register(name: str = "worker") -> Registered:
        body = (await client.post("/services", json={"name": name})).json()
        headers = {"Authorization": f"Bearer {body['token']}"}
        return body, headers

    return _register
