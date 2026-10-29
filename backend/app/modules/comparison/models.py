from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAt, UUIDPrimaryKey
from app.core.db_types import JSON, enum_type, json_default
from app.shared.enums import ComparisonStatus, ComparisonType, FindingStatus


class DocumentComparison(UUIDPrimaryKey, CreatedAt, Base):
    """A PDF-to-PDF comparison or a PDF-to-spreadsheet reconciliation."""

    __tablename__ = "document_comparisons"
    __table_args__ = (Index("ix_document_comparisons_org_created", "organization_id", text("created_at DESC")),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    left_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    right_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    comparison_type: Mapped[ComparisonType] = mapped_column(enum_type(ComparisonType))
    matching_strategy: Mapped[str] = mapped_column(String(60))
    status: Mapped[ComparisonStatus] = mapped_column(enum_type(ComparisonStatus), default=ComparisonStatus.QUEUED)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    processing_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ComparisonDocument(Base):
    """All documents participating in a comparison (used for staleness tracking)."""

    __tablename__ = "comparison_documents"

    comparison_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_comparisons.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True, index=True)
    side: Mapped[str] = mapped_column(String(10))


class ComparisonFinding(UUIDPrimaryKey, Base):
    __tablename__ = "comparison_findings"
    __table_args__ = (
        UniqueConstraint("comparison_id", "position"),
        Index("ix_comparison_findings_status", "comparison_id", "status"),
    )

    comparison_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_comparisons.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    record_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    field_name: Mapped[str] = mapped_column(String(80))
    left_value_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    right_value_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    difference_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[FindingStatus] = mapped_column(enum_type(FindingStatus))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
