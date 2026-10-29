"""Human review: corrections, approval, rejection, assignment (async, API).

* Corrections never modify ``extraction_runs`` (immutable machine output);
  they update the current invoice record and append ``review_actions``.
* Optimistic locking: the client sends ``expected_version``; the row is also
  protected by SQLAlchemy's version counter (``WHERE version = :old``).
* Every correction triggers revalidation (and re-indexing) as a job, and marks
  comparisons involving the document as STALE.
* A correction records what a reviewer decided, not that the document changed.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.api.deps import Principal
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.auditing.service import record_audit
from app.modules.documents.models import Document
from app.modules.documents.service import mark_comparisons_stale
from app.modules.extraction.models import ExtractionRun, InvoiceLineItem, InvoiceRecord
from app.modules.jobs.models import ProcessingRun
from app.modules.jobs.service import build_run
from app.modules.reviews.models import ReviewAction, ReviewTask
from app.modules.reviews.schemas import FieldChange
from app.modules.validation.models import ValidationIssue
from app.shared.enums import (
    TERMINAL_RUN_STATES,
    DocumentStatus,
    DocumentType,
    JobType,
    ResolutionStatus,
    ReviewActionType,
    ReviewStatus,
    ReviewTaskStatus,
    Severity,
)
from app.shared.money import ISO_CURRENCIES
from app.shared.text import normalize_invoice_number, normalize_supplier

TEXT_FIELDS = {
    "invoice_number": 120,
    "supplier_name": 300,
    "supplier_tax_id": 80,
    "supplier_address": 1000,
    "customer_name": 300,
    "customer_address": 1000,
    "purchase_order_number": 120,
    "payment_reference": 120,
}
AMOUNT_FIELDS = {"subtotal", "discount_amount", "shipping_amount", "tax_amount", "total_amount"}
DATE_FIELDS = {"invoice_date", "payment_due_date"}
LINE_FIELDS = {"description", "quantity", "unit_price", "discount_amount", "tax_rate", "tax_amount", "line_total"}
_LINE_PATH = re.compile(r"^line_items\[(\d+)\](?:\.(\w+))?$")
_DECIMAL_RE = re.compile(r"^-?\d{1,16}(\.\d{1,6})?$")


def _decimal(value: Any, path: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _DECIMAL_RE.match(value.strip()):
        raise ValidationFailedError(f"{path}: amounts must be decimal strings like '1234.50'", code="INVALID_CORRECTION_VALUE")
    try:
        return Decimal(value.strip())
    except InvalidOperation as exc:
        raise ValidationFailedError(f"{path}: invalid decimal", code="INVALID_CORRECTION_VALUE") from exc


def _date(value: Any, path: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationFailedError(f"{path}: dates must be YYYY-MM-DD", code="INVALID_CORRECTION_VALUE") from exc


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, DocumentType):
        return value.value
    return value


async def load_invoice(session: AsyncSession, principal: Principal, invoice_id: uuid.UUID, *, for_update: bool = False) -> InvoiceRecord:
    stmt = (
        select(InvoiceRecord)
        .join(Document, Document.id == InvoiceRecord.document_id)
        .where(
            InvoiceRecord.id == invoice_id,
            InvoiceRecord.organization_id == principal.organization_id,
            Document.deleted_at.is_(None),
        )
    )
    if for_update:
        stmt = stmt.with_for_update(of=InvoiceRecord)
    invoice = (await session.execute(stmt)).scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice not found")
    return invoice


async def machine_values(session: AsyncSession, invoice: InvoiceRecord) -> dict[str, Any] | None:
    run = await session.get(ExtractionRun, invoice.extraction_run_id)
    if run is None:
        return None
    for item in (run.normalized_result_json or {}).get("invoices", []):
        if item.get("segment_index") == invoice.segment_index:
            return {k: v for k, v in item.items() if k not in ("evidence", "notes")}
    return None


def _check_version(invoice: InvoiceRecord, expected: int) -> None:
    if invoice.version != expected:
        raise ConflictError(
            "Invoice was modified by someone else; reload and retry",
            code="VERSION_CONFLICT",
            details={"current_version": invoice.version, "expected_version": expected},
        )


async def _active_revalidation(session: AsyncSession, invoice: InvoiceRecord) -> bool:
    row = (
        await session.execute(
            select(ProcessingRun.id)
            .where(
                ProcessingRun.organization_id == invoice.organization_id,
                ProcessingRun.job_type == JobType.REVALIDATION,
                ProcessingRun.state.not_in(list(TERMINAL_RUN_STATES)),
                ProcessingRun.payload_json["invoice_id"].astext == str(invoice.id),
            )
            .limit(1)
        )
    ).first()
    return row is not None


async def _open_task(session: AsyncSession, invoice: InvoiceRecord) -> ReviewTask | None:
    return (
        await session.execute(
            select(ReviewTask)
            .where(ReviewTask.invoice_record_id == invoice.id, ReviewTask.status.in_([ReviewTaskStatus.OPEN, ReviewTaskStatus.IN_PROGRESS]))
            .with_for_update()
        )
    ).scalar_one_or_none()


async def apply_corrections(
    session: AsyncSession, principal: Principal, invoice_id: uuid.UUID, expected_version: int, reason: str, changes: list[FieldChange]
) -> tuple[InvoiceRecord, ProcessingRun, int]:
    invoice = await load_invoice(session, principal, invoice_id, for_update=True)
    _check_version(invoice, expected_version)
    if invoice.superseded_at is not None:
        raise ConflictError("Invoice record was superseded by a newer extraction", code="INVOICE_SUPERSEDED")
    lines = {
        li.position: li
        for li in (
            await session.execute(select(InvoiceLineItem).where(InvoiceLineItem.invoice_record_id == invoice.id).with_for_update())
        ).scalars()
    }
    task = await _open_task(session, invoice)
    corrected = set(invoice.corrected_fields_json or [])
    support = dict(invoice.field_support_json or {})
    evidence = dict(invoice.source_evidence_json or {})
    actions: list[ReviewAction] = []

    def record(path: str, old: Any, new: Any) -> None:
        actions.append(
            ReviewAction(
                id=uuid.uuid4(),
                organization_id=invoice.organization_id,
                document_id=invoice.document_id,
                invoice_record_id=invoice.id,
                review_task_id=task.id if task else None,
                reviewer_id=principal.user_id,
                action_type=ReviewActionType.CORRECTION,
                field_path=path,
                old_value_json=_json(old),
                new_value_json=_json(new),
                reason=reason,
                invoice_version=expected_version,
            )
        )
        corrected.add(path)

    for change in changes:
        path, value = change.field_path.strip(), change.value
        if path in TEXT_FIELDS:
            if value is not None and not isinstance(value, str):
                raise ValidationFailedError(f"{path}: expected a string", code="INVALID_CORRECTION_VALUE")
            new = value.strip()[: TEXT_FIELDS[path]] if isinstance(value, str) else None
            record(path, getattr(invoice, path), new)
            setattr(invoice, path, new)
            if path == "invoice_number":
                invoice.normalized_invoice_number = normalize_invoice_number(new)
            if path == "supplier_name":
                invoice.normalized_supplier = normalize_supplier(new)
        elif path in AMOUNT_FIELDS:
            new_amount = _decimal(value, path)
            record(path, getattr(invoice, path), new_amount)
            setattr(invoice, path, new_amount)
        elif path in DATE_FIELDS:
            new_date = _date(value, path)
            record(path, getattr(invoice, path), new_date)
            setattr(invoice, path, new_date)
        elif path == "currency":
            if value is not None and (not isinstance(value, str) or value.upper() not in ISO_CURRENCIES):
                raise ValidationFailedError("currency: must be a supported ISO 4217 code", code="INVALID_CORRECTION_VALUE")
            new_cur = value.upper() if isinstance(value, str) else None
            record(path, invoice.currency, new_cur)
            invoice.currency = new_cur
        elif path == "amounts_tax_inclusive":
            if value is not None and not isinstance(value, bool):
                raise ValidationFailedError(f"{path}: expected boolean", code="INVALID_CORRECTION_VALUE")
            record(path, invoice.amounts_tax_inclusive, value)
            invoice.amounts_tax_inclusive = value if isinstance(value, bool) or value is None else None
        elif path == "document_type":
            try:
                new_type = DocumentType(str(value))
            except ValueError as exc:
                raise ValidationFailedError("document_type: invalid value", code="INVALID_CORRECTION_VALUE") from exc
            record(path, invoice.document_type, new_type)
            invoice.document_type = new_type
        elif path == "line_items[]":
            if not isinstance(value, dict):
                raise ValidationFailedError("line_items[]: expected an object", code="INVALID_CORRECTION_VALUE")
            position = max(lines, default=0) + 1
            li = InvoiceLineItem(
                id=uuid.uuid4(),
                invoice_record_id=invoice.id,
                position=position,
                source_evidence_json={"extraction_method": "human_correction"},
            )
            for key, raw in value.items():
                if key not in LINE_FIELDS:
                    raise ValidationFailedError(f"line_items[]: unknown field {key}", code="INVALID_CORRECTION_VALUE")
                setattr(li, key, raw if key == "description" else _decimal(raw, f"line_items[].{key}"))
            session.add(li)
            lines[position] = li
            record(f"line_items[{position - 1}]", None, {k: _json(v) for k, v in value.items()})
        else:
            m = _LINE_PATH.match(path)
            if not m:
                raise ValidationFailedError(f"Field '{path}' cannot be corrected", code="FIELD_NOT_CORRECTABLE")
            position = int(m.group(1)) + 1
            li_opt = lines.get(position)
            if li_opt is None:
                raise ValidationFailedError(f"{path}: line item does not exist", code="INVALID_CORRECTION_VALUE")
            attr = m.group(2)
            if attr is None:
                if value is not None:
                    raise ValidationFailedError(f"{path}: use null to remove a line item", code="INVALID_CORRECTION_VALUE")
                record(path, {"description": li_opt.description, "line_total": _json(li_opt.line_total)}, None)
                await session.delete(li_opt)
                del lines[position]
                continue
            if attr not in LINE_FIELDS:
                raise ValidationFailedError(f"{path}: unknown line field", code="FIELD_NOT_CORRECTABLE")
            new_val: Any = (value.strip() if isinstance(value, str) else None) if attr == "description" else _decimal(value, path)
            record(path, getattr(li_opt, attr), new_val)
            setattr(li_opt, attr, new_val)
        top = path.split("[")[0] if path.startswith("line_items") else path
        support[top] = "HUMAN"
        if not path.startswith("line_items"):
            evidence[path] = {
                **(evidence.get(path) or {}),
                "extraction_method": "human_correction",
                "support": "HUMAN",
                "corrected_by": str(principal.user_id),
                "corrected_at": datetime.now(UTC).isoformat(),
            }

    invoice.corrected_fields_json = sorted(corrected)
    invoice.field_support_json = support
    invoice.source_evidence_json = evidence
    invoice.review_status = ReviewStatus.IN_REVIEW
    invoice.approved_by = None
    invoice.approved_at = None
    if task is None:
        task = ReviewTask(
            id=uuid.uuid4(),
            organization_id=invoice.organization_id,
            document_id=invoice.document_id,
            invoice_record_id=invoice.id,
            status=ReviewTaskStatus.IN_PROGRESS,
            reason_codes_json=["HUMAN_CORRECTION"],
            assigned_to=principal.user_id,
            assigned_at=datetime.now(UTC),
        )
        session.add(task)
        await session.flush()
        for action in actions:
            action.review_task_id = task.id
    elif task.status == ReviewTaskStatus.OPEN:
        task.status = ReviewTaskStatus.IN_PROGRESS
        task.assigned_to = task.assigned_to or principal.user_id
        task.assigned_at = task.assigned_at or datetime.now(UTC)
    session.add_all(actions)

    run, extras = build_run(
        principal, JobType.REVALIDATION, document_id=invoice.document_id, payload={"invoice_id": str(invoice.id), "reason": "correction"}
    )
    session.add(run)
    await session.flush()
    session.add_all(extras)
    stale = await mark_comparisons_stale(session, principal.organization_id, invoice.document_id, "invoice corrected")
    doc = await session.get(Document, invoice.document_id)
    if doc is not None:
        doc.status = DocumentStatus.PROCESSING
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="invoice.corrected",
        resource_type="invoice",
        resource_id=invoice.id,
        metadata={"fields": [c.field_path for c in changes], "from_version": expected_version, "revalidation_job_id": str(run.id)},
    )
    try:
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise ConflictError("Invoice was modified concurrently; reload and retry", code="VERSION_CONFLICT") from exc
    return invoice, run, stale


async def _blocking_issues(session: AsyncSession, invoice: InvoiceRecord) -> list[ValidationIssue]:
    return list(
        (
            await session.execute(
                select(ValidationIssue).where(
                    ValidationIssue.invoice_record_id == invoice.id,
                    ValidationIssue.resolution_status == ResolutionStatus.OPEN,
                    ValidationIssue.severity.in_([Severity.ERROR, Severity.CRITICAL]),
                )
            )
        ).scalars()
    )


async def _refresh_document_status(session: AsyncSession, document_id: uuid.UUID) -> None:
    open_tasks = (
        await session.execute(
            select(func.count()).where(
                ReviewTask.document_id == document_id, ReviewTask.status.in_([ReviewTaskStatus.OPEN, ReviewTaskStatus.IN_PROGRESS])
            )
        )
    ).scalar_one()
    doc = await session.get(Document, document_id)
    if doc is not None and not open_tasks and doc.status == DocumentStatus.REQUIRES_REVIEW:
        doc.status = DocumentStatus.COMPLETED
        doc.review_required = False


async def approve(
    session: AsyncSession, principal: Principal, invoice_id: uuid.UUID, expected_version: int, reason: str | None, acknowledge: bool
) -> InvoiceRecord:
    invoice = await load_invoice(session, principal, invoice_id, for_update=True)
    _check_version(invoice, expected_version)
    if invoice.superseded_at is not None:
        raise ConflictError("Invoice record was superseded", code="INVOICE_SUPERSEDED")
    if invoice.review_status == ReviewStatus.APPROVED:
        raise ConflictError("Invoice is already approved", code="ALREADY_APPROVED")
    if await _active_revalidation(session, invoice):
        raise ConflictError("Revalidation is still running; wait for it to finish", code="REVALIDATION_PENDING")
    blocking = await _blocking_issues(session, invoice)
    if blocking and not (acknowledge and reason):
        raise ConflictError(
            "Invoice has open ERROR/CRITICAL issues; correct them or approve with acknowledge_issues=true and a reason",
            code="BLOCKING_ISSUES",
            details={"issues": [{"id": str(i.id), "rule_code": i.rule_code, "severity": i.severity.value} for i in blocking]},
        )
    now = datetime.now(UTC)
    for issue in blocking:
        issue.resolution_status = ResolutionStatus.ACCEPTED
        issue.resolved_at = now
        issue.resolved_by = principal.user_id
    invoice.review_status = ReviewStatus.APPROVED
    invoice.approved_by = principal.user_id
    invoice.approved_at = now
    task = await _open_task(session, invoice)
    if task is not None:
        task.status = ReviewTaskStatus.APPROVED
        task.resolved_by = principal.user_id
        task.resolved_at = now
    session.add(
        ReviewAction(
            id=uuid.uuid4(),
            organization_id=invoice.organization_id,
            document_id=invoice.document_id,
            invoice_record_id=invoice.id,
            review_task_id=task.id if task else None,
            reviewer_id=principal.user_id,
            action_type=ReviewActionType.APPROVAL,
            reason=reason,
            invoice_version=expected_version,
            new_value_json={"acknowledged_issue_ids": [str(i.id) for i in blocking]} if blocking else None,
        )
    )
    await session.flush()
    await _refresh_document_status(session, invoice.document_id)
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="invoice.approved",
        resource_type="invoice",
        resource_id=invoice.id,
        metadata={"acknowledged_issues": len(blocking)},
    )
    try:
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise ConflictError("Invoice was modified concurrently", code="VERSION_CONFLICT") from exc
    return invoice


async def reject(session: AsyncSession, principal: Principal, invoice_id: uuid.UUID, expected_version: int, reason: str) -> InvoiceRecord:
    invoice = await load_invoice(session, principal, invoice_id, for_update=True)
    _check_version(invoice, expected_version)
    if invoice.review_status == ReviewStatus.REJECTED:
        raise ConflictError("Invoice is already rejected", code="ALREADY_REJECTED")
    now = datetime.now(UTC)
    invoice.review_status = ReviewStatus.REJECTED
    invoice.approved_by = None
    invoice.approved_at = None
    task = await _open_task(session, invoice)
    if task is not None:
        task.status = ReviewTaskStatus.REJECTED
        task.resolved_by = principal.user_id
        task.resolved_at = now
    session.add(
        ReviewAction(
            id=uuid.uuid4(),
            organization_id=invoice.organization_id,
            document_id=invoice.document_id,
            invoice_record_id=invoice.id,
            review_task_id=task.id if task else None,
            reviewer_id=principal.user_id,
            action_type=ReviewActionType.REJECTION,
            reason=reason,
            invoice_version=expected_version,
        )
    )
    await session.flush()
    await _refresh_document_status(session, invoice.document_id)
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="invoice.rejected",
        resource_type="invoice",
        resource_id=invoice.id,
    )
    try:
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise ConflictError("Invoice was modified concurrently", code="VERSION_CONFLICT") from exc
    return invoice


async def claim(session: AsyncSession, principal: Principal, review_id: uuid.UUID, force: bool) -> ReviewTask:
    from app.shared.enums import Role

    task = (
        await session.execute(
            select(ReviewTask).where(ReviewTask.id == review_id, ReviewTask.organization_id == principal.organization_id).with_for_update()
        )
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError("Review not found")
    if task.status not in (ReviewTaskStatus.OPEN, ReviewTaskStatus.IN_PROGRESS):
        raise ConflictError("Review is already resolved", code="REVIEW_RESOLVED")
    if task.assigned_to and task.assigned_to != principal.user_id and not (force and principal.role == Role.ADMIN):
        raise ConflictError("Review is assigned to another reviewer", code="REVIEW_ASSIGNED")
    previous = task.assigned_to
    task.assigned_to = principal.user_id
    task.assigned_at = datetime.now(UTC)
    task.status = ReviewTaskStatus.IN_PROGRESS
    session.add(
        ReviewAction(
            id=uuid.uuid4(),
            organization_id=task.organization_id,
            document_id=task.document_id,
            invoice_record_id=task.invoice_record_id,
            review_task_id=task.id,
            reviewer_id=principal.user_id,
            action_type=ReviewActionType.ASSIGNMENT,
            old_value_json=str(previous) if previous else None,
            new_value_json=str(principal.user_id),
        )
    )
    await session.commit()
    return task
