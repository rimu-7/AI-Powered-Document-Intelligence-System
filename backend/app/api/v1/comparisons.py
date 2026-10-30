"""PDF↔PDF comparisons and PDF↔spreadsheet reconciliations (async jobs)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select

from app.api import idempotency
from app.api.deps import Principal, SessionDep, require
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.permissions import Permission
from app.modules.auditing.service import record_audit
from app.modules.comparison.mapping import suggest_mapping, validate_mapping
from app.modules.comparison.models import ComparisonDocument, ComparisonFinding, DocumentComparison
from app.modules.comparison.schemas import (
    ComparedDocument,
    ComparisonAccepted,
    ComparisonCreate,
    ComparisonOut,
    FindingOut,
    ReconciliationCreate,
)
from app.modules.comparison.service import findings_to_csv
from app.modules.documents.models import Document, DocumentTable
from app.modules.documents.service import get_document
from app.modules.extraction.models import InvoiceRecord
from app.modules.jobs.models import ProcessingRun
from app.modules.jobs.service import build_run
from app.shared.enums import ComparisonStatus, ComparisonType, DocumentStatus, FindingStatus, JobType
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(tags=["comparisons"])
Comparer = Annotated[Principal, Depends(require(Permission.COMPARE))]
Reader = Annotated[Principal, Depends(require(Permission.EXTRACTION_READ))]

_READY = {DocumentStatus.COMPLETED, DocumentStatus.COMPLETED_WITH_WARNINGS, DocumentStatus.REQUIRES_REVIEW}


async def _ready_document(session: SessionDep, principal: Principal, document_id: uuid.UUID) -> Document:
    doc = await get_document(session, principal, document_id)
    if doc.status not in _READY:
        raise ConflictError(f"Document {document_id} is not processed yet (status {doc.status.value})", code="DOCUMENT_NOT_READY")
    return doc


async def _check_invoice_ids(session: SessionDep, principal: Principal, document_id: uuid.UUID, ids: list[uuid.UUID] | None) -> None:
    if not ids:
        return
    found = (
        await session.execute(
            select(func.count()).where(
                InvoiceRecord.id.in_(ids),
                InvoiceRecord.document_id == document_id,
                InvoiceRecord.organization_id == principal.organization_id,
                InvoiceRecord.superseded_at.is_(None),
            )
        )
    ).scalar_one()
    if found != len(set(ids)):
        raise ValidationFailedError("Some invoice ids do not belong to the document", code="INVALID_INVOICE_IDS")


async def _create(
    session: SessionDep, principal: Principal, comparison: DocumentComparison, job_type: JobType, docs: list[tuple[uuid.UUID, str]]
) -> ComparisonAccepted:
    run, extras = build_run(principal, job_type, document_id=None, payload={"comparison_id": str(comparison.id)})
    session.add(run)
    await session.flush()
    comparison.processing_run_id = run.id
    session.add(comparison)
    await session.flush()
    for doc_id, side in docs:
        session.add(ComparisonDocument(comparison_id=comparison.id, document_id=doc_id, side=side))
    session.add_all(extras)
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action=f"{job_type.value.lower()}.requested",
        resource_type="comparison",
        resource_id=comparison.id,
    )
    await session.commit()
    return ComparisonAccepted(
        comparison_id=comparison.id,
        job_id=run.id,
        status_url=f"/api/v1/jobs/{run.id}",
        column_mapping=comparison.parameters_json.get("column_mapping"),
    )


async def _idempotent(session: SessionDep, principal: Principal, endpoint: str, key: str | None, payload: dict, create) -> JSONResponse:  # type: ignore[no-untyped-def,type-arg]
    key = idempotency.validate_key(key)
    record = None
    if key:
        record, replay = await idempotency.begin(session, principal, endpoint, key, idempotency.fingerprint(payload))
        if replay is not None:
            return JSONResponse(
                status_code=replay.response_status or 202, content=replay.response_body_json, headers={"Idempotent-Replay": "true"}
            )
    try:
        accepted = await create()
    except Exception:
        if record is not None:
            await idempotency.abandon(session, record)
        raise
    body = accepted.model_dump(mode="json")
    if record is not None:
        await idempotency.complete(session, record, 202, body)
    return JSONResponse(status_code=202, content=body)


@router.post("/comparisons", response_model=ComparisonAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_comparison(
    body: ComparisonCreate,
    principal: Comparer,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def create() -> ComparisonAccepted:
        left = await _ready_document(session, principal, body.left_document_id)
        right = await _ready_document(session, principal, body.right_document_id)
        await _check_invoice_ids(session, principal, left.id, body.left_invoice_ids)
        await _check_invoice_ids(session, principal, right.id, body.right_invoice_ids)
        comparison = DocumentComparison(
            id=uuid.uuid4(),
            organization_id=principal.organization_id,
            left_document_id=left.id,
            right_document_id=right.id,
            comparison_type=ComparisonType.PDF_PDF,
            matching_strategy="invoice_number+supplier/v1",
            status=ComparisonStatus.QUEUED,
            parameters_json={
                **body.options.model_dump(mode="json"),
                "left_invoice_ids": [str(i) for i in body.left_invoice_ids] if body.left_invoice_ids else None,
                "right_invoice_ids": [str(i) for i in body.right_invoice_ids] if body.right_invoice_ids else None,
            },
            created_by=principal.user_id,
        )
        return await _create(session, principal, comparison, JobType.COMPARISON, [(left.id, "left"), (right.id, "right")])

    return await _idempotent(session, principal, "comparisons.create", idempotency_key, body.model_dump(mode="json"), create)


@router.post("/reconciliations", response_model=ComparisonAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_reconciliation(
    body: ReconciliationCreate,
    principal: Comparer,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    async def create() -> ComparisonAccepted:
        sheet = await _ready_document(session, principal, body.spreadsheet_document_id)
        if not sheet.file_kind.is_spreadsheet:
            raise ValidationFailedError("spreadsheet_document_id must be an XLSX, XLS or CSV document", code="NOT_A_SPREADSHEET")
        pdfs = [await _ready_document(session, principal, d) for d in dict.fromkeys(body.pdf_document_ids)]
        if any(d.file_kind.is_spreadsheet for d in pdfs):
            raise ValidationFailedError("pdf_document_ids must not contain spreadsheets", code="INVALID_DOCUMENT_KIND")
        tables = (
            (await session.execute(select(DocumentTable).where(DocumentTable.document_id == sheet.id, DocumentTable.page_id.is_(None))))
            .scalars()
            .all()
        )
        if body.sheet_names:
            tables = [t for t in tables if t.sheet_name in body.sheet_names]
            if not tables:
                raise ValidationFailedError("None of the requested sheets exist", code="UNKNOWN_SHEETS")
        headers = {str(h) for t in tables for h in (t.header_json or [])}
        mapping = body.column_mapping
        if mapping is None:
            suggestion = suggest_mapping(sorted(headers))
            mapping = suggestion.suggested_mapping
        errors = validate_mapping(mapping, headers)
        if errors:
            raise ValidationFailedError(
                "Column mapping is incomplete or invalid; confirm a mapping",
                code="INVALID_COLUMN_MAPPING",
                details={"errors": errors, "suggestions": suggest_mapping(sorted(headers)).model_dump()},
            )
        comparison = DocumentComparison(
            id=uuid.uuid4(),
            organization_id=principal.organization_id,
            left_document_id=None,
            right_document_id=sheet.id,
            comparison_type=ComparisonType.PDF_SPREADSHEET,
            matching_strategy="invoice_number+supplier/v1",
            status=ComparisonStatus.QUEUED,
            parameters_json={
                **body.options.model_dump(mode="json"),
                "pdf_document_ids": [str(d.id) for d in pdfs],
                "column_mapping": mapping,
                "sheet_names": body.sheet_names,
            },
            created_by=principal.user_id,
        )
        return await _create(session, principal, comparison, JobType.RECONCILIATION, [(sheet.id, "right"), *[(d.id, "left") for d in pdfs]])

    return await _idempotent(session, principal, "reconciliations.create", idempotency_key, body.model_dump(mode="json"), create)


async def _outs(session: SessionDep, comparisons: list[DocumentComparison]) -> list[ComparisonOut]:
    """ComparisonOut with the participating documents' names and the failure reason."""
    if not comparisons:
        return []
    ids = [c.id for c in comparisons]
    doc_rows = (
        await session.execute(
            select(ComparisonDocument.comparison_id, ComparisonDocument.side, Document)
            .join(Document, Document.id == ComparisonDocument.document_id)
            .where(ComparisonDocument.comparison_id.in_(ids))
            .order_by(ComparisonDocument.side, Document.original_filename)
        )
    ).all()
    docs: dict[uuid.UUID, list[ComparedDocument]] = {}
    for comparison_id, side, doc in doc_rows:
        docs.setdefault(comparison_id, []).append(
            ComparedDocument(
                id=doc.id, side=side, filename=doc.original_filename, file_kind=doc.file_kind.value, deleted=doc.deleted_at is not None
            )
        )
    run_ids = [c.processing_run_id for c in comparisons if c.processing_run_id and c.status == ComparisonStatus.FAILED]
    errors: dict[uuid.UUID, str | None] = {}
    if run_ids:
        for run_id, message in (
            await session.execute(select(ProcessingRun.id, ProcessingRun.sanitized_error_message).where(ProcessingRun.id.in_(run_ids)))
        ).all():
            errors[run_id] = message
    out = []
    for c in comparisons:
        item = ComparisonOut.model_validate(c)
        item.documents = docs.get(c.id, [])
        if c.status == ComparisonStatus.FAILED:
            item.error_message = errors.get(c.processing_run_id) if c.processing_run_id else None  # type: ignore[arg-type]
            item.error_message = item.error_message or "The comparison job failed or was cancelled."
        out.append(item)
    return out


async def _get_comparison(
    session: SessionDep, principal: Principal, comparison_id: uuid.UUID, kind: ComparisonType | None
) -> DocumentComparison:
    stmt = select(DocumentComparison).where(
        DocumentComparison.id == comparison_id, DocumentComparison.organization_id == principal.organization_id
    )
    if kind:
        stmt = stmt.where(DocumentComparison.comparison_type == kind)
    comparison = (await session.execute(stmt)).scalar_one_or_none()
    if comparison is None:
        raise NotFoundError("Comparison not found")
    return comparison


@router.get("/comparisons", response_model=Page[ComparisonOut])
async def list_comparisons(
    principal: Reader,
    session: SessionDep,
    page: Annotated[PageParams, Depends(page_params)],
    comparison_type: ComparisonType | None = None,
    status_filter: Annotated[ComparisonStatus | None, Query(alias="status")] = None,
) -> Page[ComparisonOut]:
    stmt = select(DocumentComparison).where(DocumentComparison.organization_id == principal.organization_id)
    if comparison_type:
        stmt = stmt.where(DocumentComparison.comparison_type == comparison_type)
    if status_filter:
        stmt = stmt.where(DocumentComparison.status == status_filter)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                stmt.order_by(DocumentComparison.created_at.desc(), DocumentComparison.id).limit(page.limit).offset(page.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page(items=await _outs(session, list(rows)), total=total, limit=page.limit, offset=page.offset)


async def _findings(
    session: SessionDep,
    comparison: DocumentComparison,
    page: PageParams,
    finding_status: FindingStatus | None,
    records_only: bool,
    record_position: int | None = None,
) -> Page[FindingOut]:
    stmt = select(ComparisonFinding).where(ComparisonFinding.comparison_id == comparison.id)
    if record_position is not None:
        # The field findings of one record: everything after its __record__ row
        # up to the next record.
        next_record = (
            await session.execute(
                select(func.min(ComparisonFinding.position)).where(
                    ComparisonFinding.comparison_id == comparison.id,
                    ComparisonFinding.field_name == "__record__",
                    ComparisonFinding.position > record_position,
                )
            )
        ).scalar_one()
        stmt = stmt.where(ComparisonFinding.position > record_position, ComparisonFinding.field_name != "__record__")
        if next_record is not None:
            stmt = stmt.where(ComparisonFinding.position < next_record)
    if finding_status:
        stmt = stmt.where(ComparisonFinding.status == finding_status)
    if records_only:
        stmt = stmt.where(ComparisonFinding.field_name == "__record__")
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(ComparisonFinding.position).limit(page.limit).offset(page.offset))).scalars().all()
    return Page(items=[FindingOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


@router.get("/comparisons/{comparison_id}", response_model=ComparisonOut)
async def get_comparison(comparison_id: uuid.UUID, principal: Reader, session: SessionDep) -> ComparisonOut:
    comparison = await _get_comparison(session, principal, comparison_id, None)
    return (await _outs(session, [comparison]))[0]


@router.get("/comparisons/{comparison_id}/findings", response_model=Page[FindingOut])
async def comparison_findings(
    comparison_id: uuid.UUID,
    principal: Reader,
    session: SessionDep,
    page: Annotated[PageParams, Depends(page_params)],
    finding_status: FindingStatus | None = None,
    records_only: bool = False,
    record_position: Annotated[int | None, Query(ge=0, description="Only the field findings of the record at this position")] = None,
) -> Page[FindingOut]:
    comparison = await _get_comparison(session, principal, comparison_id, None)
    return await _findings(session, comparison, page, finding_status, records_only, record_position)


@router.post("/comparisons/{comparison_id}/rerun", response_model=ComparisonAccepted, status_code=status.HTTP_202_ACCEPTED)
async def rerun_comparison(comparison_id: uuid.UUID, principal: Comparer, session: SessionDep) -> ComparisonAccepted:
    """Run a comparison or reconciliation again with the same documents and settings, on the current data.

    The earlier run and its findings are kept."""
    old = await _get_comparison(session, principal, comparison_id, None)
    if old.status in (ComparisonStatus.QUEUED, ComparisonStatus.RUNNING):
        raise ConflictError("This comparison is still running", code="COMPARISON_RUNNING")
    params = dict(old.parameters_json or {})
    sides = (
        await session.execute(
            select(ComparisonDocument.document_id, ComparisonDocument.side).where(ComparisonDocument.comparison_id == old.id)
        )
    ).all()
    for doc_id, _side in sides:
        await _ready_document(session, principal, doc_id)
    if old.comparison_type == ComparisonType.PDF_PDF:
        assert old.left_document_id is not None
        for side, doc_id in (("left", old.left_document_id), ("right", old.right_document_id)):
            selected = params.get(f"{side}_invoice_ids")
            if selected:
                try:
                    await _check_invoice_ids(session, principal, doc_id, [uuid.UUID(i) for i in selected])
                except ValidationFailedError as exc:
                    raise ConflictError(
                        "Some selected invoices were replaced by reprocessing; start a new comparison", code="SELECTION_OUTDATED"
                    ) from exc
        job_type = JobType.COMPARISON
    else:
        job_type = JobType.RECONCILIATION
    comparison = DocumentComparison(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        left_document_id=old.left_document_id,
        right_document_id=old.right_document_id,
        comparison_type=old.comparison_type,
        matching_strategy=old.matching_strategy,
        status=ComparisonStatus.QUEUED,
        parameters_json={**params, "rerun_of": str(old.id)},
        created_by=principal.user_id,
    )
    return await _create(session, principal, comparison, job_type, [(d, side) for d, side in sides])


@router.get("/comparisons/{comparison_id}/export.csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
async def export_comparison(comparison_id: uuid.UUID, principal: Reader, session: SessionDep) -> Response:
    """Every finding as CSV (cells starting with = + - @ are neutralized)."""
    comparison = await _get_comparison(session, principal, comparison_id, None)
    return await _export(session, principal, comparison)


@router.get("/reconciliations/{reconciliation_id}", response_model=ComparisonOut)
async def get_reconciliation(reconciliation_id: uuid.UUID, principal: Reader, session: SessionDep) -> ComparisonOut:
    comparison = await _get_comparison(session, principal, reconciliation_id, ComparisonType.PDF_SPREADSHEET)
    return (await _outs(session, [comparison]))[0]


@router.get("/reconciliations/{reconciliation_id}/findings", response_model=Page[FindingOut])
async def reconciliation_findings(
    reconciliation_id: uuid.UUID,
    principal: Reader,
    session: SessionDep,
    page: Annotated[PageParams, Depends(page_params)],
    finding_status: FindingStatus | None = None,
    records_only: bool = False,
) -> Page[FindingOut]:
    comparison = await _get_comparison(session, principal, reconciliation_id, ComparisonType.PDF_SPREADSHEET)
    return await _findings(session, comparison, page, finding_status, records_only)


@router.get("/reconciliations/{reconciliation_id}/export.csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
async def export_reconciliation(reconciliation_id: uuid.UUID, principal: Reader, session: SessionDep) -> Response:
    """Sanitized CSV export (cells starting with = + - @ are neutralized)."""
    comparison = await _get_comparison(session, principal, reconciliation_id, ComparisonType.PDF_SPREADSHEET)
    return await _export(session, principal, comparison)


async def _export(session: SessionDep, principal: Principal, comparison: DocumentComparison) -> Response:
    if comparison.status not in (ComparisonStatus.COMPLETED, ComparisonStatus.STALE):
        raise ConflictError("The comparison has not completed", code="NOT_COMPLETED")
    rows = (
        (
            await session.execute(
                select(ComparisonFinding)
                .where(ComparisonFinding.comparison_id == comparison.id)
                .order_by(ComparisonFinding.position)
                .limit(200_000)
            )
        )
        .scalars()
        .all()
    )
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action=f"{comparison.comparison_type.value.lower()}.exported",
        resource_type="comparison",
        resource_id=comparison.id,
    )
    await session.commit()
    return Response(
        content=findings_to_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_export_name(comparison)}-{comparison.id}.csv"'},
    )


def _export_name(comparison: DocumentComparison) -> str:
    return "comparison" if comparison.comparison_type == ComparisonType.PDF_PDF else "reconciliation"
