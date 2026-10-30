"""Pipeline stage handlers (sync, run inside Celery workers).

Every handler is idempotent under at-least-once delivery:
* it runs only with a valid lease (see ``claim_task``),
* writes are keyed (page upserts, per-run replace of results),
* the stage transition and the next stage's outbox event are committed in the
  same transaction as the results, after re-checking the lease and run state.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import sync_session
from app.core.exceptions import PermanentProcessingError
from app.core.logging import document_id_var, get_logger
from app.modules.auditing.service import record_audit
from app.modules.comparison.models import ComparisonDocument, DocumentComparison
from app.modules.comparison.service import run_comparison
from app.modules.documents.fingerprint import FileRejected, check_office_archive
from app.modules.documents.models import (
    Document,
    DocumentPage,
    DocumentTable,
    SpreadsheetRow,
    StorageObject,
)
from app.modules.documents.storage import bucket_for, get_storage, make_key
from app.modules.extraction.currency_policy import load_policy_sync, resolve_with_organization
from app.modules.extraction.models import ExtractionRun, InvoiceLineItem, InvoiceRecord
from app.modules.extraction.prompts import INVOICE_PROMPT_VERSION
from app.modules.extraction.providers.factory import get_extraction_provider
from app.modules.extraction.providers.fixture import LocalRulesProvider
from app.modules.extraction.schemas import NormalizedInvoice
from app.modules.extraction.service import DocumentExtraction, ExtractionPage, extract_document
from app.modules.jobs.lifecycle import (
    Claim,
    advance,
    fail_run,
    finalize_document_run,
    is_cancelled,
    lock_owned_task,
    lock_run,
    mark_task_done,
    maybe_finish_parsing,
    page_counts,
    transition,
)
from app.modules.jobs.models import ProcessingRun
from app.modules.jobs.outbox import ensure_task
from app.modules.parsing.classification import ClassificationResult, classify_text
from app.modules.parsing.image_parser import count_frames, process_image_frame
from app.modules.parsing.ocr_service import get_ocr_provider
from app.modules.parsing.pdf_parser import inspect_pdf, open_pdf, process_pdf_page
from app.modules.parsing.schemas import PageResult
from app.modules.parsing.spreadsheet_parser import build_tables
from app.modules.search.embeddings import get_embedding_provider
from app.modules.search.indexing import index_document
from app.modules.validation.rules import IssueDraft
from app.modules.validation.service import validate_invoices
from app.shared.enums import (
    ComparisonStatus,
    DocumentStatus,
    DocumentType,
    ExtractionStatus,
    FileKind,
    JobType,
    PageStatus,
    RunState,
    ScanStatus,
    Severity,
    StorageCategory,
    StorageObjectStatus,
    TaskType,
)
from app.shared.text import normalize_invoice_number, normalize_supplier, truncate
from app.workers.files import local_copy

logger = get_logger(__name__)


class LeaseLost(Exception):
    """Another worker owns this task now; discard our results."""


def _commit_owned(session: Session, claim: Claim, fn: Callable[[ProcessingRun], None]) -> None:
    """Re-check the lease, lock the run, apply ``fn``, mark the task done, commit."""
    task = lock_owned_task(session, claim)
    if task is None:
        session.rollback()
        raise LeaseLost(str(claim.task_id))
    run = lock_run(session, claim.run_id)
    if run.state.is_terminal:
        session.rollback()
        raise LeaseLost("run already terminal")
    # Mark done first (and flush: sessions do not autoflush) so stage-completion
    # checks inside ``fn`` see this task as finished.
    mark_task_done(task)
    session.flush()
    fn(run)
    session.commit()


def _document(session: Session, run: ProcessingRun) -> Document:
    if run.document_id is None:
        raise PermanentProcessingError("Run has no document", code="DOCUMENT_MISSING")
    doc = session.get(Document, run.document_id)
    if doc is None or doc.deleted_at is not None or doc.organization_id != run.organization_id:
        raise PermanentProcessingError("Document no longer available", code="DOCUMENT_DELETED")
    return doc


def _store_artifact(session: Session, doc: Document, category: StorageCategory, payload: Any, suffix: str = ".json") -> str:
    key = make_key(category, doc.organization_id, doc.id, suffix)
    bucket = bucket_for(category)
    get_storage().put_json(bucket, key, payload)
    session.add(
        StorageObject(
            id=uuid.uuid4(),
            organization_id=doc.organization_id,
            document_id=doc.id,
            category=category,
            bucket=bucket,
            key=key,
            status=StorageObjectStatus.ACTIVE,
        )
    )
    return key


# --- PREPROCESS -----------------------------------------------------------------


def handle_preprocess(claim: Claim) -> None:
    settings = get_settings()
    with sync_session() as session:
        run = lock_run(session, claim.run_id)
        if run.state == RunState.QUEUED:
            transition(session, run, RunState.PREPROCESSING)
        doc = _document(session, run)
        doc.status = DocumentStatus.PROCESSING
        session.commit()
        document_id_var.set(str(doc.id))
        path = local_copy(doc)

        scan_status = ScanStatus.SKIPPED  # signature/archive checks run at upload; no AV engine configured

        page_total = 0
        metadata: dict[str, Any] = {}
        if doc.file_kind == FileKind.PDF:
            info = inspect_pdf(path)
            page_total, metadata = info.page_count, info.metadata
        elif doc.file_kind in (FileKind.IMAGE, FileKind.TIFF):
            page_total = count_frames(path)
            if doc.file_kind == FileKind.IMAGE:
                page_total = 1
        elif doc.file_kind == FileKind.XLSX:
            with open(path, "rb") as fh:
                try:
                    check_office_archive(fh, settings)
                except FileRejected as exc:
                    raise PermanentProcessingError(exc.message, code=exc.code) from exc
        if page_total > settings.max_pdf_pages:
            raise PermanentProcessingError(
                f"Document has {page_total} pages; limit is {settings.max_pdf_pages}", code="PAGE_LIMIT_EXCEEDED"
            )

        def apply(run: ProcessingRun) -> None:
            doc.scan_status = scan_status
            doc.metadata_json = {**(doc.metadata_json or {}), **metadata}
            if doc.file_kind.is_spreadsheet:
                transition(session, run, RunState.PARSING)
                ensure_task(session, run.id, TaskType.PARSE_SPREADSHEET)
                return
            doc.page_count = page_total
            run.pages_total = page_total
            done_pages = set(
                session.execute(
                    select(DocumentPage.page_number).where(
                        DocumentPage.document_id == doc.id,
                        DocumentPage.processing_status == PageStatus.DONE,
                        DocumentPage.parser_version == settings.parser_version,
                    )
                ).scalars()
            )
            transition(session, run, RunState.PARSING)
            batch = max(1, settings.page_batch_size)
            created = 0
            for start in range(1, page_total + 1, batch):
                end = min(page_total, start + batch - 1)
                if all(p in done_pages for p in range(start, end + 1)):
                    continue  # checkpoint from an earlier run
                ensure_task(session, run.id, TaskType.PARSE_PAGES, start, end)
                created += 1
            if created == 0:
                maybe_finish_parsing(session, run)
            else:
                done, failed = page_counts(session, run)
                run.pages_completed, run.pages_failed = done, failed

        _commit_owned(session, claim, apply)


# --- PARSE_PAGES ------------------------------------------------------------------


def _persist_page(session: Session, doc: Document, result: PageResult) -> None:
    settings = get_settings()
    text = result.text or ""
    text_key = None
    if len(text) > settings.page_text_db_max_chars:
        text_key = _store_artifact(session, doc, StorageCategory.PAGE_TEXT, {"page": result.page_number, "text": text})
    layout_key = None
    if result.lines:
        layout_key = _store_artifact(
            session,
            doc,
            StorageCategory.PAGE_LAYOUT,
            {
                "page": result.page_number,
                "width": result.page_width,
                "height": result.page_height,
                "lines": [ln.to_json() for ln in result.lines],
            },
        )
    values = {
        "page_type": result.page_type,
        "extracted_text": truncate(text, settings.page_text_db_max_chars),
        "text_storage_key": text_key,
        "layout_storage_key": layout_key,
        "character_count": len(text),
        "ocr_engine": result.ocr_engine,
        "ocr_confidence": Decimal(str(result.ocr_confidence)) if result.ocr_confidence is not None else None,
        "processing_status": PageStatus.DONE,
        "parser_version": settings.parser_version,
        "error_code": None,
        "metadata_json": result.metadata,
    }
    page_id = session.execute(
        pg_insert(DocumentPage)
        .values(id=uuid.uuid4(), organization_id=doc.organization_id, document_id=doc.id, page_number=result.page_number, **values)
        .on_conflict_do_update(index_elements=["document_id", "page_number"], set_=values)
        .returning(DocumentPage.id)
    ).scalar_one()
    session.execute(delete(DocumentTable).where(DocumentTable.document_id == doc.id, DocumentTable.page_id == page_id))
    for table in result.tables:
        session.add(
            DocumentTable(
                id=uuid.uuid4(),
                organization_id=doc.organization_id,
                document_id=doc.id,
                page_id=page_id,
                page_number=result.page_number,
                source_key=f"page:{result.page_number}",
                table_index=table.index,
                header_json=table.header,
                normalized_data_json=table.rows[:200],
                row_count=len(table.rows),
                column_count=max((len(r) for r in table.rows), default=0),
                metadata_json={"bbox": list(table.bbox) if table.bbox else None, "truncated": len(table.rows) > 200},
            )
        )


def handle_parse_pages(claim: Claim) -> None:
    settings = get_settings()
    assert claim.page_start is not None and claim.page_end is not None
    with sync_session() as session:
        run = session.get(ProcessingRun, claim.run_id)
        assert run is not None
        doc = _document(session, run)
        document_id_var.set(str(doc.id))
        path = local_copy(doc)
        done = set(
            session.execute(
                select(DocumentPage.page_number).where(
                    DocumentPage.document_id == doc.id,
                    DocumentPage.page_number.between(claim.page_start, claim.page_end),
                    DocumentPage.processing_status == PageStatus.DONE,
                    DocumentPage.parser_version == settings.parser_version,
                )
            ).scalars()
        )
        session.commit()
        ocr = get_ocr_provider()
        pdf = open_pdf(path) if doc.file_kind == FileKind.PDF else None
        try:
            for page_number in range(claim.page_start, claim.page_end + 1):
                if page_number in done:
                    continue
                if is_cancelled(session, run.id):
                    session.commit()
                    return
                try:
                    if pdf is not None:
                        result = process_pdf_page(pdf, page_number, ocr)
                    else:
                        result = process_image_frame(path, page_number, ocr)
                except PermanentProcessingError as exc:
                    session.rollback()
                    from app.modules.jobs.lifecycle import mark_pages_failed

                    mark_pages_failed(session, run, page_number, page_number, exc.code)
                    session.commit()
                    logger.warning("page_failed", extra={"page": page_number, "error_code": exc.code})
                    continue
                _persist_page(session, doc, result)
                session.commit()  # checkpoint: this page will not be repeated
        finally:
            if pdf is not None:
                pdf.close()

        _commit_owned(session, claim, lambda run: maybe_finish_parsing(session, run))


# --- PARSE_SPREADSHEET --------------------------------------------------------------


def handle_parse_spreadsheet(claim: Claim) -> None:
    with sync_session() as session:
        run = session.get(ProcessingRun, claim.run_id)
        assert run is not None
        doc = _document(session, run)
        document_id_var.set(str(doc.id))
        path = local_copy(doc)
        # Replace any partial output of an earlier attempt, atomically with the new output.
        session.execute(delete(DocumentTable).where(DocumentTable.document_id == doc.id, DocumentTable.page_id.is_(None)))
        issues: list[dict[str, Any]] = []
        registers = 0
        sheets = 0
        total_rows = 0
        for table, rows in build_tables(path, doc.file_kind):
            sheets += 1
            table_id = uuid.uuid4()
            source_key = f"sheet:{table.sheet_name}" if table.sheet_name else "csv"
            session.add(
                DocumentTable(
                    id=table_id,
                    organization_id=doc.organization_id,
                    document_id=doc.id,
                    page_id=None,
                    source_key=source_key[:300],
                    sheet_name=table.sheet_name,
                    table_index=table.table_index,
                    header_row_number=table.header_row_number,
                    header_json=table.headers,
                    row_count=0,
                    column_count=table.column_count,
                    metadata_json={},
                )
            )
            session.flush()
            preview: list[Any] = []
            batch: list[dict[str, Any]] = []
            count = 0
            for row_number, record in rows:
                count += 1
                if len(preview) < 20:
                    preview.append({"row": row_number, "cells": record})
                batch.append(
                    {
                        "id": uuid.uuid4(),
                        "organization_id": doc.organization_id,
                        "document_id": doc.id,
                        "table_id": table_id,
                        "sheet_name": table.sheet_name,
                        "row_number": row_number,
                        "cells_json": record,
                    }
                )
                if len(batch) >= 1000:
                    session.execute(insert(SpreadsheetRow), batch)
                    batch = []
            if batch:
                session.execute(insert(SpreadsheetRow), batch)
            total_rows += count
            if table.looks_like_register:
                registers += 1
            issues.extend({**i, "sheet": table.sheet_name} for i in table.issues)
            session.execute(
                update(DocumentTable)
                .where(DocumentTable.id == table_id)
                .values(
                    row_count=count,
                    normalized_data_json=preview,
                    metadata_json={
                        "issues": table.issues[:200],
                        "truncated": table.truncated,
                        "looks_like_register": table.looks_like_register,
                    },
                )
            )

        classification = classify_text("", doc.file_kind, looks_like_register=registers > 0)

        def apply(run: ProcessingRun) -> None:
            _apply_classification(doc, classification)
            doc.sheet_count = sheets
            doc.metadata_json = {**(doc.metadata_json or {}), "rows": total_rows}
            drafts: list[IssueDraft] = []
            formula = [i for i in issues if i["code"] == "FORMULA_CACHE_MISSING"]
            if formula:
                drafts.append(
                    IssueDraft(
                        "FORMULA_CACHE_MISSING",
                        Severity.WARNING,
                        f"{len(formula)} formula cell(s) have no cached value; values were not computed",
                        details={"cells": formula[:50]},
                    )
                )
            if any(i["code"] == "ROW_LIMIT_REACHED" for i in issues):
                drafts.append(
                    IssueDraft(
                        "ROW_LIMIT_REACHED",
                        Severity.ERROR,
                        "Spreadsheet exceeds the configured row limit; remaining rows were not imported",
                    )
                )
            inconsistent = [i for i in issues if i["code"] == "INCONSISTENT_ROW_LENGTH"]
            if inconsistent:
                drafts.append(
                    IssueDraft(
                        "INCONSISTENT_ROW_LENGTH",
                        Severity.INFO,
                        f"{len(inconsistent)} row(s) have a different number of columns than the header",
                        details={"rows": inconsistent[:50]},
                    )
                )
            validate_invoices(session, document=doc, invoices=[], run_id=run.id, include_document_level=True, extra_document_issues=drafts)
            advance(session, run, RunState.INDEXING, TaskType.INDEX)

        _commit_owned(session, claim, apply)


def _apply_classification(doc: Document, result: ClassificationResult) -> None:
    settings = get_settings()
    doc.document_type = result.document_type
    doc.classification_method = result.method
    doc.classification_confidence = result.confidence
    doc.classification_version = settings.classification_version
    doc.review_required = result.needs_review
    doc.metadata_json = {**(doc.metadata_json or {}), "classification_signals": result.signals}


# --- EXTRACT --------------------------------------------------------------------------


def _load_pages(session: Session, doc: Document) -> list[ExtractionPage]:
    pages = []
    rows = session.execute(
        select(
            DocumentPage.page_number,
            DocumentPage.extracted_text,
            DocumentPage.text_storage_key,
            DocumentPage.ocr_engine,
            DocumentPage.ocr_confidence,
        )
        .where(DocumentPage.document_id == doc.id, DocumentPage.processing_status == PageStatus.DONE)
        .order_by(DocumentPage.page_number)
    ).all()
    storage = get_storage()
    for number, text, text_key, engine, conf in rows:
        if text_key:
            text = storage.get_json(bucket_for(StorageCategory.PAGE_TEXT), text_key).get("text", text)
        pages.append(
            ExtractionPage(
                page_number=number,
                text=text or "",
                method="ocr" if engine else "native",
                ocr_confidence=float(conf) if conf is not None else None,
            )
        )
    return pages


def _layout_loader(doc: Document) -> Callable[[int], list[dict[str, Any]]]:
    def load(page_number: int) -> list[dict[str, Any]]:
        with sync_session() as session:
            key = session.execute(
                select(DocumentPage.layout_storage_key).where(DocumentPage.document_id == doc.id, DocumentPage.page_number == page_number)
            ).scalar_one_or_none()
        if not key:
            return []
        data = get_storage().get_json(bucket_for(StorageCategory.PAGE_LAYOUT), key)
        return list(data.get("lines", []))

    return load


def _evidence_json(inv: NormalizedInvoice) -> dict[str, Any]:
    return {k: v.model_dump(mode="json") for k, v in inv.evidence.items()}


def _persist_extraction(
    session: Session, run: ProcessingRun, doc: Document, result: DocumentExtraction | None, classification: ClassificationResult
) -> list[uuid.UUID]:
    settings = get_settings()
    now = datetime.now(UTC)
    existing = session.execute(select(ExtractionRun).where(ExtractionRun.processing_run_id == run.id)).scalar_one_or_none()
    if existing is not None:
        session.delete(existing)  # idempotent re-execution of this stage
        session.flush()
    revision = (
        session.execute(select(func.max(ExtractionRun.extraction_revision)).where(ExtractionRun.document_id == doc.id)).scalar_one() or 0
    ) + 1
    superseded = session.execute(
        update(InvoiceRecord).where(InvoiceRecord.document_id == doc.id, InvoiceRecord.superseded_at.is_(None)).values(superseded_at=now)
    )
    if superseded.rowcount:  # type: ignore[attr-defined]
        # Finished comparisons over the replaced invoices no longer reflect the data.
        session.execute(
            update(DocumentComparison)
            .where(
                DocumentComparison.organization_id == doc.organization_id,
                DocumentComparison.id.in_(select(ComparisonDocument.comparison_id).where(ComparisonDocument.document_id == doc.id)),
                DocumentComparison.status == ComparisonStatus.COMPLETED,
            )
            .values(status=ComparisonStatus.STALE, stale_reason="document reprocessed")
        )
    if result is None:
        status = ExtractionStatus.SKIPPED
    elif result.failed_segments and result.invoices:
        status = ExtractionStatus.PARTIAL
    elif result.failed_segments:
        status = ExtractionStatus.FAILED
    else:
        status = ExtractionStatus.SUCCEEDED
    raw_key = None
    if result is not None and result.raw_responses and settings.store_raw_llm_responses:
        raw_key = _store_artifact(session, doc, StorageCategory.EXTRACTION_RAW, {"responses": result.raw_responses})
    normalized = {
        "invoices": [inv.model_dump(mode="json") for inv in result.invoices] if result else [],
        "segments": [s.__dict__ for s in result.segments] if result else [],
        "classification": {"type": classification.document_type.value, "method": classification.method, "signals": classification.signals},
    }
    extraction = ExtractionRun(
        id=uuid.uuid4(),
        organization_id=doc.organization_id,
        document_id=doc.id,
        processing_run_id=run.id,
        provider=result.provider if result else "none",
        model_name=result.model if result else "none",
        prompt_version=INVOICE_PROMPT_VERSION,
        schema_version=settings.extraction_schema_version,
        extraction_revision=revision,
        raw_result_storage_key=raw_key,
        normalized_result_json=normalized,
        usage_json=result.usage if result else {},
        status=status,
        error_code=result.failed_segments[0].error_code if result and result.failed_segments else None,
    )
    session.add(extraction)
    session.flush()
    ids: list[uuid.UUID] = []
    invoices = result.invoices if result else []
    policy = load_policy_sync(session, doc.organization_id) if any(inv.currency is None for inv in invoices) else None
    for inv in invoices:
        if policy is not None:
            resolve_with_organization(session, doc.organization_id, doc.id, inv, policy)
        kind = {"CREDIT_NOTE": DocumentType.CREDIT_NOTE, "RECEIPT": DocumentType.RECEIPT}.get(inv.document_kind or "")
        if kind is None:
            kind = doc.document_type if doc.document_type.is_invoice_like else DocumentType.INVOICE
        record = InvoiceRecord(
            id=uuid.uuid4(),
            organization_id=doc.organization_id,
            document_id=doc.id,
            extraction_run_id=extraction.id,
            segment_index=inv.segment_index,
            page_start=inv.page_start,
            page_end=inv.page_end,
            document_type=kind,
            invoice_number=inv.invoice_number,
            normalized_invoice_number=normalize_invoice_number(inv.invoice_number),
            invoice_date=inv.invoice_date,
            invoice_date_raw=inv.invoice_date_raw,
            payment_due_date=inv.payment_due_date,
            supplier_name=inv.supplier_name,
            normalized_supplier=normalize_supplier(inv.supplier_name),
            supplier_tax_id=inv.supplier_tax_id,
            supplier_address=inv.supplier_address,
            customer_name=inv.customer_name,
            customer_address=inv.customer_address,
            purchase_order_number=inv.purchase_order_number,
            payment_reference=inv.payment_reference,
            currency=inv.currency,
            currency_raw=inv.currency_raw,
            currency_source=inv.currency_source,
            subtotal=inv.subtotal,
            discount_amount=inv.discount_amount,
            shipping_amount=inv.shipping_amount,
            tax_amount=inv.tax_amount,
            total_amount=inv.total_amount,
            amounts_tax_inclusive=inv.amounts_tax_inclusive,
            extraction_confidence=inv.confidence,
            extraction_status=ExtractionStatus.SUCCEEDED,
            field_support_json=inv.field_support(),
            source_evidence_json=_evidence_json(inv),
            alternatives_json={"alternatives": inv.alternatives, "notes": [n.model_dump() for n in inv.notes]},
            corrected_fields_json=[],
        )
        session.add(record)
        session.flush()
        for li in inv.line_items:
            session.add(
                InvoiceLineItem(
                    id=uuid.uuid4(),
                    invoice_record_id=record.id,
                    position=li.position,
                    description=li.description,
                    quantity=li.quantity,
                    unit_price=li.unit_price,
                    discount_amount=li.discount_amount,
                    tax_rate=li.tax_rate,
                    tax_amount=li.tax_amount,
                    line_total=li.line_total,
                    source_evidence_json=li.evidence.model_dump(mode="json") if li.evidence else {},
                )
            )
        ids.append(record.id)
    return ids


def handle_extract(claim: Claim) -> None:
    settings = get_settings()
    with sync_session() as session:
        run = session.get(ProcessingRun, claim.run_id)
        assert run is not None
        doc = _document(session, run)
        document_id_var.set(str(doc.id))
        pages = _load_pages(session, doc)
        session.commit()
        full_text = "\n".join(p.text for p in pages)
        classification = classify_text(full_text, doc.file_kind)
        provider = get_extraction_provider()
        if settings.llm_classification_enabled and classification.needs_review:
            sample = "\n".join(p.text for p in pages[:3])
            response = provider.classify_document(sample)
            llm_type = DocumentType(response.classification.document_type)
            classification = ClassificationResult(
                llm_type, None, f"llm:{response.model}", classification.signals, needs_review=llm_type == DocumentType.UNKNOWN
            )

        result: DocumentExtraction | None = None
        if classification.document_type.is_invoice_like:
            hosted = provider.provider_name() != "local-rules"
            result = extract_document(
                pages,
                provider,
                document_id=str(doc.id),
                document_type_hint=classification.document_type.value,
                layout_loader=_layout_loader(doc),
                fallback=LocalRulesProvider() if hosted and settings.extraction_fallback_to_rules else None,
                cross_check=hosted and settings.extraction_cross_check,
                max_workers=settings.llm_max_concurrency if hosted else 1,
            )

        def apply(run: ProcessingRun) -> None:
            _apply_classification(doc, classification)
            ids = _persist_extraction(session, run, doc, result, classification)
            payload = dict(run.payload_json or {})
            payload["extraction"] = {
                "invoices": len(ids),
                "failed_segments": [s.__dict__ for s in result.failed_segments] if result else [],
                "skipped": result is None,
            }
            run.payload_json = payload
            if result is not None and not ids:
                doc.review_required = True
            if ids:
                advance(session, run, RunState.VALIDATING, TaskType.VALIDATE)
            else:
                # Nothing to validate; run document-level checks before indexing.
                drafts = _document_issue_drafts(run, doc)
                validate_invoices(
                    session, document=doc, invoices=[], run_id=run.id, include_document_level=True, extra_document_issues=drafts
                )
                advance(session, run, RunState.INDEXING, TaskType.INDEX)

        _commit_owned(session, claim, apply)


def _document_issue_drafts(run: ProcessingRun, doc: Document) -> list[IssueDraft]:
    drafts: list[IssueDraft] = []
    info = (run.payload_json or {}).get("extraction", {})
    for seg in info.get("failed_segments", []):
        drafts.append(
            IssueDraft(
                "EXTRACTION_FAILED",
                Severity.ERROR,
                f"Extraction failed for pages {seg.get('page_start')}-{seg.get('page_end')} ({seg.get('error_code')})",
                details=seg,
            )
        )
    if doc.document_type.is_invoice_like and info.get("invoices") == 0 and not info.get("skipped"):
        drafts.append(
            IssueDraft("NO_INVOICE_FOUND", Severity.ERROR, "Document looks like an invoice but no invoice data could be extracted")
        )
    if (doc.metadata_json or {}).get("repaired"):
        drafts.append(IssueDraft("PDF_REPAIRED", Severity.ERROR, "The PDF is damaged and was repaired on open; content may be incomplete"))
    if run.pages_failed:
        drafts.append(
            IssueDraft(
                "PAGES_FAILED",
                Severity.WARNING,
                f"{run.pages_failed} page(s) could not be processed",
                details={"pages_failed": run.pages_failed},
            )
        )
    if doc.review_required and doc.document_type != DocumentType.UNKNOWN and doc.classification_confidence is not None:
        drafts.append(
            IssueDraft(
                "LOW_CLASSIFICATION_CONFIDENCE",
                Severity.WARNING,
                f"Classification confidence {doc.classification_confidence} is low",
                details={"signals": (doc.metadata_json or {}).get("classification_signals")},
            )
        )
    return drafts


# --- VALIDATE ---------------------------------------------------------------------------


def handle_validate(claim: Claim) -> None:
    with sync_session() as session:

        def apply(run: ProcessingRun) -> None:
            if run.state == RunState.QUEUED:
                transition(session, run, RunState.VALIDATING)
            doc = _document(session, run)
            if run.job_type == JobType.REVALIDATION:
                invoice_id = uuid.UUID(str(run.payload_json["invoice_id"]))
                invoices = list(
                    session.execute(
                        select(InvoiceRecord).where(
                            InvoiceRecord.id == invoice_id,
                            InvoiceRecord.organization_id == run.organization_id,
                            InvoiceRecord.superseded_at.is_(None),
                        )
                    ).scalars()
                )
                validate_invoices(session, document=doc, invoices=invoices, run_id=run.id, include_document_level=False)
            else:
                invoices = list(
                    session.execute(
                        select(InvoiceRecord)
                        .where(InvoiceRecord.document_id == doc.id, InvoiceRecord.superseded_at.is_(None))
                        .order_by(InvoiceRecord.segment_index)
                    ).scalars()
                )
                validate_invoices(
                    session,
                    document=doc,
                    invoices=invoices,
                    run_id=run.id,
                    include_document_level=True,
                    extra_document_issues=_document_issue_drafts(run, doc),
                )
            advance(session, run, RunState.INDEXING, TaskType.INDEX)

        _commit_owned(session, claim, apply)


# --- INDEX ------------------------------------------------------------------------------------


def handle_index(claim: Claim) -> None:
    embedder = get_embedding_provider()
    with sync_session() as session:

        def apply(run: ProcessingRun) -> None:
            if run.state == RunState.QUEUED:
                transition(session, run, RunState.INDEXING)
            doc = _document(session, run)
            document_id_var.set(str(doc.id))
            count = index_document(session, doc, embedder)
            payload = dict(run.payload_json or {})
            payload["chunks_indexed"] = count
            run.payload_json = payload
            finalize_document_run(session, run, doc)

        _commit_owned(session, claim, apply)


# --- COMPARE ----------------------------------------------------------------------------------


def handle_compare(claim: Claim) -> None:
    settings = get_settings()
    with sync_session() as session:

        def apply(run: ProcessingRun) -> None:
            if run.state == RunState.QUEUED:
                transition(session, run, RunState.COMPARING)
            comparison = session.execute(
                select(DocumentComparison).where(
                    DocumentComparison.processing_run_id == run.id, DocumentComparison.organization_id == run.organization_id
                )
            ).scalar_one()
            comparison.status = ComparisonStatus.RUNNING
            summary = run_comparison(session, comparison, settings.date_day_first)
            problems = sum(int(summary.get(k, 0)) for k in summary if k.endswith("_count") and k != "matched_count")
            transition(session, run, RunState.COMPLETED_WITH_WARNINGS if problems else RunState.COMPLETED)
            record_audit(
                session,
                organization_id=run.organization_id,
                actor_id=run.created_by,
                action="comparison.completed",
                resource_type="comparison",
                resource_id=comparison.id,
                metadata={"summary": summary},
            )

        _commit_owned(session, claim, apply)


HANDLERS: dict[TaskType, Callable[[Claim], None]] = {
    TaskType.PREPROCESS: handle_preprocess,
    TaskType.PARSE_PAGES: handle_parse_pages,
    TaskType.PARSE_SPREADSHEET: handle_parse_spreadsheet,
    TaskType.EXTRACT: handle_extract,
    TaskType.VALIDATE: handle_validate,
    TaskType.INDEX: handle_index,
    TaskType.COMPARE: handle_compare,
}


def fail_unexpected(run_id: uuid.UUID, code: str, message: str) -> None:
    with sync_session() as session:
        run = lock_run(session, run_id)
        fail_run(session, run, code, message)
        session.commit()
