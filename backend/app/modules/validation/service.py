"""Validation persistence (sync, used by workers).

Idempotent per validation run: issues written by a run are replaced if the
run's stage executes again; issues from earlier runs are marked SUPERSEDED.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.metrics import VALIDATION_ISSUES
from app.modules.documents.models import Document
from app.modules.extraction.models import InvoiceLineItem, InvoiceRecord
from app.modules.reviews.models import ReviewTask
from app.modules.validation.models import ValidationIssue
from app.modules.validation.rules import (
    DuplicateCandidate,
    InvoiceView,
    IssueDraft,
    LineView,
    ValidationContext,
    outcome_for,
    run_rules,
)
from app.shared.enums import (
    SEVERITY_ORDER,
    DocumentType,
    ResolutionStatus,
    ReviewStatus,
    ReviewTaskStatus,
    Severity,
    ValidationOutcome,
)

_OUTCOME_ORDER = {
    ValidationOutcome.PASSED: 0,
    ValidationOutcome.PASSED_WITH_WARNINGS: 1,
    ValidationOutcome.REQUIRES_REVIEW: 2,
    ValidationOutcome.FAILED: 3,
}


def worst_outcome(outcomes: list[ValidationOutcome]) -> ValidationOutcome | None:
    if not outcomes:
        return None
    return max(outcomes, key=lambda o: _OUTCOME_ORDER[o])


def build_view(record: InvoiceRecord, lines: list[InvoiceLineItem]) -> InvoiceView:
    alt = record.alternatives_json or {}
    return InvoiceView(
        document_type=record.document_type,
        invoice_number=record.invoice_number,
        invoice_date=record.invoice_date,
        invoice_date_raw=record.invoice_date_raw,
        payment_due_date=record.payment_due_date,
        supplier_name=record.supplier_name,
        customer_name=record.customer_name,
        currency=record.currency,
        currency_raw=record.currency_raw,
        subtotal=record.subtotal,
        discount_amount=record.discount_amount,
        shipping_amount=record.shipping_amount,
        tax_amount=record.tax_amount,
        total_amount=record.total_amount,
        amounts_tax_inclusive=record.amounts_tax_inclusive,
        line_items=[
            LineView(
                position=li.position,
                description=li.description,
                quantity=li.quantity,
                unit_price=li.unit_price,
                discount_amount=li.discount_amount,
                tax_rate=li.tax_rate,
                tax_amount=li.tax_amount,
                line_total=li.line_total,
                evidence=li.source_evidence_json or {},
            )
            for li in sorted(lines, key=lambda x: x.position)
        ],
        evidence=record.source_evidence_json or {},
        field_support=record.field_support_json or {},
        notes=list(alt.get("notes", [])),
        alternatives=dict(alt.get("alternatives", {})),
        extraction_confidence=record.extraction_confidence,
        corrected_fields=list(record.corrected_fields_json or []),
    )


def find_duplicate_candidates(session: Session, record: InvoiceRecord, sha256: str) -> list[DuplicateCandidate]:
    if not record.normalized_invoice_number or not record.normalized_supplier:
        return []
    rows = session.execute(
        select(InvoiceRecord, Document.sha256, Document.original_filename)
        .join(Document, Document.id == InvoiceRecord.document_id)
        .where(
            InvoiceRecord.organization_id == record.organization_id,
            InvoiceRecord.normalized_invoice_number == record.normalized_invoice_number,
            InvoiceRecord.normalized_supplier == record.normalized_supplier,
            InvoiceRecord.superseded_at.is_(None),
            InvoiceRecord.document_id != record.document_id,
            InvoiceRecord.review_status != ReviewStatus.REJECTED,
            Document.deleted_at.is_(None),
        )
        .limit(20)
    ).all()
    return [
        DuplicateCandidate(
            invoice_id=str(other.id),
            document_id=str(other.document_id),
            invoice_date=other.invoice_date,
            total_amount=other.total_amount,
            currency=other.currency,
            same_file=other_sha == sha256,
            filename=other_filename,
            review_status=other.review_status.value if other.review_status else None,
        )
        for other, other_sha, other_filename in rows
    ]


def duplicate_file_issue(session: Session, document: Document) -> IssueDraft | None:
    others = (
        session.execute(
            select(Document.id)
            .where(
                Document.organization_id == document.organization_id,
                Document.sha256 == document.sha256,
                Document.id != document.id,
                Document.deleted_at.is_(None),
            )
            .limit(20)
        )
        .scalars()
        .all()
    )
    if not others:
        return None
    return IssueDraft(
        "DUPLICATE_FILE",
        Severity.WARNING,
        f"An identical file (same SHA-256) was uploaded {len(others)} other time(s)",
        details={"sha256": document.sha256, "other_document_ids": [str(o) for o in others]},
    )


def context() -> ValidationContext:
    settings = get_settings()
    return ValidationContext(
        tolerance=settings.validation_amount_tolerance,
        today=datetime.now(UTC).date(),
        future_date_policy=settings.future_date_policy,
        future_grace_days=settings.future_date_grace_days,
        low_confidence_threshold=Decimal(str(settings.low_confidence_threshold)),
    )


def _to_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def write_issues(
    session: Session,
    *,
    document: Document,
    invoice: InvoiceRecord | None,
    run_id: uuid.UUID,
    issues: list[IssueDraft],
) -> None:
    for draft in issues:
        session.add(
            ValidationIssue(
                id=uuid.uuid4(),
                organization_id=document.organization_id,
                document_id=document.id,
                invoice_record_id=invoice.id if invoice else None,
                validation_run_id=run_id,
                rule_code=draft.rule_code,
                severity=draft.severity,
                field_path=draft.field_path,
                expected_value_json=_to_json(draft.expected),
                actual_value_json=_to_json(draft.actual),
                source_evidence_json=draft.evidence or {},
                details_json=draft.details or {},
                message=draft.message[:1000],
                resolution_status=ResolutionStatus.OPEN,
            )
        )
        VALIDATION_ISSUES.labels(draft.rule_code, draft.severity.value).inc()


def reset_run_issues(session: Session, run_id: uuid.UUID, document_id: uuid.UUID, invoice_ids: list[uuid.UUID] | None) -> None:
    """Idempotency: drop issues this run wrote before; supersede older open ones."""
    session.execute(delete(ValidationIssue).where(ValidationIssue.validation_run_id == run_id))
    stmt = update(ValidationIssue).where(
        ValidationIssue.document_id == document_id,
        ValidationIssue.resolution_status == ResolutionStatus.OPEN,
    )
    if invoice_ids is not None:
        stmt = stmt.where(ValidationIssue.invoice_record_id.in_(invoice_ids))
    session.execute(stmt.values(resolution_status=ResolutionStatus.SUPERSEDED, resolved_at=datetime.now(UTC)))


def ensure_review_task(session: Session, invoice: InvoiceRecord, reasons: list[str]) -> None:
    session.execute(
        insert(ReviewTask)
        .values(
            id=uuid.uuid4(),
            organization_id=invoice.organization_id,
            document_id=invoice.document_id,
            invoice_record_id=invoice.id,
            status=ReviewTaskStatus.OPEN,
            reason_codes_json=sorted(set(reasons))[:20],
        )
        .on_conflict_do_update(
            index_elements=["invoice_record_id"],
            # Literal predicate: with bound parameters PostgreSQL cannot match the
            # partial unique index once psycopg switches to prepared statements.
            index_where=text("status IN ('OPEN','IN_PROGRESS')"),
            set_={"reason_codes_json": sorted(set(reasons))[:20], "updated_at": datetime.now(UTC)},
        )
    )


def validate_invoices(
    session: Session,
    *,
    document: Document,
    invoices: list[InvoiceRecord],
    run_id: uuid.UUID,
    include_document_level: bool,
    extra_document_issues: list[IssueDraft] | None = None,
) -> ValidationOutcome | None:
    ctx_base = context()
    reset_run_issues(session, run_id, document.id, [i.id for i in invoices] if not include_document_level else None)
    outcomes: list[ValidationOutcome] = []
    for invoice in invoices:
        lines = list(session.execute(select(InvoiceLineItem).where(InvoiceLineItem.invoice_record_id == invoice.id)).scalars())
        view = build_view(invoice, lines)
        ctx = ValidationContext(
            **{**ctx_base.__dict__, "duplicate_candidates": find_duplicate_candidates(session, invoice, document.sha256)}
        )
        issues = run_rules(view, ctx)
        write_issues(session, document=document, invoice=invoice, run_id=run_id, issues=issues)
        outcome = outcome_for(issues)
        invoice.validation_outcome = outcome
        outcomes.append(outcome)
        if invoice.review_status in (ReviewStatus.APPROVED, ReviewStatus.REJECTED):
            continue
        if outcome in (ValidationOutcome.REQUIRES_REVIEW, ValidationOutcome.FAILED):
            if invoice.review_status != ReviewStatus.IN_REVIEW:
                invoice.review_status = ReviewStatus.REQUIRED
            reasons = [i.rule_code for i in issues if SEVERITY_ORDER[i.severity] >= SEVERITY_ORDER[Severity.WARNING]]
            ensure_review_task(session, invoice, reasons)
        elif invoice.review_status == ReviewStatus.REQUIRED:
            invoice.review_status = ReviewStatus.NOT_REQUIRED
            session.execute(
                update(ReviewTask)
                .where(ReviewTask.invoice_record_id == invoice.id, ReviewTask.status == ReviewTaskStatus.OPEN)
                .values(status=ReviewTaskStatus.CANCELLED, resolved_at=datetime.now(UTC))
            )

    if include_document_level:
        doc_issues = list(extra_document_issues or [])
        dup = duplicate_file_issue(session, document)
        if dup:
            doc_issues.append(dup)
        if document.document_type == DocumentType.UNKNOWN:
            doc_issues.append(
                IssueDraft("UNKNOWN_DOCUMENT_TYPE", Severity.WARNING, "Document type could not be determined; manual classification needed")
            )
        write_issues(session, document=document, invoice=None, run_id=run_id, issues=doc_issues)
        if doc_issues:
            outcomes.append(outcome_for(doc_issues))
    else:
        # Keep document-level issues from the original processing run in the rollup.
        open_doc_level = session.execute(
            select(ValidationIssue.severity, ValidationIssue.rule_code).where(
                ValidationIssue.document_id == document.id,
                ValidationIssue.invoice_record_id.is_(None),
                ValidationIssue.resolution_status == ResolutionStatus.OPEN,
            )
        ).all()
        if open_doc_level:
            outcomes.append(outcome_for([IssueDraft(code, sev, "") for sev, code in open_doc_level]))
        others = (
            session.execute(
                select(InvoiceRecord.validation_outcome).where(
                    InvoiceRecord.document_id == document.id,
                    InvoiceRecord.superseded_at.is_(None),
                    InvoiceRecord.id.not_in([i.id for i in invoices]),
                )
            )
            .scalars()
            .all()
        )
        outcomes.extend(o for o in others if o is not None)
    result = worst_outcome(outcomes)
    document.validation_outcome = result
    return result
