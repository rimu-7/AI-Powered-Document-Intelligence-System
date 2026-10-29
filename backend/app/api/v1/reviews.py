from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import Principal, SessionDep, require
from app.api.v1.invoices import invoice_detail
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.modules.documents.models import Document
from app.modules.extraction.api_schemas import InvoiceOut, ValidationIssueOut
from app.modules.extraction.models import InvoiceRecord
from app.modules.reviews import service
from app.modules.reviews.models import ReviewAction, ReviewTask
from app.modules.reviews.schemas import ReviewActionOut, ReviewDetail, ReviewQueueItem, ReviewTaskOut
from app.modules.validation.models import ValidationIssue
from app.shared.enums import ResolutionStatus, ReviewTaskStatus
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/reviews", tags=["reviews"])
Reader = Annotated[Principal, Depends(require(Permission.REVIEW_READ))]
Reviewer = Annotated[Principal, Depends(require(Permission.INVOICE_CORRECT))]


@router.get("/queue", response_model=Page[ReviewQueueItem])
async def queue(
    principal: Reader,
    session: SessionDep,
    page: Annotated[PageParams, Depends(page_params)],
    status: ReviewTaskStatus | None = None,
    assigned_to_me: bool = False,
    unassigned: bool = False,
) -> Page[ReviewQueueItem]:
    stmt = (
        select(ReviewTask, InvoiceRecord, Document.original_filename)
        .join(Document, Document.id == ReviewTask.document_id)
        .outerjoin(InvoiceRecord, InvoiceRecord.id == ReviewTask.invoice_record_id)
        .where(ReviewTask.organization_id == principal.organization_id, Document.deleted_at.is_(None))
    )
    stmt = (
        stmt.where(ReviewTask.status == status)
        if status
        else stmt.where(ReviewTask.status.in_([ReviewTaskStatus.OPEN, ReviewTaskStatus.IN_PROGRESS]))
    )
    if assigned_to_me:
        stmt = stmt.where(ReviewTask.assigned_to == principal.user_id)
    if unassigned:
        stmt = stmt.where(ReviewTask.assigned_to.is_(None))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(ReviewTask.created_at, ReviewTask.id).limit(page.limit).offset(page.offset))).all()
    invoice_ids = [inv.id for _, inv, _ in rows if inv is not None]
    counts: dict[uuid.UUID | None, int] = {}
    if invoice_ids:
        counts = {
            iid: int(n)
            for iid, n in (
                await session.execute(
                    select(ValidationIssue.invoice_record_id, func.count())
                    .where(ValidationIssue.invoice_record_id.in_(invoice_ids), ValidationIssue.resolution_status == ResolutionStatus.OPEN)
                    .group_by(ValidationIssue.invoice_record_id)
                )
            ).all()
        }
    items = [
        ReviewQueueItem(
            **ReviewTaskOut.model_validate(task).model_dump(),
            invoice=InvoiceOut.model_validate(inv) if inv is not None else None,
            document_filename=filename,
            open_issue_count=counts.get(inv.id, 0) if inv is not None else 0,
        )
        for task, inv, filename in rows
    ]
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{review_id}", response_model=ReviewDetail)
async def get_review(review_id: uuid.UUID, principal: Reader, session: SessionDep) -> ReviewDetail:
    task = (
        await session.execute(select(ReviewTask).where(ReviewTask.id == review_id, ReviewTask.organization_id == principal.organization_id))
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError("Review not found")
    invoice = None
    issues: list[ValidationIssue] = []
    history: list[ReviewAction] = []
    if task.invoice_record_id:
        inv = await session.get(InvoiceRecord, task.invoice_record_id)
        if inv is not None:
            invoice = await invoice_detail(session, inv)
            issues = list(
                (
                    await session.execute(
                        select(ValidationIssue)
                        .where(ValidationIssue.invoice_record_id == inv.id, ValidationIssue.resolution_status == ResolutionStatus.OPEN)
                        .order_by(ValidationIssue.severity.desc())
                    )
                ).scalars()
            )
            history = list(
                (
                    await session.execute(
                        select(ReviewAction).where(ReviewAction.invoice_record_id == inv.id).order_by(ReviewAction.created_at)
                    )
                ).scalars()
            )
    return ReviewDetail(
        **ReviewTaskOut.model_validate(task).model_dump(),
        invoice=invoice,
        issues=[ValidationIssueOut.model_validate(i) for i in issues],
        history=[ReviewActionOut.model_validate(h) for h in history],
    )


@router.post("/{review_id}/claim", response_model=ReviewTaskOut)
async def claim_review(review_id: uuid.UUID, principal: Reviewer, session: SessionDep, force: bool = False) -> ReviewTask:
    """Assign the review to the caller (ADMIN may take over with force=true)."""
    return await service.claim(session, principal, review_id, force)
