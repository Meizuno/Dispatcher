"""Use case: register a service."""

from __future__ import annotations

from docket.domain import DomainError, Service, ServiceRepository
from docket.security import generate_token, hash_token


class RegisterService:
    """Register a new service (created ONLINE and free).

    Issues a bearer token, persisting only its hash. Returns the service and
    the plaintext token together; the token is shown to the caller this once
    and cannot be recovered afterwards.
    """

    def __init__(self, services: ServiceRepository) -> None:
        self._services = services

    async def execute(self, name: str) -> tuple[Service, str]:
        if not name.strip():
            raise DomainError("service name must not be empty")
        token = generate_token()
        service = Service(name=name, token_hash=hash_token(token))
        await self._services.add(service)
        return service, token
