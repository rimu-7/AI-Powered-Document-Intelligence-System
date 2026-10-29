"""Task claiming (leases), stage transitions, and failure recording (sync).

Correctness never depends on Redis: a task can run only after a successful
conditional UPDATE in PostgreSQL that hands out a lease token, and results are
committed only while that token is still current.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import DOCUMENT_PROCESSING_DURATION, DOCUMENTS_COMPLETED, JOBS_FAILED
from app.modules.auditing.service import record_audit
from app.modules.comparison.models import DocumentComparison
from app.modules.documents.models import Document, DocumentPage
from app.modules.jobs.models import ProcessingRun, ProcessingTask
from app.modules.jobs.outbox import TASK_ROUTES, ensure_task
from app.modules.jobs.state import assert_transition, compute_progress
from app.shared.enums import (
    ComparisonStatus,
    DocumentStatus,
    JobType,
    PageStatus,
    RunState,
    TaskState,
    TaskType,
)

logger = get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Claim:
    task_id: uuid.UUID
    run_id: uuid.UUID
    task_type: TaskType
    token: uuid.UUID
    attempt: int
    page_start: int | None
    page_end: int | None


def lease_seconds(task_type: TaskType) -> int:
    return max(get_settings().task_lease_seconds, TASK_ROUTES[task_type].time_limit + 60)


def claim_task(session: Session, task_id: uuid.UUID) -> Claim | None:
    now = utcnow()
    token = uuid.uuid4()
    task = session.get(ProcessingTask, task_id)
    if task is None:
        return None
    result = session.execute(
        update(ProcessingTask)
        .where(
            ProcessingTask.id == task_id,
            or_(
                ProcessingTask.task_state == TaskState.PENDING,
                and_(ProcessingTask.task_state == TaskState.RUNNING, ProcessingTask.lease_expires_at < now),
            ),
        )
        .values(
            task_state=TaskState.RUNNING,
            lease_token=token,
            lease_expires_at=now + timedelta(seconds=lease_seconds(task.task_type)),
            attempt_count=ProcessingTask.attempt_count + 1,
            started_at=func.coalesce(ProcessingTask.started_at, now),
            updated_at=now,
        )
        .returning(ProcessingTask.attempt_count)
        .execution_options(synchronize_session=False)
    )
    row = result.first()
    if row is None:
        session.rollback()
        return None
    run = session.get(ProcessingRun, task.processing_run_id)
    if run is None or run.state in (
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.COMPLETED,
        RunState.COMPLETED_WITH_WARNINGS,
        RunState.REQUIRES_REVIEW,
    ):
        session.execute(
            update(ProcessingTask)
            .where(ProcessingTask.id == task_id)
            .values(task_state=TaskState.CANCELLED, lease_token=None, lease_expires_at=None)
        )
        session.commit()
        return None
    session.commit()
    return Claim(task_id, task.processing_run_id, task.task_type, token, int(row[0]), task.page_start, task.page_end)


def lock_run(session: Session, run_id: uuid.UUID) -> ProcessingRun:
    run = session.execute(select(ProcessingRun).where(ProcessingRun.id == run_id).with_for_update()).scalar_one()
    return run


def lock_owned_task(session: Session, claim: Claim) -> ProcessingTask | None:
    task = session.execute(select(ProcessingTask).where(ProcessingTask.id == claim.task_id).with_for_update()).scalar_one_or_none()
    if task is None or task.lease_token != claim.token or task.task_state != TaskState.RUNNING:
        return None
    return task


def mark_task_done(task: ProcessingTask) -> None:
    task.task_state = TaskState.DONE
    task.completed_at = utcnow()
    task.lease_token = None
    task.lease_expires_at = None


def is_cancelled(session: Session, run_id: uuid.UUID) -> bool:
    state = session.execute(select(ProcessingRun.state).where(ProcessingRun.id == run_id)).scalar_one_or_none()
    return state in (RunState.CANCELLED, RunState.FAILED, None)


def transition(session: Session, run: ProcessingRun, target: RunState, *, units_done: int = 0, units_total: int = 0) -> None:
    assert_transition(run.job_type, run.state, target)
    now = utcnow()
    history = list(run.stage_history_json or [])
    history.append({"from": run.state.value, "to": target.value, "at": now.isoformat()})
    run.stage_history_json = history[-50:]
    run.state = target
    run.stage_started_at = now
    run.started_at = run.started_at or now
    run.progress_percent = compute_progress(
        run.job_type, target, units_done=units_done, units_total=units_total, previous=run.progress_percent
    )
    if target.is_terminal:
        run.completed_at = now


def advance(session: Session, run: ProcessingRun, target: RunState, next_task: TaskType | None) -> None:
    """Transition and enqueue the next stage in the same transaction."""
    transition(session, run, target)
    if next_task is not None:
        ensure_task(session, run.id, next_task)


def record_task_error(session: Session, task_id: uuid.UUID, code: str, message: str, *, release: bool) -> None:
    task = session.get(ProcessingTask, task_id)
    if task is None:
        return
    history = list(task.error_history_json or [])
    history.append({"at": utcnow().isoformat(), "code": code, "message": message[:300], "attempt": task.attempt_count})
    task.error_history_json = history[-20:]
    task.last_error_code = code
    task.last_error_message = message[:500]
    if release and task.task_state == TaskState.RUNNING:
        task.task_state = TaskState.PENDING
        task.lease_token = None
        task.lease_expires_at = None


def fail_run(session: Session, run: ProcessingRun, code: str, message: str, *, actor: str = "system") -> None:
    if run.state.is_terminal:
        return
    transition(session, run, RunState.FAILED)
    run.error_code = code
    run.sanitized_error_message = message[:500]
    session.execute(
        update(ProcessingTask)
        .where(ProcessingTask.processing_run_id == run.id, ProcessingTask.task_state.in_([TaskState.PENDING, TaskState.RUNNING]))
        .values(task_state=TaskState.CANCELLED, lease_token=None, lease_expires_at=None)
    )
    if run.document_id and run.job_type == JobType.DOCUMENT_PROCESSING:
        doc = session.get(Document, run.document_id)
        if doc is not None and doc.current_processing_run_id == run.id and doc.status != DocumentStatus.QUARANTINED:
            doc.status = DocumentStatus.FAILED
    if run.job_type in (JobType.COMPARISON, JobType.RECONCILIATION):
        session.execute(
            update(DocumentComparison).where(DocumentComparison.processing_run_id == run.id).values(status=ComparisonStatus.FAILED)
        )
    JOBS_FAILED.labels(run.job_type.value, code).inc()
    record_audit(
        session,
        organization_id=run.organization_id,
        actor_id=None,
        action="job.failed",
        resource_type="processing_run",
        resource_id=run.id,
        metadata={"error_code": code, "job_type": run.job_type.value, "actor": actor},
    )
    logger.warning("run_failed", extra={"run_id": str(run.id), "error_code": code})


def fail_task_terminally(session: Session, claim: Claim, code: str, message: str) -> None:
    """Retries exhausted or permanent error: dead-letter the task.

    A failed page batch does not fail the document: its pages are marked FAILED
    and the run continues (partial completion). Any other failed stage fails
    the run.
    """
    task = session.execute(select(ProcessingTask).where(ProcessingTask.id == claim.task_id).with_for_update()).scalar_one_or_none()
    run = lock_run(session, claim.run_id)
    if task is None:
        return
    record_task_error(session, task.id, code, message, release=False)
    task.task_state = TaskState.FAILED
    task.completed_at = utcnow()
    task.lease_token = None
    task.lease_expires_at = None
    session.flush()
    if claim.task_type == TaskType.PARSE_PAGES and run.document_id and claim.page_start is not None and claim.page_end is not None:
        mark_pages_failed(session, run, claim.page_start, claim.page_end, code)
        maybe_finish_parsing(session, run)
    else:
        fail_run(session, run, code, message)


def mark_pages_failed(session: Session, run: ProcessingRun, start: int, end: int, code: str) -> None:
    from sqlalchemy.dialects.postgresql import insert

    assert run.document_id is not None
    for page_number in range(start, end + 1):
        session.execute(
            insert(DocumentPage)
            .values(
                id=uuid.uuid4(),
                organization_id=run.organization_id,
                document_id=run.document_id,
                page_number=page_number,
                processing_status=PageStatus.FAILED,
                error_code=code,
                character_count=0,
                parser_version=get_settings().parser_version,
                metadata_json={},
            )
            .on_conflict_do_update(
                index_elements=["document_id", "page_number"],
                set_={"processing_status": PageStatus.FAILED, "error_code": code},
                where=DocumentPage.processing_status != PageStatus.DONE,
            )
        )


def page_counts(session: Session, run: ProcessingRun) -> tuple[int, int]:
    rows = session.execute(
        select(DocumentPage.processing_status, func.count())
        .where(
            DocumentPage.document_id == run.document_id,
            DocumentPage.page_number <= max(run.pages_total, 0),
        )
        .group_by(DocumentPage.processing_status)
    ).all()
    counts = {status: int(n) for status, n in rows}
    return counts.get(PageStatus.DONE, 0), counts.get(PageStatus.FAILED, 0)


def maybe_finish_parsing(session: Session, run: ProcessingRun) -> None:
    """Called with the run row locked, after a parse batch reached a terminal state."""
    done, failed = page_counts(session, run)
    run.pages_completed, run.pages_failed = done, failed
    run.progress_percent = compute_progress(
        run.job_type, run.state, units_done=done + failed, units_total=run.pages_total, previous=run.progress_percent
    )
    if run.state != RunState.PARSING:
        return
    open_tasks = session.execute(
        select(func.count()).where(
            ProcessingTask.processing_run_id == run.id,
            ProcessingTask.task_type == TaskType.PARSE_PAGES,
            ProcessingTask.task_state.in_([TaskState.PENDING, TaskState.RUNNING]),
        )
    ).scalar_one()
    if open_tasks:
        return
    if done == 0:
        fail_run(session, run, "ALL_PAGES_FAILED", "No page could be processed")
        return
    advance(session, run, RunState.EXTRACTING, TaskType.EXTRACT)


def final_state_for(session: Session, run: ProcessingRun, document: Document | None) -> RunState:
    from app.modules.reviews.models import ReviewTask
    from app.shared.enums import ReviewTaskStatus, ValidationOutcome

    if document is None:
        return RunState.COMPLETED
    open_reviews = session.execute(
        select(func.count()).where(
            ReviewTask.document_id == document.id,
            ReviewTask.status.in_([ReviewTaskStatus.OPEN, ReviewTaskStatus.IN_PROGRESS]),
        )
    ).scalar_one()
    if (
        open_reviews
        or document.review_required
        or document.validation_outcome in (ValidationOutcome.REQUIRES_REVIEW, ValidationOutcome.FAILED)
    ):
        return RunState.REQUIRES_REVIEW
    if run.pages_failed or document.validation_outcome == ValidationOutcome.PASSED_WITH_WARNINGS:
        return RunState.COMPLETED_WITH_WARNINGS
    return RunState.COMPLETED


_DOC_STATUS = {
    RunState.COMPLETED: DocumentStatus.COMPLETED,
    RunState.COMPLETED_WITH_WARNINGS: DocumentStatus.COMPLETED_WITH_WARNINGS,
    RunState.REQUIRES_REVIEW: DocumentStatus.REQUIRES_REVIEW,
}


def finalize_document_run(session: Session, run: ProcessingRun, document: Document | None) -> RunState:
    target = final_state_for(session, run, document)
    transition(session, run, target)
    if document is not None and (run.job_type != JobType.DOCUMENT_PROCESSING or document.current_processing_run_id == run.id):
        document.status = _DOC_STATUS[target]
    DOCUMENTS_COMPLETED.labels(target.value).inc()
    if run.job_type == JobType.DOCUMENT_PROCESSING and run.started_at and document is not None:
        DOCUMENT_PROCESSING_DURATION.labels(document.file_kind.value, target.value).observe((utcnow() - run.created_at).total_seconds())
    record_audit(
        session,
        organization_id=run.organization_id,
        actor_id=None,
        action="job.completed",
        resource_type="processing_run",
        resource_id=run.id,
        metadata={"state": target.value, "job_type": run.job_type.value, "document_id": str(run.document_id) if run.document_id else None},
    )
    return target


def run_payload(run: ProcessingRun) -> dict[str, Any]:
    return dict(run.payload_json or {})
