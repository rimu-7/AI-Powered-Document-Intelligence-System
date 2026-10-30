from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAt, Timestamps, UUIDPrimaryKey
from app.core.db_types import JSON, MONEY, QUANTITY, RATIO, UNIT_PRICE, enum_type, json_default
from app.shared.enums import CurrencyCode, CurrencySource, DocumentType, ExtractionStatus, ReviewStatus, ValidationOutcome


def _doc_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", "document_id"],
        ["documents.organization_id", "documents.id"],
        ondelete="CASCADE",
    )


class ExtractionRun(UUIDPrimaryKey, CreatedAt, Base):
    """Immutable record of one extraction attempt over a document."""

    __tablename__ = "extraction_runs"
    __table_args__ = (
        _doc_fk(),
        UniqueConstraint("document_id", "extraction_revision"),
        UniqueConstraint("processing_run_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    processing_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str] = mapped_column(String(60))
    model_name: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(60))
    schema_version: Mapped[str] = mapped_column(String(20))
    extraction_revision: Mapped[int] = mapped_column(Integer)
    raw_result_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    normalized_result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    status: Mapped[ExtractionStatus] = mapped_column(enum_type(ExtractionStatus))
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)


class InvoiceRecord(UUIDPrimaryKey, Timestamps, Base):
    """Current (machine or human-corrected) values of one invoice in a document.

    Machine values are preserved immutably in ``extraction_runs`` and every
    human change is recorded in ``review_actions``.
    """

    __tablename__ = "invoice_records"
    __table_args__ = (
        _doc_fk(),
        UniqueConstraint("organization_id", "id", name="uq_invoice_records_org_id"),
        UniqueConstraint("extraction_run_id", "segment_index"),
        Index(
            "ix_invoice_records_dup_key",
            "organization_id",
            "normalized_supplier",
            "normalized_invoice_number",
            postgresql_where=text("superseded_at IS NULL"),
        ),
        Index(
            "ix_invoice_records_doc_current",
            "document_id",
            postgresql_where=text("superseded_at IS NULL"),
        ),
        Index(
            "ix_invoice_records_org_review",
            "organization_id",
            "review_status",
            postgresql_where=text("superseded_at IS NULL"),
        ),
        Index("ix_invoice_records_org_date", "organization_id", "invoice_date"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extraction_runs.id", ondelete="CASCADE"))
    segment_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_type: Mapped[DocumentType] = mapped_column(enum_type(DocumentType), default=DocumentType.INVOICE)
    invoice_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    normalized_invoice_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    invoice_date_raw: Mapped[str | None] = mapped_column(String(60), nullable=True)
    payment_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    normalized_supplier: Mapped[str | None] = mapped_column(String(300), nullable=True)
    supplier_tax_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    supplier_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    customer_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchase_order_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    currency: Mapped[CurrencyCode | None] = mapped_column(enum_type(CurrencyCode, length=3), nullable=True)
    currency_raw: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency_source: Mapped[CurrencySource | None] = mapped_column(enum_type(CurrencySource), nullable=True)
    subtotal: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    shipping_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    amounts_tax_inclusive: Mapped[bool | None] = mapped_column(nullable=True)
    extraction_confidence: Mapped[Decimal | None] = mapped_column(RATIO, nullable=True)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(enum_type(ExtractionStatus))
    field_support_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    source_evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    alternatives_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    validation_outcome: Mapped[ValidationOutcome | None] = mapped_column(enum_type(ValidationOutcome), nullable=True)
    review_status: Mapped[ReviewStatus] = mapped_column(enum_type(ReviewStatus), default=ReviewStatus.NOT_REQUIRED)
    corrected_fields_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}

    @property
    def currency_reason(self) -> str | None:
        """Why the currency was chosen automatically (None when printed or set by hand)."""
        ev = (self.source_evidence_json or {}).get("currency")
        return ev.get("reason") if isinstance(ev, dict) else None

    @property
    def currency_suggestions(self) -> list[str]:
        """Candidate currencies for an unresolved symbol, most likely first."""
        alts = (self.alternatives_json or {}).get("alternatives", {}).get("currency")
        return [str(c) for c in alts] if isinstance(alts, list) else []


class InvoiceLineItem(UUIDPrimaryKey, Base):
    __tablename__ = "invoice_line_items"
    __table_args__ = (UniqueConstraint("invoice_record_id", "position"),)

    invoice_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoice_records.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(QUANTITY, nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(UNIT_PRICE, nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    tax_rate: Mapped[Decimal | None] = mapped_column(RATIO, nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    line_total: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    source_evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
