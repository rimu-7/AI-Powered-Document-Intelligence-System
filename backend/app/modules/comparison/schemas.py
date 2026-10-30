from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enums import ComparisonStatus, ComparisonType, CurrencyCode, FindingStatus


class ComparisonOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_tolerance: Decimal = Field(default=Decimal("0.01"), ge=0, le=Decimal("100"), description="Absolute tolerance in currency units")
    supplier_fuzzy_threshold: int = Field(default=90, ge=70, le=100)
    fuzzy_invoice_numbers: bool = True
    default_currency: CurrencyCode | None = Field(default=None, description="Explicit policy: currency assumed for records that state none")


class ComparisonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_document_id: uuid.UUID
    right_document_id: uuid.UUID
    comparison_type: ComparisonType = ComparisonType.PDF_PDF
    left_invoice_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    right_invoice_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    options: ComparisonOptions = Field(default_factory=ComparisonOptions)

    @model_validator(mode="after")
    def _check(self) -> ComparisonCreate:
        if self.comparison_type != ComparisonType.PDF_PDF:
            raise ValueError("Use POST /reconciliations for PDF-to-spreadsheet reconciliation")
        if self.left_document_id == self.right_document_id:
            raise ValueError("left and right documents must differ")
        return self


class ReconciliationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pdf_document_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    spreadsheet_document_id: uuid.UUID
    column_mapping: dict[str, str] | None = Field(
        default=None, description="invoice field → spreadsheet header; suggestions are used when omitted"
    )
    sheet_names: list[str] | None = Field(default=None, max_length=50)
    options: ComparisonOptions = Field(default_factory=ComparisonOptions)


class ComparedDocument(BaseModel):
    id: uuid.UUID
    side: str = Field(description="left (PDF side) or right (second PDF or spreadsheet)")
    filename: str
    file_kind: str
    deleted: bool = False


class ComparisonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    comparison_type: ComparisonType
    left_document_id: uuid.UUID | None
    right_document_id: uuid.UUID
    matching_strategy: str
    status: ComparisonStatus
    parameters_json: dict[str, Any]
    summary_json: dict[str, Any]
    processing_run_id: uuid.UUID | None
    stale_reason: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None
    documents: list[ComparedDocument] = Field(default_factory=list)
    error_message: str | None = Field(default=None, description="Why the run failed, when status is FAILED")


class ComparisonAccepted(BaseModel):
    comparison_id: uuid.UUID
    job_id: uuid.UUID
    status_url: str
    column_mapping: dict[str, str] | None = None


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    record_key: str | None
    field_name: str
    status: FindingStatus
    left_value_json: Any | None
    right_value_json: Any | None
    difference_json: Any | None
    evidence_json: dict[str, Any]
