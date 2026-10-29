"""Chunking and (re)indexing of a document into ``document_chunks`` (sync, workers).

* Page text is split into bounded chunks on line boundaries with overlap.
* Spreadsheet rows are grouped into chunks with sheet/row-range references.
* One metadata chunk per document carries filename, type, supplier, customer,
  invoice numbers and line-item descriptions, so those fields are searchable
  through the same full-text and vector indexes.
Re-indexing replaces all chunks of a document in one transaction.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.documents.models import Document, DocumentChunk, DocumentPage, DocumentTable, SpreadsheetRow
from app.modules.extraction.models import InvoiceLineItem, InvoiceRecord
from app.modules.search.embeddings import EmbeddingProvider
from app.shared.enums import PageStatus


@dataclass
class ChunkDraft:
    text: str
    kind: str
    page_id: uuid.UUID | None
    page_number: int | None
    source: dict[str, Any]


def chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            cut = text.rfind("\n", start + max_chars // 2, end)
            if cut == -1:
                cut = text.rfind(" ", start + max_chars // 2, end)
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _page_chunks(session: Session, document: Document) -> Iterator[ChunkDraft]:
    settings = get_settings()
    pages = session.execute(
        select(DocumentPage.id, DocumentPage.page_number, DocumentPage.extracted_text)
        .where(DocumentPage.document_id == document.id, DocumentPage.processing_status == PageStatus.DONE)
        .order_by(DocumentPage.page_number)
        .execution_options(yield_per=50)
    )
    for page_id, page_number, text in pages:
        for i, piece in enumerate(chunk_text(text or "", settings.chunk_max_chars, settings.chunk_overlap_chars)):
            yield ChunkDraft(
                piece, "page", page_id, page_number, {"document_id": str(document.id), "page_number": page_number, "chunk_in_page": i}
            )


def _row_chunks(session: Session, document: Document, rows_per_chunk: int = 25) -> Iterator[ChunkDraft]:
    tables = (
        session.execute(select(DocumentTable).where(DocumentTable.document_id == document.id, DocumentTable.page_id.is_(None)))
        .scalars()
        .all()
    )
    for table in tables:
        rows = session.execute(
            select(SpreadsheetRow.row_number, SpreadsheetRow.cells_json)
            .where(SpreadsheetRow.table_id == table.id)
            .order_by(SpreadsheetRow.row_number)
            .execution_options(yield_per=500)
        )
        batch: list[tuple[int, dict[str, Any]]] = []
        for row_number, cells in rows:
            batch.append((row_number, cells))
            if len(batch) >= rows_per_chunk:
                yield _rows_draft(document, table, batch)
                batch = []
        if batch:
            yield _rows_draft(document, table, batch)


def _rows_draft(document: Document, table: DocumentTable, batch: list[tuple[int, dict[str, Any]]]) -> ChunkDraft:
    lines = []
    for row_number, cells in batch:
        values = "; ".join(f"{k}: {v.get('v')}" for k, v in cells.items() if v.get("v"))
        lines.append(f"row {row_number}: {values}")
    return ChunkDraft(
        "\n".join(lines),
        "rows",
        None,
        None,
        {
            "document_id": str(document.id),
            "sheet_name": table.sheet_name,
            "row_start": batch[0][0],
            "row_end": batch[-1][0],
        },
    )


def _metadata_chunk(session: Session, document: Document) -> ChunkDraft:
    parts = [f"filename: {document.original_filename}", f"document type: {document.document_type.value}"]
    invoices = (
        session.execute(select(InvoiceRecord).where(InvoiceRecord.document_id == document.id, InvoiceRecord.superseded_at.is_(None)))
        .scalars()
        .all()
    )
    for inv in invoices:
        fields = [
            ("invoice number", inv.invoice_number),
            ("supplier", inv.supplier_name),
            ("customer", inv.customer_name),
            ("invoice date", inv.invoice_date.isoformat() if inv.invoice_date else None),
            ("currency", inv.currency),
            ("total", format(inv.total_amount, "f") if inv.total_amount is not None else None),
        ]
        parts.append(" | ".join(f"{k}: {v}" for k, v in fields if v))
        descriptions = (
            session.execute(
                select(InvoiceLineItem.description)
                .where(InvoiceLineItem.invoice_record_id == inv.id)
                .order_by(InvoiceLineItem.position)
                .limit(200)
            )
            .scalars()
            .all()
        )
        if descriptions:
            parts.append("items: " + "; ".join(d for d in descriptions if d))
    return ChunkDraft("\n".join(parts)[:8000], "metadata", None, None, {"document_id": str(document.id), "kind": "metadata"})


def index_document(session: Session, document: Document, embedder: EmbeddingProvider) -> int:
    """Rebuild all chunks of a document. Caller owns the transaction."""
    settings = get_settings()
    drafts: list[ChunkDraft] = [_metadata_chunk(session, document)]
    drafts.extend(_page_chunks(session, document))
    drafts.extend(_row_chunks(session, document))

    session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    batch_size = settings.embedding_batch_size
    for start in range(0, len(drafts), batch_size):
        batch = drafts[start : start + batch_size]
        vectors = embedder.embed([d.text for d in batch])
        for offset, (draft, vector) in enumerate(zip(batch, vectors, strict=True)):
            session.add(
                DocumentChunk(
                    id=uuid.uuid4(),
                    organization_id=document.organization_id,
                    document_id=document.id,
                    page_id=draft.page_id,
                    page_number=draft.page_number,
                    chunk_index=start + offset,
                    chunk_kind=draft.kind,
                    text=draft.text,
                    source_reference_json=draft.source,
                    embedding=vector,
                    embedding_model=embedder.model,
                )
            )
        session.flush()
    return len(drafts)
