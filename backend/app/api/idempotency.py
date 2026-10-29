"""Idempotency-Key support for creation endpoints.

The first request with a key reserves it; a completed response is stored and
replayed for repeats with the same request fingerprint. Reusing a key for a
different request is rejected.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal
from app.core.config import get_settings
from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.documents.models import IdempotencyRecord


def fingerprint(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def validate_key(key: str | None) -> str | None:
    if key is None:
        return None
    key = key.strip()
    if not (8 <= len(key) <= 200) or not all(c.isalnum() or c in "-_.:" for c in key):
        raise ValidationFailedError("Idempotency-Key must be 8-200 characters of [A-Za-z0-9-_.:]", code="INVALID_IDEMPOTENCY_KEY")
    return key


async def begin(
    session: AsyncSession, principal: Principal, endpoint: str, key: str, request_hash: str
) -> tuple[IdempotencyRecord | None, IdempotencyRecord | None]:
    """Returns (reserved_record, replay_record). Exactly one is non-None."""
    expires = datetime.now(UTC) + timedelta(hours=get_settings().idempotency_ttl_hours)
    record_id = uuid.uuid4()
    inserted = (
        await session.execute(
            insert(IdempotencyRecord)
            .values(
                id=record_id,
                organization_id=principal.organization_id,
                user_id=principal.user_id,
                endpoint=endpoint,
                key=key,
                request_hash=request_hash,
                expires_at=expires,
            )
            .on_conflict_do_nothing(index_elements=["organization_id", "user_id", "endpoint", "key"])
            .returning(IdempotencyRecord.id)
        )
    ).scalar_one_or_none()
    await session.commit()
    if inserted is not None:
        return await session.get(IdempotencyRecord, record_id), None
    existing = (
        await session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.organization_id == principal.organization_id,
                IdempotencyRecord.user_id == principal.user_id,
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.key == key,
            )
        )
    ).scalar_one()
    if existing.request_hash != request_hash:
        raise ValidationFailedError("Idempotency-Key was already used for a different request", code="IDEMPOTENCY_KEY_REUSED")
    if existing.response_status is None:
        raise ConflictError("A request with this Idempotency-Key is still in progress", code="IDEMPOTENCY_IN_PROGRESS")
    return None, existing


async def complete(session: AsyncSession, record: IdempotencyRecord, status_code: int, body: Any) -> None:
    record.response_status = status_code
    record.response_body_json = body
    await session.commit()


async def abandon(session: AsyncSession, record: IdempotencyRecord) -> None:
    await session.delete(record)
    await session.commit()
