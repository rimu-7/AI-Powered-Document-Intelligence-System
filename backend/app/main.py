"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import get_async_engine
from app.core.exceptions import install_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.modules.documents.models import EMBEDDING_DIMENSIONS

logger = get_logger("docintel.api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise RuntimeError("EMBEDDING_DIMENSIONS does not match the database vector column")
    if settings.s3_create_buckets:
        from app.modules.documents.storage import get_storage

        get_storage().ensure_buckets()
    logger.info("api_started", extra={"env": settings.app_env.value})
    yield
    await get_async_engine().dispose()
    logger.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, service=settings.service_name)
    app = FastAPI(
        title="DocIntel AI",
        version="0.1.0",
        description="Document intelligence and financial verification API. Long-running work returns 202 with a job status URL.",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    install_exception_handlers(app, expose_details=settings.expose_error_details and not settings.is_production)
    app.include_router(health_router)
    app.include_router(api_router)

    # Middleware order: the last added runs first.
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts or ["*"])
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.upload_max_request_bytes)
    app.add_middleware(RequestContextMiddleware)
    return app


app = create_app()
