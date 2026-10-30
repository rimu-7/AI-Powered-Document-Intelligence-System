from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import and_, func, or_, select

from app.api.deps import Principal, SessionDep, require
from app.core.permissions import Permission
from app.modules.documents.models import Document
from app.modules.documents.service import get_document
from app.modules.extraction.models import InvoiceRecord
from app.modules.jobs import service
from app.modules.jobs.models import ProcessingRun
from app.modules.jobs.schemas import ActiveJobOut, JobAccepted, JobDetail, JobOut
from app.modules.reviews.models import ReviewTask
from app.shared.enums import TERMINAL_RUN_STATES, JobType, ReviewTaskStatus, RunState
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(tags=["jobs"])
Reader = Annotated[Principal, Depends(require(Permission.JOB_READ))]
Manager = Annotated[Principal, Depends(require(Permission.JOB_MANAGE))]


async def _page(session: SessionDep, stmt, page: PageParams) -> Page[JobOut]:  # type: ignore[no-untyped-def]
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                stmt.order_by(ProcessingRun.created_at.desc(), ProcessingRun.id.desc()).limit(page.limit).offset(page.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page(items=[JobOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


@router.get("/jobs", response_model=Page[JobOut])
async def list_jobs(
    principal: Reader,
    session: SessionDep,
    page: Annotated[PageParams, Depends(page_params)],
    state: RunState | None = None,
    job_type: JobType | None = None,
) -> Page[JobOut]:
    stmt = select(ProcessingRun).where(ProcessingRun.organization_id == principal.organization_id)
    if state:
        stmt = stmt.where(ProcessingRun.state == state)
    if job_type:
        stmt = stmt.where(ProcessingRun.job_type == job_type)
    return await _page(session, stmt, page)


# Finished runs stay in the list this long, so the outcome is seen once.
RECENTLY_FINISHED = timedelta(minutes=2)


@router.get("/jobs/active", response_model=list[ActiveJobOut])
async def active_jobs(principal: Reader, session: SessionDep) -> list[ActiveJobOut]:
    """Documents being processed now, plus those that finished in the last two minutes."""
    since = datetime.now(UTC) - RECENTLY_FINISHED
    invoices = (
        select(func.count())
        .where(InvoiceRecord.document_id == ProcessingRun.document_id, InvoiceRecord.superseded_at.is_(None))
        .correlate(ProcessingRun)
        .scalar_subquery()
    )
    open_reviews = (
        select(func.count())
        .where(
            ReviewTask.document_id == ProcessingRun.document_id,
            ReviewTask.status.in_([ReviewTaskStatus.OPEN, ReviewTaskStatus.IN_PROGRESS]),
        )
        .correlate(ProcessingRun)
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(ProcessingRun, Document.original_filename, Document.file_kind, invoices, open_reviews)
            .join(Document, and_(Document.id == ProcessingRun.document_id, Document.organization_id == ProcessingRun.organization_id))
            .where(
                ProcessingRun.organization_id == principal.organization_id,
                ProcessingRun.job_type == JobType.DOCUMENT_PROCESSING,
                Document.deleted_at.is_(None),
                or_(
                    ProcessingRun.state.not_in(list(TERMINAL_RUN_STATES)),
                    ProcessingRun.completed_at >= since,
                ),
            )
            .order_by(ProcessingRun.created_at.desc(), ProcessingRun.id.desc())
            .limit(100)
        )
    ).all()
    return [
        ActiveJobOut(
            job_id=run.id,
            document_id=run.document_id,
            filename=filename,
            file_kind=file_kind,
            state=run.state,
            pages_total=run.pages_total,
            pages_completed=run.pages_completed,
            pages_failed=run.pages_failed,
            progress_percent=run.progress_percent,
            created_at=run.created_at,
            completed_at=run.completed_at,
            sanitized_error_message=run.sanitized_error_message,
            invoices=n_invoices,
            open_reviews=n_reviews,
        )
        for run, filename, file_kind, n_invoices, n_reviews in rows
    ]


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: uuid.UUID, principal: Reader, session: SessionDep) -> JobDetail:
    run = await service.get_run(session, principal, job_id)
    return await service.job_detail(session, run)


@router.get("/documents/{document_id}/jobs", response_model=Page[JobOut])
async def document_jobs(
    document_id: uuid.UUID, principal: Reader, session: SessionDep, page: Annotated[PageParams, Depends(page_params)]
) -> Page[JobOut]:
    doc = await get_document(session, principal, document_id)
    stmt = select(ProcessingRun).where(ProcessingRun.organization_id == principal.organization_id, ProcessingRun.document_id == doc.id)
    return await _page(session, stmt, page)


@router.post("/jobs/{job_id}/retry", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def retry_job(job_id: uuid.UUID, principal: Manager, session: SessionDep) -> JobAccepted:
    """Replay a FAILED/CANCELLED job as a new attempt. Completed pages are reused."""
    run = await service.retry(session, principal, job_id)
    return JobAccepted(job_id=run.id, status_url=f"/api/v1/jobs/{run.id}", state=run.state)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: uuid.UUID, principal: Manager, session: SessionDep) -> ProcessingRun:
    return await service.cancel(session, principal, job_id)


@router.post("/documents/{document_id}/reprocess", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(document_id: uuid.UUID, principal: Manager, session: SessionDep) -> JobAccepted:
    """Run the full pipeline again (e.g. after a parser upgrade). Earlier invoice
    records are superseded, not deleted."""
    doc = await get_document(session, principal, document_id, for_update=True)
    parent = await session.get(ProcessingRun, doc.current_processing_run_id) if doc.current_processing_run_id else None
    run = await service.start_document_run(session, principal, doc, parent, "reprocess")
    await session.commit()
    return JobAccepted(job_id=run.id, status_url=f"/api/v1/jobs/{run.id}", state=run.state)
