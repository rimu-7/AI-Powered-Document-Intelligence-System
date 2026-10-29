"""Append-only audit trail. Works with both sync and async sessions (``add`` only)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.logging import redact, request_id_var
from app.modules.auditing.models import AuditEvent


def record_audit(
    session: Session | AsyncSession,
    *,
    organization_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | str | None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        id=uuid.uuid4(),
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        request_id=request_id_var.get(),
        metadata_json=redact(metadata or {}),
    )
    session.add(event)
    return event
