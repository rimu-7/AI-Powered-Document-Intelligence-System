from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.extraction.api_schemas import InvoiceDetail, InvoiceOut, ValidationIssueOut
from app.shared.enums import ReviewActionType, ReviewTaskStatus


class FieldChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str = Field(
        max_length=120,
        description="e.g. 'total_amount', 'line_items[0].quantity', 'line_items[]' (append), 'line_items[2]' with null (remove)",
    )
    value: str | bool | dict[str, Any] | None = Field(description="Amounts as decimal strings, dates as YYYY-MM-DD")


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)
    changes: list[FieldChange] = Field(min_length=1, max_length=100)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)
    acknowledge_issues: bool = False


class RejectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)


class ReviewActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_record_id: uuid.UUID | None
    review_task_id: uuid.UUID | None
    reviewer_id: uuid.UUID | None
    action_type: ReviewActionType
    field_path: str | None
    old_value_json: Any | None
    new_value_json: Any | None
    reason: str | None
    invoice_version: int | None
    created_at: datetime


class ReviewTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    invoice_record_id: uuid.UUID | None
    status: ReviewTaskStatus
    reason_codes_json: list[Any]
    assigned_to: uuid.UUID | None
    assigned_at: datetime | None
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReviewQueueItem(ReviewTaskOut):
    invoice: InvoiceOut | None
    document_filename: str
    open_issue_count: int


class ReviewDetail(ReviewTaskOut):
    invoice: InvoiceDetail | None
    issues: list[ValidationIssueOut]
    history: list[ReviewActionOut]


class CorrectionResponse(BaseModel):
    invoice: InvoiceDetail
    revalidation_job_id: uuid.UUID
    status_url: str
    stale_comparisons: int
