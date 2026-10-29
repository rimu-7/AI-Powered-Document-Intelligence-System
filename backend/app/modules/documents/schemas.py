from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import DocumentStatus, DocumentType, FileKind, PageStatus, PageType, ScanStatus, ValidationOutcome


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    content_type: str
    file_extension: str
    file_kind: FileKind
    file_size_bytes: int
    sha256: str
    document_type: DocumentType
    classification_method: str | None
    classification_confidence: Decimal | None
    page_count: int | None
    sheet_count: int | None
    status: DocumentStatus
    scan_status: ScanStatus
    validation_outcome: ValidationOutcome | None
    review_required: bool
    current_processing_run_id: uuid.UUID | None
    uploaded_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class UploadError(BaseModel):
    code: str
    message: str


class UploadResult(BaseModel):
    filename: str
    status: Literal["accepted", "rejected"]
    document_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    status_url: str | None = None
    sha256: str | None = None
    duplicate_of_document_ids: list[uuid.UUID] = []
    error: UploadError | None = None


class UploadResponse(BaseModel):
    results: list[UploadResult]
    accepted: int
    rejected: int


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_number: int
    page_type: PageType | None
    character_count: int
    ocr_engine: str | None
    ocr_confidence: Decimal | None
    processing_status: PageStatus
    error_code: str | None
    metadata_json: dict[str, Any]


class PageText(BaseModel):
    page_number: int
    text: str
    truncated: bool = False


class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_key: str
    sheet_name: str | None
    page_number: int | None
    table_index: int
    header_row_number: int | None
    header_json: list[Any] | None
    normalized_data_json: list[Any] | None
    row_count: int
    column_count: int
    metadata_json: dict[str, Any]


class RowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    sheet_name: str | None
    cells_json: dict[str, Any]


class PresignedDownload(BaseModel):
    url: str
    expires_in: int


class DirectUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, description="Exact file size in bytes (the storage enforces it)")


class DirectUploadTicketOut(BaseModel):
    upload_id: uuid.UUID
    document_id: uuid.UUID
    upload_url: str = Field(description="Send the file here: PUT, multipart/form-data, field name 'file'")
    method: Literal["PUT"] = "PUT"
    form_field: str = "file"
    max_bytes: int
    expires_at: datetime
    complete_url: str
