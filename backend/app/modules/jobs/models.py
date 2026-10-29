from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAt, Timestamps, UUIDPrimaryKey
from app.core.db_types import JSON, enum_type, json_default
from app.shared.enums import JobType, RunState, TaskState, TaskType

NON_TERMINAL_SQL = "state NOT IN ('COMPLETED','COMPLETED_WITH_WARNINGS','REQUIRES_REVIEW','FAILED','CANCELLED')"


class ProcessingRun(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "processing_runs"
    __table_args__ = (
        Index("ix_processing_runs_org_created", "organization_id", text("created_at DESC")),
        Index("ix_processing_runs_org_state", "organization_id", "state"),
        Index("ix_processing_runs_document", "document_id", text("created_at DESC")),
        Index("ix_processing_runs_active", "updated_at", postgresql_where=text(NON_TERMINAL_SQL)),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    job_type: Mapped[JobType] = mapped_column(enum_type(JobType))
    state: Mapped[RunState] = mapped_column(enum_type(RunState), default=RunState.QUEUED)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=json_default)
    pages_total: Mapped[int] = mapped_column(Integer, default=0)
    pages_completed: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    warnings_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stage_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recovery_attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    sanitized_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stage_history_json: Mapped[list[Any]] = mapped_column(JSON, default=list)


class ProcessingTask(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "processing_tasks"
    __table_args__ = (
        Index("ix_processing_tasks_run_state", "processing_run_id", "task_state"),
        Index(
            "ix_processing_tasks_running_lease",
            "lease_expires_at",
            postgresql_where=text("task_state = 'RUNNING'"),
        ),
        Index(
            "ix_processing_tasks_pending",
            "updated_at",
            postgresql_where=text("task_state = 'PENDING'"),
        ),
    )

    processing_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_runs.id", ondelete="CASCADE"))
    task_type: Mapped[TaskType] = mapped_column(enum_type(TaskType))
    task_state: Mapped[TaskState] = mapped_column(enum_type(TaskState), default=TaskState.PENDING)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_history_json: Mapped[list[Any]] = mapped_column(JSON, default=list)


class OutboxEvent(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_unpublished",
            "available_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        Index("ix_outbox_events_published", "published_at", postgresql_where=text("published_at IS NOT NULL")),
    )

    event_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[uuid.UUID] = mapped_column()
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
