import pytest
from docket.domain import DomainError, ServiceStatus
from docket.security import hash_token
from docket.use_cases import RegisterService

from tests.fakes import FakeServiceRepository


async def test_creates_online_idle_service(
    services: FakeServiceRepository,
) -> None:
    service, _token = await RegisterService(services).execute("worker-1")
    assert service.name == "worker-1"
    assert service.status is ServiceStatus.ONLINE
    assert service.busy is False


async def test_persists_to_repository(
    services: FakeServiceRepository,
) -> None:
    service, _token = await RegisterService(services).execute("worker-1")
    assert await services.get(service.id) == service


async def test_issues_a_token_and_stores_only_its_hash(
    services: FakeServiceRepository,
) -> None:
    service, token = await RegisterService(services).execute("worker-1")
    assert token  # plaintext returned to the caller
    assert service.token_hash == hash_token(token)
    assert token not in service.token_hash  # the plaintext is not stored
    # the service is resolvable by the token's hash
    assert await services.get_by_token_hash(hash_token(token)) == service


async def test_empty_name_raises(services: FakeServiceRepository) -> None:
    with pytest.raises(DomainError):
        await RegisterService(services).execute("   ")
