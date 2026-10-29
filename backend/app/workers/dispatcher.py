"""Outbox dispatcher: publishes committed outbox events to Celery.

Several dispatcher replicas can run safely: rows are claimed with
``FOR UPDATE SKIP LOCKED``. If the process dies after publishing but before
committing ``published_at``, the event is published again (at-least-once);
stage handlers are idempotent.

Run: ``python -m app.workers.dispatcher``
"""

from __future__ import annotations

import signal
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register every table so foreign keys resolve)
from app.core.config import get_settings
from app.core.database import sync_session
from app.core.logging import configure_logging, get_logger
from app.core.metrics import OUTBOX_FAILURES, OUTBOX_LAG, OUTBOX_PUBLISHED
from app.modules.jobs.models import OutboxEvent
from app.modules.jobs.outbox import CELERY_STAGE_TASK, STAGE_EVENT, TASK_ROUTES
from app.shared.enums import TaskType

logger = get_logger("docintel.dispatcher")


class Publisher(Protocol):
    def publish(self, event: OutboxEvent) -> None: ...


class CeleryPublisher:
    def __init__(self) -> None:
        from app.workers.celery_app import celery_app

        self.app = celery_app

    def publish(self, event: OutboxEvent) -> None:
        payload: dict[str, Any] = dict(event.payload_json)
        if event.event_type != STAGE_EVENT:
            raise ValueError(f"unknown outbox event type {event.event_type}")
        route = TASK_ROUTES[TaskType(payload["task_type"])]
        self.app.send_task(
            CELERY_STAGE_TASK,
            kwargs={
                "task_id": payload["task_id"],
                "run_id": payload.get("run_id"),
                "task_type": payload["task_type"],
                "queue": route.queue,
            },
            queue=route.queue,
            task_id=str(event.id),
            soft_time_limit=route.soft_time_limit,
            time_limit=route.time_limit,
            retry=True,
            retry_policy={"max_retries": 3, "interval_start": 0.2, "interval_step": 0.5, "interval_max": 2},
        )


def dispatch_batch(session: Session, publisher: Publisher, batch_size: int) -> int:
    now = datetime.now(UTC)
    events = list(
        session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None), OutboxEvent.available_at <= now)
            .order_by(OutboxEvent.available_at, OutboxEvent.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    published = 0
    for event in events:
        try:
            publisher.publish(event)
        except Exception as exc:  # noqa: BLE001 - broker outage: back off this event
            event.attempt_count += 1
            delay = min(300, 2 ** min(event.attempt_count, 8))
            event.available_at = now + timedelta(seconds=delay)
            event.last_error = f"{type(exc).__name__}"[:500]
            OUTBOX_FAILURES.inc()
            logger.warning("outbox_publish_failed", extra={"event_id": str(event.id), "attempt": event.attempt_count})
            continue
        event.published_at = datetime.now(UTC)
        event.attempt_count += 1
        published += 1
        OUTBOX_PUBLISHED.labels(event.event_type).inc()
        OUTBOX_LAG.observe((event.published_at - event.created_at).total_seconds())
    session.commit()
    return published


_running = True


def _stop(*_: object) -> None:
    global _running
    _running = False


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, service="docintel-dispatcher")
    from app.workers.metrics_server import start_worker_metrics_server

    start_worker_metrics_server()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    publisher = CeleryPublisher()
    logger.info("dispatcher_started")
    backoff = 1.0
    while _running:
        try:
            with sync_session() as session:
                count = dispatch_batch(session, publisher, settings.outbox_batch_size)
            backoff = 1.0
            if count == 0:
                time.sleep(settings.outbox_poll_interval_seconds)
        except Exception:
            logger.exception("dispatcher_loop_error")
            time.sleep(backoff)
            backoff = min(30.0, backoff * 2)
    logger.info("dispatcher_stopped")


if __name__ == "__main__":
    main()
