from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import FileKind, JobType, RunState, TaskState, TaskType


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_type: TaskType
    task_state: TaskState
    page_start: int | None
    page_end: int | None
    attempt_count: int
    last_error_code: str | None
    last_error_message: str | None
    error_history_json: list[Any]
    started_at: datetime | None
    completed_at: datetime | None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID | None
    job_type: JobType
    state: RunState
    attempt_number: int
    parent_run_id: uuid.UUID | None
    pages_total: int
    pages_completed: int
    pages_failed: int
    progress_percent: Decimal
    started_at: datetime | None
    completed_at: datetime | None
    stage_started_at: datetime | None
    error_code: str | None
    sanitized_error_message: str | None
    created_at: datetime
    updated_at: datetime


class JobDetail(JobOut):
    stage_history_json: list[Any]
    tasks_by_state: dict[str, int]
    failed_tasks: list[TaskOut]


class JobAccepted(BaseModel):
    job_id: uuid.UUID
    status_url: str
    state: RunState


class ActiveJobOut(BaseModel):
    """A document being processed, or one that finished moments ago."""

    job_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    file_kind: FileKind
    state: RunState
    pages_total: int
    pages_completed: int
    pages_failed: int
    progress_percent: Decimal
    created_at: datetime
    completed_at: datetime | None
    sanitized_error_message: str | None
    invoices: int = Field(description="Invoices extracted so far")
    open_reviews: int = Field(description="Invoices from this document waiting for a reviewer")
