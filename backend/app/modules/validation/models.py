from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAt, UUIDPrimaryKey
from app.core.db_types import JSON, enum_type, json_default
from app.shared.enums import ResolutionStatus, Severity


class ValidationIssue(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "validation_issues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            ondelete="CASCADE",
        ),
        Index(
            "ix_validation_issues_doc_open",
            "document_id",
            postgresql_where=text("resolution_status = 'OPEN'"),
        ),
        Index("ix_validation_issues_invoice", "invoice_record_id"),
        Index("ix_validation_issues_run", "validation_run_id"),
        Index("ix_validation_issues_org_rule", "organization_id", "rule_code"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    invoice_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoice_records.id", ondelete="CASCADE"), nullable=True)
    validation_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True)
    rule_code: Mapped[str] = mapped_column(String(60))
    severity: Mapped[Severity] = mapped_column(enum_type(Severity))
    field_path: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expected_value_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    actual_value_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    source_evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    message: Mapped[str] = mapped_column(String(1000))
    resolution_status: Mapped[ResolutionStatus] = mapped_column(enum_type(ResolutionStatus), default=ResolutionStatus.OPEN)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
