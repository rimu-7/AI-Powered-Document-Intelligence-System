"""Database engines, sessions, and the declarative base.

The API uses asyncpg through SQLAlchemy's async engine. Celery workers and the
outbox dispatcher use psycopg through a synchronous engine, because document
processing code is CPU-bound and synchronous.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import DateTime, MetaData, create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=utcnow, nullable=False)


class Timestamps(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


# --- Async (API) -------------------------------------------------------------


@lru_cache(maxsize=1)
def get_async_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.async_database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "statement_timeout": str(settings.db_statement_timeout_ms),
                "application_name": settings.service_name,
            },
            "timeout": 10,
        },
    )


def _load_models() -> None:
    """Register every mapped table before the first session is used.

    Foreign keys reference tables by name; a process that imported only part of
    the models (a worker, the dispatcher) would otherwise fail to resolve them.
    Imported lazily to avoid a circular import with the model modules.
    """
    import app.models  # noqa: F401


@lru_cache(maxsize=1)
def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    _load_models()
    return async_sessionmaker(get_async_engine(), expire_on_commit=False, autoflush=False)


async def get_async_session() -> AsyncIterator[AsyncSession]:
    async with get_async_sessionmaker()() as session:
        yield session


# --- Sync (workers) ----------------------------------------------------------


@lru_cache(maxsize=1)
def get_sync_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sync_database_url,
        pool_size=max(2, settings.db_pool_size // 2),
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_pre_ping=True,
        connect_args={
            "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
            "application_name": settings.service_name,
            "connect_timeout": 10,
        },
    )


@lru_cache(maxsize=1)
def get_sync_sessionmaker() -> sessionmaker[Session]:
    _load_models()
    return sessionmaker(get_sync_engine(), expire_on_commit=False, autoflush=False)


@contextmanager
def sync_session() -> Iterator[Session]:
    session = get_sync_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def reset_engines() -> None:
    """Dispose cached engines (used after fork and in tests)."""
    if get_sync_engine.cache_info().currsize:
        get_sync_engine().dispose(close=False)
    get_sync_engine.cache_clear()
    get_sync_sessionmaker.cache_clear()
    get_async_engine.cache_clear()
    get_async_sessionmaker.cache_clear()
