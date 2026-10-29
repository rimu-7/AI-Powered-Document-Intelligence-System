"""Test configuration.

Integration tests need PostgreSQL (pgvector), Redis, and S3 (MinIO). By default
they are started with Testcontainers; set TEST_DATABASE_URL, TEST_REDIS_URL,
TEST_S3_ENDPOINT_URL (+ TEST_S3_ACCESS_KEY / TEST_S3_SECRET_KEY) to use
existing services instead (CI, docker compose).
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest

# Base settings must be in place before any app module reads them.
os.environ["ENV_FILE"] = ""  # hermetic: never read the developer's .env
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-0123")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("REGISTRATION_MODE", "open")
os.environ.setdefault("S3_CREATE_BUCKETS", "true")
os.environ.setdefault("EXTRACTION_PROVIDER", "local")
os.environ.setdefault("EMBEDDING_PROVIDER", "local")
os.environ.setdefault("AI_EXTERNAL_TRANSMISSION_ENABLED", "false")
os.environ.setdefault("METRICS_PORT", "0")
os.environ.setdefault("TASK_RETRY_BACKOFF_BASE_SECONDS", "0")
os.environ.pop("MISTRAL_API_KEY", None)
os.environ.setdefault("LLM_API_KEY", "")

HAS_TESSERACT = shutil.which("tesseract") is not None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_ocr = pytest.mark.skip(reason="tesseract binary not installed")
    for item in items:
        if "ocr" in item.keywords and not HAS_TESSERACT:
            item.add_marker(skip_ocr)


# --- Service containers -----------------------------------------------------------------


@pytest.fixture(scope="session")
def services() -> Iterator[dict[str, str]]:
    if os.environ.get("TEST_DATABASE_URL"):
        yield {
            "database_url": os.environ["TEST_DATABASE_URL"],
            "redis_url": os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15"),
            "s3_endpoint": os.environ.get("TEST_S3_ENDPOINT_URL", "http://localhost:9000"),
            "s3_key": os.environ.get("TEST_S3_ACCESS_KEY", "minioadmin"),
            "s3_secret": os.environ.get("TEST_S3_SECRET_KEY", "minioadmin"),
        }
        return
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import HttpWaitStrategy

    pg = PostgresContainer("pgvector/pgvector:0.8.1-pg17", username="docintel", password="docintel", dbname="docintel_test")
    redis = RedisContainer("redis:7.4.6-alpine")
    minio = (
        DockerContainer("chainguard/minio:latest")
        .with_env("MINIO_ROOT_USER", "testadmin")
        .with_env("MINIO_ROOT_PASSWORD", "testadmin-secret")
        .with_command("server /data --address :9000")
        .with_exposed_ports(9000)
        .waiting_for(HttpWaitStrategy(9000, "/minio/health/live").for_status_code(200))
    )
    pg.start()
    redis.start()
    minio.start()
    try:
        yield {
            "database_url": f"postgresql+asyncpg://docintel:docintel@{pg.get_container_host_ip()}:{pg.get_exposed_port(5432)}/docintel_test",
            "redis_url": f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0",
            "s3_endpoint": f"http://{minio.get_container_host_ip()}:{minio.get_exposed_port(9000)}",
            "s3_key": "testadmin",
            "s3_secret": "testadmin-secret",
        }
    finally:
        minio.stop()
        redis.stop()
        pg.stop()


def _clear_caches() -> None:
    from app.core.config import get_settings
    from app.core.database import reset_engines
    from app.core.redis import get_async_redis, get_sync_redis
    from app.modules.documents import storage
    from app.modules.documents.uploadthing import reset_uploadthing
    from app.modules.extraction.providers.factory import get_extraction_provider
    from app.modules.parsing.ocr_service import get_ocr_provider
    from app.modules.search.embeddings import get_embedding_provider

    get_settings.cache_clear()
    reset_engines()
    get_async_redis.cache_clear()
    get_sync_redis.cache_clear()
    storage._client.cache_clear()
    storage.get_storage.cache_clear()
    get_extraction_provider.cache_clear()
    get_embedding_provider.cache_clear()
    get_ocr_provider.cache_clear()
    reset_uploadthing()


@pytest.fixture(scope="session")
def configured(services: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, str]]:
    os.environ["DATABASE_URL"] = services["database_url"]
    os.environ["REDIS_URL"] = services["redis_url"]
    os.environ["S3_ENDPOINT_URL"] = services["s3_endpoint"]
    os.environ["S3_ACCESS_KEY_ID"] = services["s3_key"]
    os.environ["S3_SECRET_ACCESS_KEY"] = services["s3_secret"]
    os.environ["S3_BUCKET_ORIGINALS"] = "test-originals"
    os.environ["S3_BUCKET_ARTIFACTS"] = "test-artifacts"
    os.environ["WORKER_TMP_DIR"] = str(tmp_path_factory.mktemp("worker"))
    _clear_caches()

    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from alembic import command
    from app.core.config import get_settings

    engine = create_engine(get_settings().sync_database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    command.upgrade(Config("alembic.ini"), "head")

    from app.modules.documents.storage import get_storage

    get_storage().ensure_buckets()
    yield services
    _clear_caches()


@pytest.fixture
def settings_override(configured: dict[str, str]) -> Iterator[Any]:
    """Temporarily override settings: ``settings_override(KEY="value")``."""
    saved: dict[str, str | None] = {}

    def apply(**values: Any) -> None:
        for key, value in values.items():
            env = key.upper()
            saved.setdefault(env, os.environ.get(env))
            os.environ[env] = str(value)
        _clear_caches()

    yield apply
    for env, value in saved.items():
        if value is None:
            os.environ.pop(env, None)
        else:
            os.environ[env] = value
    _clear_caches()


# --- Pipeline driver --------------------------------------------------------------------


class InlinePublisher:
    def __init__(self) -> None:
        self.task_ids: list[str] = []
        self.fail = False

    def publish(self, event: Any) -> None:
        if self.fail:
            raise ConnectionError("broker down")
        self.task_ids.append(event.payload_json["task_id"])


def drain(max_rounds: int = 200, fail_task_types: set[str] | None = None) -> list[str]:
    """Dispatch outbox events and execute stage tasks in-process until idle."""
    from app.core.database import sync_session
    from app.workers.dispatcher import dispatch_batch
    from app.workers.tasks import RetryRequested, execute_stage

    executed: list[str] = []
    for _ in range(max_rounds):
        publisher = InlinePublisher()
        with sync_session() as session:
            dispatch_batch(session, publisher, 100)
        if not publisher.task_ids:
            return executed
        for task_id in publisher.task_ids:
            for _attempt in range(10):
                try:
                    executed.append(execute_stage(task_id))
                    break
                except RetryRequested:
                    continue
    raise AssertionError("pipeline did not become idle")


@pytest.fixture
def pipeline(configured: dict[str, str]) -> Any:
    return drain


# --- API client -----------------------------------------------------------------------------


@pytest.fixture
async def client(configured: dict[str, str]) -> AsyncIterator[Any]:
    import httpx

    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def register_org(client: Any, name: str | None = None) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    email = f"admin-{suffix}@example.com"
    password = "Correct-Horse-9-Battery"
    r = await client.post(
        "/api/v1/auth/register",
        json={"organization_name": name or f"Org {suffix}", "email": email, "password": password, "full_name": "Test Admin"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    tokens = r.json()
    return {
        "email": email,
        "password": password,
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
        "tokens": tokens,
        "user": None,
    }


@pytest.fixture
async def org(client: Any) -> dict[str, Any]:
    return await register_org(client)


async def upload(client: Any, headers: dict[str, str], files: list[tuple[str, bytes, str]], **kwargs: Any) -> Any:
    return await client.post(
        "/api/v1/documents/upload",
        headers=headers | kwargs.pop("extra_headers", {}),
        files=[("files", (name, data, ctype)) for name, data, ctype in files],
    )
