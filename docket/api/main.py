"""FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from docket.api import services, tasks
from docket.domain import DomainError

app = FastAPI(title="Docket")


@app.exception_handler(DomainError)
async def handle_domain_error(
    request: Request, exc: Exception
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(tasks.router)
app.include_router(services.router)
