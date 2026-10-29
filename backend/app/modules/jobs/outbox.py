"""Transactional outbox helpers.

Business state and the event that triggers the next unit of work are written
in the same PostgreSQL transaction. A separate dispatcher publishes events to
Celery. Delivery is at-least-once; every handler is idempotent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.jobs.models import OutboxEvent, ProcessingRun, ProcessingTask
from app.shared.enums import TaskState, TaskType

STAGE_EVENT = "stage.run"
CELERY_STAGE_TASK = "docintel.run_stage"


@dataclass(frozen=True)
class Route:
    queue: str
    soft_time_limit: int
    time_limit: int


TASK_ROUTES: dict[TaskType, Route] = {
    TaskType.PREPROCESS: Route("ingestion", 300, 360),
    TaskType.PARSE_PAGES: Route("ocr", 840, 900),
    TaskType.PARSE_SPREADSHEET: Route("ingestion", 1200, 1260),
    TaskType.EXTRACT: Route("extraction", 1500, 1560),
    TaskType.VALIDATE: Route("validation", 240, 300),
    TaskType.INDEX: Route("indexing", 840, 900),
    TaskType.COMPARE: Route("comparison", 600, 660),
}

QUEUES = ("ingestion", "ocr", "extraction", "validation", "comparison", "indexing", "maintenance")


def idempotency_key(run_id: uuid.UUID, task_type: TaskType, page_start: int | None = None, page_end: int | None = None) -> str:
    version = get_settings().parser_version
    span = f":{page_start}-{page_end}" if page_start is not None else ""
    return f"{run_id}:{task_type.value}{span}:v{version}"


def stage_event(task_id: uuid.UUID, run_id: uuid.UUID, task_type: TaskType) -> OutboxEvent:
    return OutboxEvent(
        id=uuid.uuid4(),
        event_type=STAGE_EVENT,
        aggregate_id=run_id,
        payload_json={
            "task_id": str(task_id),
            "run_id": str(run_id),
            "task_type": task_type.value,
        },
    )


def new_task_with_event(
    run: ProcessingRun,
    task_type: TaskType,
    page_start: int | None = None,
    page_end: int | None = None,
) -> tuple[ProcessingTask, OutboxEvent]:
    """Build a task and its outbox event for a brand-new run (no conflict possible)."""
    task = ProcessingTask(
        id=uuid.uuid4(),
        processing_run_id=run.id,
        task_type=task_type,
        task_state=TaskState.PENDING,
        page_start=page_start,
        page_end=page_end,
        attempt_count=0,
        idempotency_key=idempotency_key(run.id, task_type, page_start, page_end),
    )
    return task, stage_event(task.id, run.id, task_type)


def ensure_task(
    session: Session,
    run_id: uuid.UUID,
    task_type: TaskType,
    page_start: int | None = None,
    page_end: int | None = None,
) -> ProcessingTask | None:
    """Create a task + outbox event idempotently. Returns None if it already existed."""
    key = idempotency_key(run_id, task_type, page_start, page_end)
    task_id = uuid.uuid4()
    result = session.execute(
        insert(ProcessingTask)
        .values(
            id=task_id,
            processing_run_id=run_id,
            task_type=task_type,
            task_state=TaskState.PENDING,
            page_start=page_start,
            page_end=page_end,
            attempt_count=0,
            idempotency_key=key,
            error_history_json=[],
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(ProcessingTask.id)
    )
    if result.scalar_one_or_none() is None:
        return None
    session.add(stage_event(task_id, run_id, task_type))
    return session.get(ProcessingTask, task_id)


def republish(session: Session, task: ProcessingTask) -> OutboxEvent:
    event = stage_event(task.id, task.processing_run_id, task.task_type)
    session.add(event)
    return event


def pending_event_exists(session: Session, task_id: uuid.UUID) -> bool:
    stmt = (
        select(OutboxEvent.id)
        .where(
            OutboxEvent.published_at.is_(None),
            OutboxEvent.payload_json["task_id"].astext == str(task_id),
        )
        .limit(1)
    )
    return session.execute(stmt).first() is not None


def payload_for_celery(event: OutboxEvent) -> dict[str, Any]:
    return dict(event.payload_json)
