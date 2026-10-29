from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.shared.enums import (
    DocumentType,
    ExtractionStatus,
    ResolutionStatus,
    ReviewStatus,
    Severity,
    ValidationOutcome,
)


class ExtractionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    processing_run_id: uuid.UUID | None
    provider: str
    model_name: str
    prompt_version: str
    schema_version: str
    extraction_revision: int
    status: ExtractionStatus
    error_code: str | None
    usage_json: dict[str, Any]
    created_at: datetime


class ExtractionRunDetail(ExtractionRunOut):
    normalized_result_json: dict[str, Any]


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    discount_amount: Decimal | None
    tax_rate: Decimal | None
    tax_amount: Decimal | None
    line_total: Decimal | None
    source_evidence_json: dict[str, Any]


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    extraction_run_id: uuid.UUID
    segment_index: int
    page_start: int | None
    page_end: int | None
    document_type: DocumentType
    invoice_number: str | None
    invoice_date: date | None
    invoice_date_raw: str | None
    payment_due_date: date | None
    supplier_name: str | None
    supplier_tax_id: str | None
    supplier_address: str | None
    customer_name: str | None
    customer_address: str | None
    purchase_order_number: str | None
    payment_reference: str | None
    currency: str | None
    currency_raw: str | None
    subtotal: Decimal | None
    discount_amount: Decimal | None
    shipping_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    amounts_tax_inclusive: bool | None
    extraction_confidence: Decimal | None
    extraction_status: ExtractionStatus
    validation_outcome: ValidationOutcome | None
    review_status: ReviewStatus
    corrected_fields_json: list[Any]
    field_support_json: dict[str, Any]
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class InvoiceDetail(InvoiceOut):
    source_evidence_json: dict[str, Any]
    alternatives_json: dict[str, Any]
    line_items: list[LineItemOut]
    machine_values: dict[str, Any] | None = None


class ValidationIssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    invoice_record_id: uuid.UUID | None
    validation_run_id: uuid.UUID | None
    rule_code: str
    severity: Severity
    field_path: str | None
    expected_value_json: Any | None
    actual_value_json: Any | None
    source_evidence_json: dict[str, Any]
    details_json: dict[str, Any]
    message: str
    resolution_status: ResolutionStatus
    created_at: datetime
    resolved_at: datetime | None
