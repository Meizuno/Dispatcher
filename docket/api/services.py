"""Service routes."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from docket.api.dependencies import ServiceRepo
from docket.domain import ServiceStatus
from docket.use_cases import GetService, ListServices, RegisterService


class ServiceCreate(BaseModel):
    name: str


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: ServiceStatus
    busy: bool
    registered_at: datetime
    last_seen_at: datetime


class ServiceRegistered(ServiceOut):
    # The bearer token is returned exactly once, at registration.
    token: str


router = APIRouter(prefix="/services", tags=["services"])


@router.post("", status_code=201)
async def register_service(
    body: ServiceCreate, services: ServiceRepo
) -> ServiceRegistered:
    service, token = await RegisterService(services).execute(body.name)
    out = ServiceOut.model_validate(service)
    return ServiceRegistered(**out.model_dump(), token=token)


@router.get("")
async def list_services(services: ServiceRepo) -> list[ServiceOut]:
    return [
        ServiceOut.model_validate(service)
        for service in await ListServices(services).execute()
    ]


@router.get("/{service_id}")
async def get_service(
    service_id: uuid.UUID, services: ServiceRepo
) -> ServiceOut:
    service = await GetService(services).execute(service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="service not found")
    return ServiceOut.model_validate(service)
