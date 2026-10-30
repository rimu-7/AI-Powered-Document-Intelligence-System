from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import Principal, SessionDep, require
from app.core.exceptions import ValidationFailedError
from app.core.permissions import Permission
from app.modules.search import service
from app.modules.search.schemas import SearchFilters, SearchRequest, SearchResponse
from app.shared.enums import CurrencyCode, DocumentStatus, DocumentType, FileKind, ValidationOutcome

router = APIRouter(prefix="/search", tags=["search"])
Searcher = Annotated[Principal, Depends(require(Permission.SEARCH))]


@router.get("/keyword", response_model=SearchResponse)
async def keyword(
    principal: Searcher,
    session: SessionDep,
    q: Annotated[str, Query(max_length=500)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
    supplier: Annotated[str | None, Query(max_length=200)] = None,
    currency: CurrencyCode | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    amount_min: str | None = None,
    amount_max: str | None = None,
    file_kind: Annotated[list[FileKind] | None, Query()] = None,
    document_type: Annotated[list[DocumentType] | None, Query()] = None,
    status: Annotated[list[DocumentStatus] | None, Query()] = None,
    validation_outcome: Annotated[list[ValidationOutcome] | None, Query()] = None,
) -> SearchResponse:
    """PostgreSQL full-text search over page text, spreadsheet rows, and invoice metadata."""
    if not q.strip():
        raise ValidationFailedError("Query must not be empty", code="EMPTY_QUERY")
    try:
        filters = SearchFilters(
            supplier=supplier,
            currency=currency,
            date_from=date_from,  # type: ignore[arg-type]
            date_to=date_to,  # type: ignore[arg-type]
            amount_min=amount_min,  # type: ignore[arg-type]
            amount_max=amount_max,  # type: ignore[arg-type]
            file_kinds=file_kind,
            document_types=document_type,
            processing_statuses=status,
            validation_outcomes=validation_outcome,
        )
    except ValueError as exc:
        raise ValidationFailedError("Invalid filter value", code="INVALID_FILTER", details=str(exc)[:500]) from exc
    return await service.keyword_search(session, principal.organization_id, q.strip(), filters, limit, offset)


@router.post("/semantic", response_model=SearchResponse)
async def semantic(body: SearchRequest, principal: Searcher, session: SessionDep) -> SearchResponse:
    """Vector similarity (pgvector HNSW, cosine). Scores are raw cosine similarities."""
    return await service.semantic_search(session, principal.organization_id, body.query, body.filters, body.limit, body.offset)


@router.post("/hybrid", response_model=SearchResponse)
async def hybrid(body: SearchRequest, principal: Searcher, session: SessionDep) -> SearchResponse:
    """Keyword + vector results fused with Reciprocal Rank Fusion (k configurable)."""
    return await service.hybrid_search(session, principal.organization_id, body.query, body.filters, body.limit, body.offset)
