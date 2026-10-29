"""Tenant-scoped document queries and lifecycle operations (async, API)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal
from app.core.exceptions import NotFoundError
from app.modules.auditing.service import record_audit
from app.modules.comparison.models import ComparisonDocument, DocumentComparison
from app.modules.documents.models import Document, DocumentChunk
from app.modules.jobs.models import ProcessingRun, ProcessingTask
from app.shared.enums import TERMINAL_RUN_STATES, ComparisonStatus, DocumentStatus, RunState, TaskState


async def get_document(session: AsyncSession, principal: Principal, document_id: uuid.UUID, *, for_update: bool = False) -> Document:
    """Fetch a document of the caller's organization; 404 otherwise (no existence leak)."""
    stmt = select(Document).where(
        Document.id == document_id,
        Document.organization_id == principal.organization_id,
        Document.deleted_at.is_(None),
    )
    if for_update:
        stmt = stmt.with_for_update()
    doc = (await session.execute(stmt)).scalar_one_or_none()
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


async def mark_comparisons_stale(session: AsyncSession, organization_id: uuid.UUID, document_id: uuid.UUID, reason: str) -> int:
    ids = select(ComparisonDocument.comparison_id).where(ComparisonDocument.document_id == document_id)
    result = await session.execute(
        update(DocumentComparison)
        .where(
            DocumentComparison.organization_id == organization_id,
            DocumentComparison.id.in_(ids),
            DocumentComparison.status == ComparisonStatus.COMPLETED,
        )
        .values(status=ComparisonStatus.STALE, stale_reason=reason[:200])
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def soft_delete(session: AsyncSession, principal: Principal, document_id: uuid.UUID) -> None:
    doc = await get_document(session, principal, document_id, for_update=True)
    now = datetime.now(UTC)
    doc.deleted_at = now
    doc.status = DocumentStatus.DELETED
    active_runs = select(ProcessingRun.id).where(ProcessingRun.document_id == doc.id, ProcessingRun.state.not_in(list(TERMINAL_RUN_STATES)))
    await session.execute(
        update(ProcessingTask)
        .where(ProcessingTask.processing_run_id.in_(active_runs), ProcessingTask.task_state.in_([TaskState.PENDING, TaskState.RUNNING]))
        .values(task_state=TaskState.CANCELLED, lease_token=None, lease_expires_at=None)
    )
    await session.execute(
        update(ProcessingRun)
        .where(ProcessingRun.document_id == doc.id, ProcessingRun.state.not_in(list(TERMINAL_RUN_STATES)))
        .values(state=RunState.CANCELLED, completed_at=now, error_code="DOCUMENT_DELETED")
    )
    # Remove from search immediately; originals are purged after the retention period.
    await session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == doc.id, DocumentChunk.organization_id == principal.organization_id)
    )
    await mark_comparisons_stale(session, principal.organization_id, doc.id, "document deleted")
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="document.deleted",
        resource_type="document",
        resource_id=doc.id,
    )
    await session.commit()
