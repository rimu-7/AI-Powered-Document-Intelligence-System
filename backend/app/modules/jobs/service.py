"""Job queries, cancellation, retry/replay, and run creation (async, API)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal
from app.core.exceptions import ConflictError, NotFoundError
from app.core.metrics import JOBS_REPROCESSED
from app.modules.auditing.service import record_audit
from app.modules.comparison.models import DocumentComparison
from app.modules.documents.models import Document
from app.modules.jobs.models import ProcessingRun, ProcessingTask
from app.modules.jobs.outbox import new_task_with_event
from app.modules.jobs.schemas import JobDetail, JobOut, TaskOut
from app.shared.enums import (
    TERMINAL_RUN_STATES,
    ComparisonStatus,
    DocumentStatus,
    JobType,
    RunState,
    TaskState,
    TaskType,
)

FIRST_TASK = {
    JobType.DOCUMENT_PROCESSING: TaskType.PREPROCESS,
    JobType.REVALIDATION: TaskType.VALIDATE,
    JobType.REINDEX: TaskType.INDEX,
    JobType.COMPARISON: TaskType.COMPARE,
    JobType.RECONCILIATION: TaskType.COMPARE,
}


async def get_run(session: AsyncSession, principal: Principal, run_id: uuid.UUID, *, for_update: bool = False) -> ProcessingRun:
    stmt = select(ProcessingRun).where(ProcessingRun.id == run_id, ProcessingRun.organization_id == principal.organization_id)
    if for_update:
        stmt = stmt.with_for_update()
    run = (await session.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise NotFoundError("Job not found")
    return run


async def job_detail(session: AsyncSession, run: ProcessingRun) -> JobDetail:
    counts = (
        await session.execute(
            select(ProcessingTask.task_state, func.count())
            .where(ProcessingTask.processing_run_id == run.id)
            .group_by(ProcessingTask.task_state)
        )
    ).all()
    failed = (
        (
            await session.execute(
                select(ProcessingTask)
                .where(ProcessingTask.processing_run_id == run.id, ProcessingTask.task_state == TaskState.FAILED)
                .order_by(ProcessingTask.page_start)
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    base = JobOut.model_validate(run).model_dump()
    return JobDetail(
        **base,
        stage_history_json=run.stage_history_json or [],
        tasks_by_state={state.value: int(n) for state, n in counts},
        failed_tasks=[TaskOut.model_validate(t) for t in failed],
    )


def build_run(
    principal: Principal,
    job_type: JobType,
    *,
    document_id: uuid.UUID | None,
    payload: dict[str, Any] | None = None,
    parent: ProcessingRun | None = None,
) -> tuple[ProcessingRun, list[Any]]:
    run = ProcessingRun(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        document_id=document_id,
        job_type=job_type,
        state=RunState.QUEUED,
        attempt_number=(parent.attempt_number + 1) if parent else 1,
        parent_run_id=parent.id if parent else None,
        created_by=principal.user_id,
        payload_json=payload or {},
        stage_history_json=[],
    )
    task, event = new_task_with_event(run, FIRST_TASK[job_type])
    return run, [task, event]


async def active_document_run(session: AsyncSession, document_id: uuid.UUID) -> ProcessingRun | None:
    return (
        await session.execute(
            select(ProcessingRun)
            .where(
                ProcessingRun.document_id == document_id,
                ProcessingRun.job_type == JobType.DOCUMENT_PROCESSING,
                ProcessingRun.state.not_in(list(TERMINAL_RUN_STATES)),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def start_document_run(
    session: AsyncSession, principal: Principal, document: Document, parent: ProcessingRun | None, reason: str
) -> ProcessingRun:
    if await active_document_run(session, document.id):
        raise ConflictError("Document already has an active processing job", code="JOB_ALREADY_ACTIVE")
    run, extras = build_run(principal, JobType.DOCUMENT_PROCESSING, document_id=document.id, parent=parent)
    session.add(run)
    await session.flush()
    session.add_all(extras)
    document.current_processing_run_id = run.id
    document.status = DocumentStatus.PROCESSING
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="job.started",
        resource_type="processing_run",
        resource_id=run.id,
        metadata={"reason": reason, "document_id": str(document.id), "parent_run_id": str(parent.id) if parent else None},
    )
    return run


async def retry(session: AsyncSession, principal: Principal, run_id: uuid.UUID) -> ProcessingRun:
    old = await get_run(session, principal, run_id, for_update=True)
    if old.state not in (RunState.FAILED, RunState.CANCELLED):
        raise ConflictError("Only FAILED or CANCELLED jobs can be retried", code="JOB_NOT_RETRYABLE")
    if old.job_type == JobType.DOCUMENT_PROCESSING:
        assert old.document_id is not None
        doc = (
            await session.execute(
                select(Document)
                .where(Document.id == old.document_id, Document.organization_id == principal.organization_id, Document.deleted_at.is_(None))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if doc is None:
            raise ConflictError("Document was deleted", code="DOCUMENT_DELETED")
        if doc.status == DocumentStatus.QUARANTINED:
            raise ConflictError("Quarantined documents cannot be reprocessed", code="FILE_QUARANTINED")
        run = await start_document_run(session, principal, doc, old, "retry")
    else:
        run, extras = build_run(principal, old.job_type, document_id=old.document_id, payload=dict(old.payload_json or {}), parent=old)
        session.add(run)
        await session.flush()
        session.add_all(extras)
        if old.job_type in (JobType.COMPARISON, JobType.RECONCILIATION):
            await session.execute(
                update(DocumentComparison)
                .where(DocumentComparison.processing_run_id == old.id, DocumentComparison.organization_id == principal.organization_id)
                .values(processing_run_id=run.id, status=ComparisonStatus.QUEUED)
            )
    JOBS_REPROCESSED.labels(old.job_type.value).inc()
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="job.retried",
        resource_type="processing_run",
        resource_id=old.id,
        metadata={"new_run_id": str(run.id)},
    )
    await session.commit()
    return run


async def cancel(session: AsyncSession, principal: Principal, run_id: uuid.UUID) -> ProcessingRun:
    run = await get_run(session, principal, run_id, for_update=True)
    if run.state in TERMINAL_RUN_STATES:
        raise ConflictError("Job already finished", code="JOB_ALREADY_TERMINAL")
    now = datetime.now(UTC)
    history = list(run.stage_history_json or [])
    history.append({"from": run.state.value, "to": RunState.CANCELLED.value, "at": now.isoformat(), "by": str(principal.user_id)})
    run.stage_history_json = history
    run.state = RunState.CANCELLED
    run.completed_at = now
    await session.execute(
        update(ProcessingTask)
        .where(ProcessingTask.processing_run_id == run.id, ProcessingTask.task_state.in_([TaskState.PENDING, TaskState.RUNNING]))
        .values(task_state=TaskState.CANCELLED, lease_token=None, lease_expires_at=None)
    )
    if run.document_id and run.job_type == JobType.DOCUMENT_PROCESSING:
        doc = await session.get(Document, run.document_id)
        if doc is not None and doc.current_processing_run_id == run.id:
            doc.status = DocumentStatus.CANCELLED
    if run.job_type in (JobType.COMPARISON, JobType.RECONCILIATION):
        await session.execute(
            update(DocumentComparison).where(DocumentComparison.processing_run_id == run.id).values(status=ComparisonStatus.FAILED)
        )
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="job.cancelled",
        resource_type="processing_run",
        resource_id=run.id,
    )
    await session.commit()
    return run
