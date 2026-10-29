from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAt, Timestamps, UUIDPrimaryKey
from app.core.db_types import JSON, enum_type
from app.shared.enums import ReviewActionType, ReviewTaskStatus


class ReviewTask(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "review_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            ondelete="CASCADE",
        ),
        # At most one open review task per invoice.
        Index(
            "uq_review_tasks_open_invoice",
            "invoice_record_id",
            unique=True,
            postgresql_where=text("status IN ('OPEN','IN_PROGRESS')"),
        ),
        Index("ix_review_tasks_org_status", "organization_id", "status", text("created_at")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    invoice_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoice_records.id", ondelete="CASCADE"), nullable=True)
    status: Mapped[ReviewTaskStatus] = mapped_column(enum_type(ReviewTaskStatus), default=ReviewTaskStatus.OPEN)
    reason_codes_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewAction(UUIDPrimaryKey, CreatedAt, Base):
    """Append-only record of every human review action."""

    __tablename__ = "review_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            ondelete="CASCADE",
        ),
        Index("ix_review_actions_invoice", "invoice_record_id", text("created_at")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column()
    document_id: Mapped[uuid.UUID] = mapped_column()
    invoice_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoice_records.id", ondelete="CASCADE"), nullable=True)
    review_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("review_tasks.id", ondelete="SET NULL"), nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action_type: Mapped[ReviewActionType] = mapped_column(enum_type(ReviewActionType))
    field_path: Mapped[str | None] = mapped_column(String(120), nullable=True)
    old_value_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    new_value_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    invoice_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
