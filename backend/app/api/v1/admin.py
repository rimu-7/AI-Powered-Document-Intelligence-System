"""Organization-scoped operational endpoints (ADMIN)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.deps import Principal, SessionDep, require
from app.core.permissions import Permission
from app.modules.auditing.models import AuditEvent
from app.modules.documents.models import Document
from app.modules.jobs.models import ProcessingRun, ProcessingTask
from app.modules.jobs.schemas import JobOut, TaskOut
from app.modules.reviews.models import ReviewTask
from app.shared.enums import ReviewTaskStatus, RunState, TaskState
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/admin", tags=["admin"])
Admin = Annotated[Principal, Depends(require(Permission.OPS_ADMIN))]
Auditor = Annotated[Principal, Depends(require(Permission.AUDIT_READ))]


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    request_id: str | None
    metadata_json: dict[str, Any]
    created_at: datetime


class OrgStats(BaseModel):
    documents_by_status: dict[str, int]
    jobs_by_state: dict[str, int]
    open_reviews: int
    failed_tasks: int


class DeadLetter(BaseModel):
    job: JobOut
    failed_tasks: list[TaskOut]


@router.get("/stats", response_model=OrgStats)
async def stats(principal: Admin, session: SessionDep) -> OrgStats:
    org = principal.organization_id
    docs = (
        await session.execute(select(Document.status, func.count()).where(Document.organization_id == org).group_by(Document.status))
    ).all()
    jobs = (
        await session.execute(
            select(ProcessingRun.state, func.count()).where(ProcessingRun.organization_id == org).group_by(ProcessingRun.state)
        )
    ).all()
    reviews = (
        await session.execute(
            select(func.count()).where(
                ReviewTask.organization_id == org, ReviewTask.status.in_([ReviewTaskStatus.OPEN, ReviewTaskStatus.IN_PROGRESS])
            )
        )
    ).scalar_one()
    failed = (
        await session.execute(
            select(func.count())
            .select_from(ProcessingTask)
            .join(ProcessingRun, ProcessingRun.id == ProcessingTask.processing_run_id)
            .where(ProcessingRun.organization_id == org, ProcessingTask.task_state == TaskState.FAILED)
        )
    ).scalar_one()
    return OrgStats(
        documents_by_status={s.value: int(n) for s, n in docs},
        jobs_by_state={s.value: int(n) for s, n in jobs},
        open_reviews=int(reviews),
        failed_tasks=int(failed),
    )


@router.get("/dead-letter", response_model=Page[DeadLetter])
async def dead_letter(principal: Admin, session: SessionDep, page: Annotated[PageParams, Depends(page_params)]) -> Page[DeadLetter]:
    """Terminally failed jobs with their failed tasks; replay via POST /jobs/{id}/retry."""
    stmt = select(ProcessingRun).where(ProcessingRun.organization_id == principal.organization_id, ProcessingRun.state == RunState.FAILED)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    runs = (
        (await session.execute(stmt.order_by(ProcessingRun.updated_at.desc(), ProcessingRun.id).limit(page.limit).offset(page.offset)))
        .scalars()
        .all()
    )
    items = []
    for run in runs:
        tasks = (
            (
                await session.execute(
                    select(ProcessingTask)
                    .where(ProcessingTask.processing_run_id == run.id, ProcessingTask.task_state == TaskState.FAILED)
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        items.append(DeadLetter(job=JobOut.model_validate(run), failed_tasks=[TaskOut.model_validate(t) for t in tasks]))
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/audit-events", response_model=Page[AuditEventOut])
async def audit_events(
    principal: Auditor,
    session: SessionDep,
    page: Annotated[PageParams, Depends(page_params)],
    resource_type: str | None = None,
    resource_id: str | None = None,
    action: str | None = None,
) -> Page[AuditEventOut]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == principal.organization_id)
    if resource_type:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditEvent.resource_id == resource_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        (await session.execute(stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id).limit(page.limit).offset(page.offset)))
        .scalars()
        .all()
    )
    return Page(items=[AuditEventOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset)
