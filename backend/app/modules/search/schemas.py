from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.enums import DocumentStatus, DocumentType, FileKind, ValidationOutcome


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date | None = None
    date_to: date | None = None
    supplier: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    file_kinds: list[FileKind] | None = Field(default=None, max_length=10)
    document_types: list[DocumentType] | None = Field(default=None, max_length=10)
    processing_statuses: list[DocumentStatus] | None = Field(default=None, max_length=10)
    validation_outcomes: list[ValidationOutcome] | None = Field(default=None, max_length=10)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1000)

    @field_validator("query")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be blank")
        return v.strip()


class SourceReference(BaseModel):
    document_id: uuid.UUID
    page_number: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    chunk_kind: str


class SearchHit(BaseModel):
    document_id: uuid.UUID
    filename: str
    document_type: DocumentType
    snippet: str
    matched_pages: list[int]
    score: float = Field(description="Ranking score; meaning depends on score_kind (not a percentage)")
    score_kind: Literal["ts_rank_cd", "cosine_similarity", "rrf"]
    match_type: Literal["keyword", "semantic", "hybrid"]
    source_reference: SourceReference


class SearchResponse(BaseModel):
    items: list[SearchHit]
    total: int
    limit: int
    offset: int
    mode: Literal["keyword", "semantic", "hybrid"]
    candidate_limit: int | None = None
    embedding_model: str | None = None
