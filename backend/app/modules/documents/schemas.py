from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    page_width: float | None = None
    page_height: float | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_dimensions(cls, data: Any) -> Any:
        if isinstance(data, dict):
            meta = data.get("metadata_json") or {}
            if data.get("page_width") is None:
                val = meta.get("width") or meta.get("page_width")
                data["page_width"] = float(val) if val is not None else None
            if data.get("page_height") is None:
                val = meta.get("height") or meta.get("page_height")
                data["page_height"] = float(val) if val is not None else None
            return data
        elif hasattr(data, "metadata_json"):
            meta = getattr(data, "metadata_json", {}) or {}
            w = getattr(data, "page_width", None)
            h = getattr(data, "page_height", None)
            if w is None and isinstance(meta, dict):
                w = meta.get("width") or meta.get("page_width")
            if h is None and isinstance(meta, dict):
                h = meta.get("height") or meta.get("page_height")
            d = {k: getattr(data, k) for k in (
                "id", "page_number", "page_type", "character_count",
                "ocr_engine", "ocr_confidence", "processing_status",
                "error_code", "metadata_json"
            ) if hasattr(data, k)}
            d["page_width"] = float(w) if w is not None else None
            d["page_height"] = float(h) if h is not None else None
            return d
        return data


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
