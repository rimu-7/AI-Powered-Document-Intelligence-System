"""Document, page, table, spreadsheet-row and storage-object models.

Tenant consistency: child tables carry ``organization_id`` and reference
``documents (organization_id, id)`` through a composite foreign key, so a row
can never point at a document that belongs to another organization.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAt, Timestamps, UUIDPrimaryKey
from app.core.db_types import JSON, RATIO, enum_type, json_default
from app.shared.enums import (
    DocumentStatus,
    DocumentType,
    FileKind,
    PageStatus,
    PageType,
    ScanStatus,
    StorageCategory,
    StorageObjectStatus,
    ValidationOutcome,
)

EMBEDDING_DIMENSIONS = 1024


def doc_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", "document_id"],
        ["documents.organization_id", "documents.id"],
        ondelete="CASCADE",
    )


class Document(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_documents_org_id"),
        Index(
            "ix_documents_org_created",
            "organization_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_documents_org_status",
            "organization_id",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_documents_org_sha256", "organization_id", "sha256"),
        Index("ix_documents_deleted_at", "deleted_at", postgresql_where=text("deleted_at IS NOT NULL")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    file_extension: Mapped[str] = mapped_column(String(10))
    file_kind: Mapped[FileKind] = mapped_column(enum_type(FileKind))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    document_type: Mapped[DocumentType] = mapped_column(enum_type(DocumentType), default=DocumentType.UNKNOWN)
    classification_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    classification_confidence: Mapped[Decimal | None] = mapped_column(RATIO, nullable=True)
    classification_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(enum_type(DocumentStatus), default=DocumentStatus.UPLOADED)
    scan_status: Mapped[ScanStatus] = mapped_column(enum_type(ScanStatus), default=ScanStatus.PENDING)
    validation_outcome: Mapped[ValidationOutcome | None] = mapped_column(enum_type(ValidationOutcome), nullable=True)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    current_processing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentPage(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        doc_fk(),
        UniqueConstraint("document_id", "page_number"),
        Index("ix_document_pages_doc_status", "document_id", "processing_status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    page_number: Mapped[int] = mapped_column(Integer)
    page_type: Mapped[PageType | None] = mapped_column(enum_type(PageType), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    layout_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    ocr_engine: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ocr_confidence: Mapped[Decimal | None] = mapped_column(RATIO, nullable=True)
    processing_status: Mapped[PageStatus] = mapped_column(enum_type(PageStatus), default=PageStatus.PENDING)
    parser_version: Mapped[str] = mapped_column(String(20), default="1")
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)


class DocumentTable(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "document_tables"
    __table_args__ = (
        doc_fk(),
        UniqueConstraint("document_id", "source_key", "table_index"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=True)
    source_key: Mapped[str] = mapped_column(String(300))
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_index: Mapped[int] = mapped_column(Integer)
    header_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    header_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    normalized_data_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    data_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)


class SpreadsheetRow(UUIDPrimaryKey, Base):
    """One data row of a spreadsheet/CSV table, with its exact source coordinates."""

    __tablename__ = "spreadsheet_rows"
    __table_args__ = (
        doc_fk(),
        UniqueConstraint("table_id", "row_number"),
        Index("ix_spreadsheet_rows_doc", "document_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_tables.id", ondelete="CASCADE"))
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_number: Mapped[int] = mapped_column(Integer)
    cells_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class DocumentChunk(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        doc_fk(),
        UniqueConstraint("document_id", "chunk_index"),
        Index("ix_document_chunks_org_doc", "organization_id", "document_id"),
        Index("ix_document_chunks_tsv", "text_tsv", postgresql_using="gin"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_kind: Mapped[str] = mapped_column(String(20), default="page")
    text: Mapped[str] = mapped_column(Text)
    text_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english'::regconfig, text) || to_tsvector('simple'::regconfig, text)",
            persisted=True,
        ),
    )
    source_reference_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(80), nullable=True)


class StorageObject(UUIDPrimaryKey, CreatedAt, Base):
    """Every object written to storage, so cleanup and quotas are exact."""

    __tablename__ = "storage_objects"
    __table_args__ = (
        UniqueConstraint("bucket", "key"),
        Index("ix_storage_objects_org_doc", "organization_id", "document_id"),
        Index(
            "ix_storage_objects_pending",
            "created_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    category: Mapped[StorageCategory] = mapped_column(enum_type(StorageCategory))
    bucket: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[StorageObjectStatus] = mapped_column(enum_type(StorageObjectStatus), default=StorageObjectStatus.PENDING)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default, server_default=text("'{}'::jsonb"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdempotencyRecord(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "endpoint", "key"),
        Index("ix_idempotency_records_expires", "expires_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
