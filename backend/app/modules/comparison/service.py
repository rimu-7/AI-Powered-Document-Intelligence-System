"""Comparison/reconciliation execution (sync, comparison workers) and CSV export."""

from __future__ import annotations

import csv
import io
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import PermanentProcessingError
from app.modules.comparison.matching import ComparableRecord, MatchOptions, match_records
from app.modules.comparison.models import ComparisonFinding, DocumentComparison
from app.modules.documents.models import Document, DocumentTable, SpreadsheetRow
from app.modules.extraction.models import InvoiceLineItem, InvoiceRecord
from app.shared.dates import parse_date
from app.shared.enums import ComparisonStatus, ComparisonType, CurrencyCode, FindingStatus
from app.shared.money import UNAMBIGUOUS_SYMBOLS, parse_amount, to_currency_code
from app.shared.text import normalize_invoice_number, normalize_supplier


def _page_ref(evidence: dict[str, Any] | None) -> dict[str, Any] | None:
    if not evidence:
        return None
    return {k: evidence.get(k) for k in ("page_number", "supporting_text", "bounding_box") if evidence.get(k) is not None}


def invoice_to_record(inv: InvoiceRecord, document: Document, lines: list[InvoiceLineItem]) -> ComparableRecord:
    evidence = inv.source_evidence_json or {}
    return ComparableRecord(
        record_id=str(inv.id),
        source="invoice",
        document_id=str(inv.document_id),
        invoice_number=inv.invoice_number,
        normalized_number=inv.normalized_invoice_number,
        supplier=inv.supplier_name,
        normalized_supplier=inv.normalized_supplier,
        customer=inv.customer_name,
        invoice_date=inv.invoice_date,
        currency=inv.currency,
        subtotal=inv.subtotal,
        tax_amount=inv.tax_amount,
        total_amount=inv.total_amount,
        line_items=[
            {
                "position": li.position,
                "description": li.description,
                "line_total": format(li.line_total, "f") if li.line_total is not None else None,
                "evidence": _page_ref(li.source_evidence_json),
            }
            for li in sorted(lines, key=lambda x: x.position)
        ],
        reference={
            "document_id": str(document.id),
            "filename": document.original_filename,
            "invoice_record_id": str(inv.id),
            "page_start": inv.page_start,
            "page_end": inv.page_end,
        },
        field_refs={k: _page_ref(v) for k, v in evidence.items() if isinstance(v, dict)},
    )


def _cell(cells: dict[str, Any], header: str | None) -> tuple[str | None, str | None]:
    if not header or header not in cells:
        return None, None
    entry = cells[header]
    return entry.get("v"), entry.get("c")


def row_to_record(row: SpreadsheetRow, document: Document, mapping: dict[str, str], day_first: bool) -> ComparableRecord:
    cells = row.cells_json
    notes: list[str] = []
    refs: dict[str, Any] = {}

    def text_field(name: str) -> str | None:
        value, coord = _cell(cells, mapping.get(name))
        if coord:
            refs[name] = {"cell": coord}
        return value

    def amount_field(name: str) -> Decimal | None:
        value, coord = _cell(cells, mapping.get(name))
        if coord:
            refs[name] = {"cell": coord}
        if value is None:
            return None
        parsed = parse_amount(value)
        if parsed is None:
            notes.append(f"{name}: unparseable {value!r}")
            return None
        if parsed.ambiguous:
            notes.append(f"{name}: ambiguous separator in {value!r}")
        return parsed.value

    number = text_field("invoice_number")
    supplier = text_field("supplier_name")
    raw_date = text_field("invoice_date")
    parsed_date = parse_date(raw_date, day_first=day_first) if raw_date else None
    if raw_date and parsed_date is None:
        notes.append(f"invoice_date: unparseable {raw_date!r}")
    raw_currency = text_field("currency")
    currency: CurrencyCode | None = None
    if raw_currency:
        token = raw_currency.strip()
        currency = to_currency_code(token) or UNAMBIGUOUS_SYMBOLS.get(token)
        if currency is None:
            notes.append(f"currency: unrecognised {raw_currency!r}")
    return ComparableRecord(
        record_id=str(row.id),
        source="row",
        document_id=str(row.document_id),
        invoice_number=number,
        normalized_number=normalize_invoice_number(number),
        supplier=supplier,
        normalized_supplier=normalize_supplier(supplier),
        customer=text_field("customer_name"),
        invoice_date=parsed_date.value if parsed_date else None,
        currency=currency,
        subtotal=amount_field("subtotal"),
        tax_amount=amount_field("tax_amount"),
        total_amount=amount_field("total_amount"),
        reference={
            "document_id": str(document.id),
            "filename": document.original_filename,
            "sheet_name": row.sheet_name,
            "row_number": row.row_number,
        },
        field_refs=refs,
        parse_notes=notes,
    )


def _current_invoices(
    session: Session, document_ids: Iterable[uuid.UUID], selected: list[str] | None, org_id: uuid.UUID
) -> list[ComparableRecord]:
    records: list[ComparableRecord] = []
    for doc_id in document_ids:
        document = session.get(Document, doc_id)
        if document is None or document.organization_id != org_id or document.deleted_at is not None:
            raise PermanentProcessingError("Document not available", code="DOCUMENT_UNAVAILABLE")
        stmt = select(InvoiceRecord).where(
            InvoiceRecord.document_id == doc_id,
            InvoiceRecord.organization_id == org_id,
            InvoiceRecord.superseded_at.is_(None),
        )
        if selected:
            stmt = stmt.where(InvoiceRecord.id.in_([uuid.UUID(s) for s in selected]))
        for inv in session.execute(stmt.order_by(InvoiceRecord.segment_index)).scalars():
            lines = list(session.execute(select(InvoiceLineItem).where(InvoiceLineItem.invoice_record_id == inv.id)).scalars())
            records.append(invoice_to_record(inv, document, lines))
    return records


def run_comparison(session: Session, comparison: DocumentComparison, day_first: bool) -> dict[str, Any]:
    params = comparison.parameters_json or {}
    opts = MatchOptions(
        amount_tolerance=Decimal(str(params.get("amount_tolerance", "0.01"))),
        supplier_fuzzy_threshold=int(params.get("supplier_fuzzy_threshold", 90)),
        fuzzy_invoice_numbers=bool(params.get("fuzzy_invoice_numbers", True)),
        default_currency=to_currency_code(params.get("default_currency")),
    )
    org = comparison.organization_id
    if comparison.comparison_type == ComparisonType.PDF_PDF:
        assert comparison.left_document_id is not None
        left = _current_invoices(session, [comparison.left_document_id], params.get("left_invoice_ids"), org)
        right_invoices = _current_invoices(session, [comparison.right_document_id], params.get("right_invoice_ids"), org)
        result = match_records(left, right_invoices, opts, compare_customer=True, compare_lines=True, detect_right_duplicates=False)
        summary = {
            "matched_count": result.summary["matched_count"],
            "mismatched_count": result.summary["mismatched_count"],
            "ambiguous_count": result.summary["ambiguous_count"],
            "missing_left_count": result.summary["missing_left_count"],
            "missing_right_count": result.summary["missing_right_count"],
            "left_invoices": result.summary["left_records"],
            "right_invoices": result.summary["right_records"],
        }
    else:
        pdf_ids = [uuid.UUID(d) for d in params.get("pdf_document_ids", [])]
        left = _current_invoices(session, pdf_ids, None, org)
        sheet = session.get(Document, comparison.right_document_id)
        if sheet is None or sheet.organization_id != org:
            raise PermanentProcessingError("Spreadsheet not available", code="DOCUMENT_UNAVAILABLE")
        mapping: dict[str, str] = params.get("column_mapping", {})
        sheet_names: list[str] | None = params.get("sheet_names")
        tables = (
            session.execute(select(DocumentTable).where(DocumentTable.document_id == sheet.id, DocumentTable.page_id.is_(None)))
            .scalars()
            .all()
        )
        right: list[ComparableRecord] = []
        for table in tables:
            if sheet_names and table.sheet_name not in sheet_names:
                continue
            rows = session.execute(
                select(SpreadsheetRow)
                .where(SpreadsheetRow.table_id == table.id)
                .order_by(SpreadsheetRow.row_number)
                .execution_options(yield_per=1000)
            ).scalars()
            for row in rows:
                record = row_to_record(row, sheet, mapping, day_first)
                if record.invoice_number or record.total_amount is not None:
                    right.append(record)
        result = match_records(left, right, opts, compare_customer=False, compare_lines=False, detect_right_duplicates=True)
        summary = {
            "matched_count": result.summary["matched_count"],
            "mismatched_count": result.summary["mismatched_count"],
            "missing_left_count": result.summary["missing_left_count"],
            "missing_right_count": result.summary["missing_right_count"],
            "missing_in_pdf_count": result.summary["missing_left_count"],
            "missing_in_spreadsheet_count": result.summary["missing_right_count"],
            "ambiguous_count": result.summary["ambiguous_count"],
            "duplicate_count": result.summary["duplicate_count"],
            "pdf_invoices": result.summary["left_records"],
            "spreadsheet_rows": result.summary["right_records"],
            "rows_with_parse_notes": sum(1 for r in right if r.parse_notes),
        }

    session.execute(delete(ComparisonFinding).where(ComparisonFinding.comparison_id == comparison.id))
    for position, f in enumerate(result.findings):
        session.add(
            ComparisonFinding(
                id=uuid.uuid4(),
                comparison_id=comparison.id,
                position=position,
                record_key=f.record_key[:300] if f.record_key else None,
                field_name=f.field_name,
                left_value_json=f.left,
                right_value_json=f.right,
                difference_json=f.difference,
                status=f.status,
                evidence_json=f.evidence or {},
            )
        )
    comparison.summary_json = summary
    comparison.status = ComparisonStatus.COMPLETED
    comparison.completed_at = datetime.now(UTC)
    return summary


_FORMULA_PREFIX = re.compile(r"^[=+\-@\t\r]")
_PLAIN_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def csv_safe(value: Any) -> str:
    """Neutralize spreadsheet formula injection (OWASP CSV injection guidance)."""
    if value is None:
        return ""
    if isinstance(value, dict | list):
        import json

        text = json.dumps(value, default=str)
    else:
        text = str(value)
    if _FORMULA_PREFIX.match(text) and not _PLAIN_NUMBER.match(text):
        return "'" + text
    return text


def findings_to_csv(findings: Iterable[ComparisonFinding]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
    writer.writerow(
        ["position", "record_key", "field", "status", "left_value", "right_value", "difference", "left_reference", "right_reference"]
    )
    for f in findings:
        ev = f.evidence_json or {}
        writer.writerow(
            [
                f.position,
                csv_safe(f.record_key),
                csv_safe(f.field_name),
                f.status.value if isinstance(f.status, FindingStatus) else str(f.status),
                csv_safe(f.left_value_json),
                csv_safe(f.right_value_json),
                csv_safe(f.difference_json),
                csv_safe(ev.get("left")),
                csv_safe(ev.get("right")),
            ]
        )
    return buf.getvalue()
