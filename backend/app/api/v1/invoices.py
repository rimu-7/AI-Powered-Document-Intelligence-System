"""Extraction, invoice, validation, correction and approval endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select

from app.api.deps import Principal, SessionDep, require
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.modules.auditing.service import record_audit
from app.modules.documents.service import get_document
from app.modules.extraction.api_schemas import (
    ExtractionRunDetail,
    ExtractionRunOut,
    InvoiceDetail,
    InvoiceOut,
    LineItemOut,
    ValidationIssueOut,
)
from app.modules.extraction.models import ExtractionRun, InvoiceLineItem, InvoiceRecord
from app.modules.jobs.schemas import JobAccepted
from app.modules.jobs.service import build_run
from app.modules.reviews import service as reviews
from app.modules.reviews.models import ReviewAction
from app.modules.reviews.schemas import (
    ApprovalRequest,
    CorrectionRequest,
    CorrectionResponse,
    RejectionRequest,
    ReviewActionOut,
)
from app.modules.validation.models import ValidationIssue
from app.shared.enums import JobType, ResolutionStatus, Severity
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(tags=["invoices"])
Reader = Annotated[Principal, Depends(require(Permission.EXTRACTION_READ))]
Corrector = Annotated[Principal, Depends(require(Permission.INVOICE_CORRECT))]
Approver = Annotated[Principal, Depends(require(Permission.INVOICE_APPROVE))]
Processor = Annotated[Principal, Depends(require(Permission.DOCUMENT_PROCESS))]


async def invoice_detail(session: SessionDep, invoice: InvoiceRecord) -> InvoiceDetail:
    lines = (
        (
            await session.execute(
                select(InvoiceLineItem).where(InvoiceLineItem.invoice_record_id == invoice.id).order_by(InvoiceLineItem.position)
            )
        )
        .scalars()
        .all()
    )
    base = InvoiceOut.model_validate(invoice).model_dump()
    return InvoiceDetail(
        **base,
        source_evidence_json=invoice.source_evidence_json or {},
        alternatives_json=invoice.alternatives_json or {},
        line_items=[LineItemOut.model_validate(li) for li in lines],
        machine_values=await reviews.machine_values(session, invoice),
    )


@router.get("/documents/{document_id}/extractions", response_model=list[ExtractionRunOut])
async def list_extractions(document_id: uuid.UUID, principal: Reader, session: SessionDep) -> list[ExtractionRun]:
    doc = await get_document(session, principal, document_id)
    rows = await session.execute(
        select(ExtractionRun)
        .where(ExtractionRun.document_id == doc.id, ExtractionRun.organization_id == principal.organization_id)
        .order_by(ExtractionRun.extraction_revision.desc())
    )
    return list(rows.scalars())


@router.get("/extractions/{extraction_id}", response_model=ExtractionRunDetail)
async def get_extraction(extraction_id: uuid.UUID, principal: Reader, session: SessionDep) -> ExtractionRun:
    run = (
        await session.execute(
            select(ExtractionRun).where(ExtractionRun.id == extraction_id, ExtractionRun.organization_id == principal.organization_id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("Extraction not found")
    return run


@router.get("/documents/{document_id}/invoices", response_model=list[InvoiceOut])
async def document_invoices(
    document_id: uuid.UUID, principal: Reader, session: SessionDep, include_superseded: bool = False
) -> list[InvoiceRecord]:
    doc = await get_document(session, principal, document_id)
    stmt = select(InvoiceRecord).where(InvoiceRecord.document_id == doc.id, InvoiceRecord.organization_id == principal.organization_id)
    if not include_superseded:
        stmt = stmt.where(InvoiceRecord.superseded_at.is_(None))
    return list((await session.execute(stmt.order_by(InvoiceRecord.created_at.desc(), InvoiceRecord.segment_index))).scalars())


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
async def get_invoice(invoice_id: uuid.UUID, principal: Reader, session: SessionDep) -> InvoiceDetail:
    invoice = await reviews.load_invoice(session, principal, invoice_id)
    return await invoice_detail(session, invoice)


@router.get("/invoices/{invoice_id}/line-items", response_model=list[LineItemOut])
async def get_line_items(invoice_id: uuid.UUID, principal: Reader, session: SessionDep) -> list[InvoiceLineItem]:
    invoice = await reviews.load_invoice(session, principal, invoice_id)
    rows = await session.execute(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_record_id == invoice.id).order_by(InvoiceLineItem.position)
    )
    return list(rows.scalars())


@router.get("/invoices/{invoice_id}/history", response_model=list[ReviewActionOut])
async def invoice_history(invoice_id: uuid.UUID, principal: Reader, session: SessionDep) -> list[ReviewAction]:
    invoice = await reviews.load_invoice(session, principal, invoice_id)
    rows = await session.execute(
        select(ReviewAction)
        .where(ReviewAction.invoice_record_id == invoice.id, ReviewAction.organization_id == principal.organization_id)
        .order_by(ReviewAction.created_at, ReviewAction.id)
    )
    return list(rows.scalars())


async def _issues_page(session: SessionDep, stmt, page: PageParams) -> Page[ValidationIssueOut]:  # type: ignore[no-untyped-def]
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        (await session.execute(stmt.order_by(ValidationIssue.created_at.desc(), ValidationIssue.id).limit(page.limit).offset(page.offset)))
        .scalars()
        .all()
    )
    return Page(items=[ValidationIssueOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


@router.get("/documents/{document_id}/validations", response_model=Page[ValidationIssueOut])
async def document_validations(
    document_id: uuid.UUID,
    principal: Reader,
    session: SessionDep,
    page: Annotated[PageParams, Depends(page_params)],
    resolution_status: ResolutionStatus | None = ResolutionStatus.OPEN,
    severity: Severity | None = None,
) -> Page[ValidationIssueOut]:
    doc = await get_document(session, principal, document_id)
    stmt = select(ValidationIssue).where(
        ValidationIssue.document_id == doc.id, ValidationIssue.organization_id == principal.organization_id
    )
    if resolution_status:
        stmt = stmt.where(ValidationIssue.resolution_status == resolution_status)
    if severity:
        stmt = stmt.where(ValidationIssue.severity == severity)
    return await _issues_page(session, stmt, page)


@router.get("/invoices/{invoice_id}/validations", response_model=Page[ValidationIssueOut])
async def invoice_validations(
    invoice_id: uuid.UUID,
    principal: Reader,
    session: SessionDep,
    page: Annotated[PageParams, Depends(page_params)],
    resolution_status: ResolutionStatus | None = ResolutionStatus.OPEN,
) -> Page[ValidationIssueOut]:
    invoice = await reviews.load_invoice(session, principal, invoice_id)
    stmt = select(ValidationIssue).where(
        ValidationIssue.invoice_record_id == invoice.id, ValidationIssue.organization_id == principal.organization_id
    )
    if resolution_status:
        stmt = stmt.where(ValidationIssue.resolution_status == resolution_status)
    return await _issues_page(session, stmt, page)


@router.post("/invoices/{invoice_id}/revalidate", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def revalidate(invoice_id: uuid.UUID, principal: Processor, session: SessionDep) -> JobAccepted:
    invoice = await reviews.load_invoice(session, principal, invoice_id)
    run, extras = build_run(
        principal, JobType.REVALIDATION, document_id=invoice.document_id, payload={"invoice_id": str(invoice.id), "reason": "manual"}
    )
    session.add(run)
    await session.flush()
    session.add_all(extras)
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="invoice.revalidation_requested",
        resource_type="invoice",
        resource_id=invoice.id,
    )
    await session.commit()
    return JobAccepted(job_id=run.id, status_url=f"/api/v1/jobs/{run.id}", state=run.state)


@router.patch("/invoices/{invoice_id}/corrections", response_model=CorrectionResponse)
async def correct_invoice(invoice_id: uuid.UUID, body: CorrectionRequest, principal: Corrector, session: SessionDep) -> CorrectionResponse:
    invoice, run, stale = await reviews.apply_corrections(session, principal, invoice_id, body.expected_version, body.reason, body.changes)
    invoice = await reviews.load_invoice(session, principal, invoice.id)
    return CorrectionResponse(
        invoice=await invoice_detail(session, invoice),
        revalidation_job_id=run.id,
        status_url=f"/api/v1/jobs/{run.id}",
        stale_comparisons=stale,
    )


@router.post("/invoices/{invoice_id}/approve", response_model=InvoiceOut)
async def approve_invoice(invoice_id: uuid.UUID, body: ApprovalRequest, principal: Approver, session: SessionDep) -> InvoiceRecord:
    return await reviews.approve(session, principal, invoice_id, body.expected_version, body.reason, body.acknowledge_issues)


@router.post("/invoices/{invoice_id}/reject", response_model=InvoiceOut)
async def reject_invoice(invoice_id: uuid.UUID, body: RejectionRequest, principal: Approver, session: SessionDep) -> InvoiceRecord:
    return await reviews.reject(session, principal, invoice_id, body.expected_version, body.reason)
