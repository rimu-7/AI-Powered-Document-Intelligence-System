"""Each process type must import cleanly on its own (no reliance on app.main)."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "module",
    ["app.workers.tasks", "app.workers.dispatcher", "app.modules.jobs.recovery", "app.main"],
)
def test_entrypoint_imports_resolve_all_foreign_keys(module: str) -> None:
    code = (
        f"import {module}\n"
        "from app.core.database import get_sync_sessionmaker\n"
        "get_sync_sessionmaker()\n"
        "from sqlalchemy.orm import configure_mappers\n"
        "from app.core.database import Base\n"
        "configure_mappers()\n"
        "for t in Base.metadata.sorted_tables:\n"
        "    [fk.column for fk in t.foreign_keys]\n"
        "assert len(Base.metadata.tables) >= 23, len(Base.metadata.tables)\n"
    )
    env = {**os.environ, "APP_ENV": "test"}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]


def test_celery_queues_have_matching_exchanges() -> None:
    from app.modules.jobs.outbox import QUEUES, TASK_ROUTES
    from app.workers.celery_app import celery_app

    declared = {q.name: q for q in celery_app.conf.task_queues}
    assert set(declared) == set(QUEUES)
    for route in TASK_ROUTES.values():
        queue = declared[route.queue]
        assert queue.exchange.name == route.queue and queue.routing_key == route.queue
