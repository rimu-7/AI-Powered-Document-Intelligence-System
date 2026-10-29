"""Tenant-scoped keyword, semantic and hybrid search.

Tenant isolation is enforced in SQL (``organization_id = :org`` inside every
candidate query), so another organization's chunks never enter a candidate set.

Approximate vector search: HNSW returns approximate neighbours. With a WHERE
filter, PostgreSQL may otherwise return fewer than ``k`` rows; pgvector 0.8's
iterative index scan (``hnsw.iterative_scan = relaxed_order``) keeps scanning
until enough filtered rows are found. Results are re-sorted by exact distance.
Semantic pagination covers the top ``search_candidate_limit`` chunks only.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import anyio
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.metrics import SEARCH_DURATION
from app.modules.documents.models import EMBEDDING_DIMENSIONS
from app.modules.search.embeddings import get_embedding_provider
from app.modules.search.schemas import SearchFilters, SearchHit, SearchResponse, SourceReference
from app.shared.enums import DocumentType


def _filters_sql(filters: SearchFilters, params: dict[str, Any]) -> str:
    clauses: list[str] = []
    if filters.file_kinds:
        clauses.append("d.file_kind = ANY(:f_kinds)")
        params["f_kinds"] = [k.value for k in filters.file_kinds]
    if filters.document_types:
        clauses.append("d.document_type = ANY(:f_types)")
        params["f_types"] = [t.value for t in filters.document_types]
    if filters.processing_statuses:
        clauses.append("d.status = ANY(:f_status)")
        params["f_status"] = [s.value for s in filters.processing_statuses]
    if filters.validation_outcomes:
        clauses.append("d.validation_outcome = ANY(:f_outcomes)")
        params["f_outcomes"] = [o.value for o in filters.validation_outcomes]
    inv: list[str] = []
    if filters.date_from:
        inv.append("i.invoice_date >= :f_date_from")
        params["f_date_from"] = filters.date_from
    if filters.date_to:
        inv.append("i.invoice_date <= :f_date_to")
        params["f_date_to"] = filters.date_to
    if filters.supplier:
        inv.append("i.supplier_name ILIKE :f_supplier")
        params["f_supplier"] = "%" + filters.supplier.replace("%", r"\%").replace("_", r"\_") + "%"
    if filters.currency:
        inv.append("i.currency = :f_currency")
        params["f_currency"] = filters.currency
    if filters.amount_min is not None:
        inv.append("i.total_amount >= :f_amin")
        params["f_amin"] = filters.amount_min
    if filters.amount_max is not None:
        inv.append("i.total_amount <= :f_amax")
        params["f_amax"] = filters.amount_max
    if inv:
        clauses.append(
            "EXISTS (SELECT 1 FROM invoice_records i WHERE i.document_id = d.id "
            "AND i.organization_id = d.organization_id AND i.superseded_at IS NULL AND " + " AND ".join(inv) + ")"
        )
    return "".join(f" AND {c}" for c in clauses)


_TSQUERY = "(websearch_to_tsquery('english'::regconfig, :q) || websearch_to_tsquery('simple'::regconfig, :q))"


@dataclass
class _DocHit:
    document_id: uuid.UUID
    filename: str
    document_type: str
    score: float
    pages: list[int]
    best_chunk_id: uuid.UUID
    snippet: str = ""
    source: dict[str, Any] | None = None
    chunk_kind: str = "page"


async def _keyword_docs(
    session: AsyncSession, org_id: uuid.UUID, q: str, filters: SearchFilters, limit: int, offset: int
) -> tuple[list[_DocHit], int]:
    params: dict[str, Any] = {"org": org_id, "q": q, "limit": limit, "offset": offset}
    where = _filters_sql(filters, params)
    sql = text(
        f"""
        WITH matches AS (
            SELECT c.id, c.document_id, c.page_number, ts_rank_cd(c.text_tsv, {_TSQUERY}) AS rank
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id AND d.organization_id = c.organization_id
            WHERE c.organization_id = :org AND d.organization_id = :org
              AND d.deleted_at IS NULL AND c.text_tsv @@ {_TSQUERY} {where}
        ), per_doc AS (
            SELECT document_id,
                   max(rank) AS score,
                   array_remove(array_agg(DISTINCT page_number), NULL) AS pages,
                   (array_agg(id ORDER BY rank DESC, id))[1] AS best_chunk
            FROM matches GROUP BY document_id
        )
        SELECT p.document_id, d.original_filename, d.document_type, p.score, p.pages, p.best_chunk,
               count(*) OVER () AS total
        FROM per_doc p JOIN documents d ON d.id = p.document_id
        ORDER BY p.score DESC, p.document_id
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (await session.execute(sql, params)).all()
    total = int(rows[0].total) if rows else 0
    hits = [_DocHit(r.document_id, r.original_filename, r.document_type, float(r.score), sorted(r.pages or []), r.best_chunk) for r in rows]
    if not rows and offset > 0:
        count = await session.execute(
            text(
                f"SELECT count(DISTINCT c.document_id) FROM document_chunks c JOIN documents d ON d.id = c.document_id WHERE c.organization_id = :org AND d.deleted_at IS NULL AND c.text_tsv @@ {_TSQUERY} {where}"
            ),
            params,
        )
        total = int(count.scalar_one())
    return hits, total


async def _snippets(session: AsyncSession, org_id: uuid.UUID, hits: list[_DocHit], q: str | None) -> None:
    if not hits:
        return
    ids = [h.best_chunk_id for h in hits]
    if q:
        sql = text(
            f"""SELECT id, chunk_kind, source_reference_json,
                ts_headline('simple', text, {_TSQUERY}, 'MaxFragments=2,MaxWords=30,MinWords=8,StartSel=«,StopSel=»') AS snippet
                FROM document_chunks WHERE organization_id = :org AND id = ANY(:ids)"""
        )
        params: dict[str, Any] = {"org": org_id, "ids": ids, "q": q}
    else:
        sql = text(
            "SELECT id, chunk_kind, source_reference_json, left(text, 300) AS snippet FROM document_chunks WHERE organization_id = :org AND id = ANY(:ids)"
        )
        params = {"org": org_id, "ids": ids}
    by_id = {r.id: r for r in (await session.execute(sql, params)).all()}
    for hit in hits:
        row = by_id.get(hit.best_chunk_id)
        if row is not None:
            hit.snippet = row.snippet
            hit.source = row.source_reference_json
            hit.chunk_kind = row.chunk_kind


async def _vector_candidates(
    session: AsyncSession, org_id: uuid.UUID, query: str, filters: SearchFilters, candidates: int
) -> list[tuple[uuid.UUID, uuid.UUID, int | None, float, str, str]]:
    settings = get_settings()
    embedder = get_embedding_provider()
    vector = (await anyio.to_thread.run_sync(embedder.embed, [query]))[0]
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {int(max(settings.search_hnsw_ef_search, candidates))}"))
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    params: dict[str, Any] = {"org": org_id, "vec": vector, "model": embedder.model, "cand": candidates}
    where = _filters_sql(filters, params)
    sql = text(
        f"""
        WITH nn AS MATERIALIZED (
            SELECT c.id, c.document_id, c.page_number, c.embedding <=> :vec AS distance
            FROM document_chunks c
            WHERE c.organization_id = :org AND c.embedding_model = :model AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> :vec
            LIMIT :cand
        )
        SELECT nn.id, nn.document_id, nn.page_number, nn.distance, d.original_filename, d.document_type
        FROM nn JOIN documents d ON d.id = nn.document_id
        WHERE d.organization_id = :org AND d.deleted_at IS NULL {where}
        ORDER BY nn.distance, nn.id
        """
    ).bindparams(bindparam("vec", type_=Vector(EMBEDDING_DIMENSIONS)))
    rows = (await session.execute(sql, params)).all()
    return [(r.id, r.document_id, r.page_number, float(r.distance), r.original_filename, r.document_type) for r in rows]


def _aggregate_vector(rows: list[tuple[uuid.UUID, uuid.UUID, int | None, float, str, str]]) -> list[_DocHit]:
    docs: dict[uuid.UUID, _DocHit] = {}
    for chunk_id, doc_id, page, distance, filename, doc_type in rows:
        similarity = 1.0 - distance
        hit = docs.get(doc_id)
        if hit is None:
            docs[doc_id] = _DocHit(doc_id, filename, doc_type, similarity, [page] if page else [], chunk_id)
        else:
            if page and page not in hit.pages:
                hit.pages.append(page)
    for hit in docs.values():
        hit.pages.sort()
    return sorted(docs.values(), key=lambda h: (-h.score, str(h.document_id)))


def _to_hit(h: _DocHit, kind: str, match_type: str) -> SearchHit:
    src = h.source or {}
    return SearchHit(
        document_id=h.document_id,
        filename=h.filename,
        document_type=DocumentType(h.document_type),
        snippet=(h.snippet or "")[:600],
        matched_pages=h.pages[:50],
        score=round(h.score, 6),
        score_kind=kind,  # type: ignore[arg-type]
        match_type=match_type,  # type: ignore[arg-type]
        source_reference=SourceReference(
            document_id=h.document_id,
            page_number=src.get("page_number"),
            sheet_name=src.get("sheet_name"),
            row_start=src.get("row_start"),
            row_end=src.get("row_end"),
            chunk_kind=h.chunk_kind,
        ),
    )


async def keyword_search(
    session: AsyncSession, org_id: uuid.UUID, q: str, filters: SearchFilters, limit: int, offset: int
) -> SearchResponse:
    started = time.perf_counter()
    hits, total = await _keyword_docs(session, org_id, q, filters, limit, offset)
    await _snippets(session, org_id, hits, q)
    SEARCH_DURATION.labels("keyword").observe(time.perf_counter() - started)
    return SearchResponse(
        items=[_to_hit(h, "ts_rank_cd", "keyword") for h in hits], total=total, limit=limit, offset=offset, mode="keyword"
    )


async def semantic_search(
    session: AsyncSession, org_id: uuid.UUID, q: str, filters: SearchFilters, limit: int, offset: int
) -> SearchResponse:
    started = time.perf_counter()
    settings = get_settings()
    rows = await _vector_candidates(session, org_id, q, filters, settings.search_candidate_limit)
    docs = _aggregate_vector(rows)
    page = docs[offset : offset + limit]
    await _snippets(session, org_id, page, None)
    SEARCH_DURATION.labels("semantic").observe(time.perf_counter() - started)
    return SearchResponse(
        items=[_to_hit(h, "cosine_similarity", "semantic") for h in page],
        total=len(docs),
        limit=limit,
        offset=offset,
        mode="semantic",
        candidate_limit=settings.search_candidate_limit,
        embedding_model=get_embedding_provider().model,
    )


async def hybrid_search(
    session: AsyncSession, org_id: uuid.UUID, q: str, filters: SearchFilters, limit: int, offset: int
) -> SearchResponse:
    """Reciprocal Rank Fusion: score(doc) = Σ_lists 1 / (k + rank_in_list)."""
    started = time.perf_counter()
    settings = get_settings()
    k = settings.search_rrf_k
    pool = settings.search_candidate_limit
    keyword_hits, _ = await _keyword_docs(session, org_id, q, filters, pool, 0)
    vector_hits = _aggregate_vector(await _vector_candidates(session, org_id, q, filters, pool))
    fused: dict[uuid.UUID, dict[str, Any]] = {}
    for rank, hit in enumerate(keyword_hits, start=1):
        entry = fused.setdefault(hit.document_id, {"hit": hit, "score": 0.0, "sources": set()})
        entry["score"] += 1.0 / (k + rank)
        entry["sources"].add("keyword")
    for rank, hit in enumerate(vector_hits, start=1):
        entry = fused.setdefault(hit.document_id, {"hit": hit, "score": 0.0, "sources": set()})
        entry["score"] += 1.0 / (k + rank)
        entry["sources"].add("semantic")
        if hit.document_id in fused and entry["hit"] is not hit:
            entry["hit"].pages = sorted(set(entry["hit"].pages) | set(hit.pages))
    ranked = sorted(fused.values(), key=lambda e: (-e["score"], str(e["hit"].document_id)))
    page = ranked[offset : offset + limit]
    keyword_page = [e["hit"] for e in page if "keyword" in e["sources"]]
    vector_page = [e["hit"] for e in page if "keyword" not in e["sources"]]
    await _snippets(session, org_id, keyword_page, q)
    await _snippets(session, org_id, vector_page, None)
    items = []
    for e in page:
        fused_hit: _DocHit = e["hit"]
        fused_hit.score = e["score"]
        match_type = "hybrid" if len(e["sources"]) == 2 else next(iter(e["sources"]))
        items.append(_to_hit(fused_hit, "rrf", match_type))
    SEARCH_DURATION.labels("hybrid").observe(time.perf_counter() - started)
    return SearchResponse(
        items=items,
        total=len(ranked),
        limit=limit,
        offset=offset,
        mode="hybrid",
        candidate_limit=pool,
        embedding_model=get_embedding_provider().model,
    )
