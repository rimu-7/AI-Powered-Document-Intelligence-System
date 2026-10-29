"""Liveness, readiness, startup probes and the Prometheus endpoint.

Public probe responses contain only ok/fail per dependency, never error text.
"""

from __future__ import annotations

import asyncio
import hmac
from typing import Any

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.database import get_async_sessionmaker
from app.core.exceptions import error_body
from app.core.metrics import ACTIVE_JOBS, DEPENDENCY_UP, QUEUE_BACKLOG
from app.core.redis import get_async_redis
from app.modules.documents.storage import get_storage
from app.modules.jobs.models import ProcessingRun
from app.modules.jobs.outbox import QUEUES
from app.shared.enums import TERMINAL_RUN_STATES

router = APIRouter(tags=["operations"])


async def _db() -> bool:
    async with get_async_sessionmaker()() as session:
        await session.execute(text("SELECT 1"))
    return True


async def _redis() -> bool:
    return bool(await get_async_redis().ping())


async def _storage() -> bool:
    return bool(await anyio.to_thread.run_sync(get_storage().healthcheck))


async def _check(name: str, fn: Any) -> bool:
    try:
        ok = bool(await asyncio.wait_for(fn(), timeout=3))
    except Exception:  # noqa: BLE001 - probe result only
        ok = False
    DEPENDENCY_UP.labels(name).set(1 if ok else 0)
    return ok


@router.get("/health/live", include_in_schema=False)
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
async def ready() -> JSONResponse:
    results = dict(
        zip(
            ("database", "redis", "storage"),
            await asyncio.gather(_check("database", _db), _check("redis", _redis), _check("storage", _storage)),
            strict=True,
        )
    )
    ok = all(results.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "unavailable", "checks": {k: "ok" if v else "fail" for k, v in results.items()}},
    )


@router.get("/health/startup", include_in_schema=False)
async def startup() -> JSONResponse:
    """Ready to serve once the database schema is at the expected migration head."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    try:
        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        async with get_async_sessionmaker()() as session:
            current = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "unavailable", "checks": {"migrations": "fail"}})
    ok = current == head
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "migrations_pending", "checks": {"migrations": "ok" if ok else "fail"}},
    )


async def _refresh_gauges() -> None:
    try:
        client = get_async_redis()
        for queue in QUEUES:
            QUEUE_BACKLOG.labels(queue).set(await client.llen(queue))  # type: ignore[misc]
    except Exception:  # noqa: BLE001
        pass
    try:
        async with get_async_sessionmaker()() as session:
            rows = (
                await session.execute(
                    select(ProcessingRun.job_type, func.count())
                    .where(ProcessingRun.state.not_in(list(TERMINAL_RUN_STATES)))
                    .group_by(ProcessingRun.job_type)
                )
            ).all()
        for job_type, count in rows:
            ACTIVE_JOBS.labels(job_type.value).set(count)
    except Exception:  # noqa: BLE001
        pass


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    token = get_settings().metrics_token
    if token is not None:
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied.encode(), token.get_secret_value().encode()):
            return JSONResponse(status_code=401, content=error_body("UNAUTHENTICATED", "Metrics token required"))
    await _refresh_gauges()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
