"""Periodic reconciliation of processing state (Celery Beat → maintenance queue).

Rules:
1. RUNNING tasks whose lease expired (worker died, Redis lost the message):
   back to PENDING and re-published, or dead-lettered after TASK_MAX_ATTEMPTS.
2. PENDING tasks with no unpublished outbox event and no progress for
   TASK_PENDING_REPUBLISH_SECONDS (message lost, e.g. Redis restart without
   persistence): re-published.
3. PARSING runs whose page batches are all terminal but the run did not
   advance (crash between commits): advanced.
4. Pending storage objects older than PENDING_UPLOAD_CLEANUP_SECONDS (upload
   interrupted before the DB commit): object deleted.
5. Soft-deleted documents past retention: objects removed, rows purged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import sync_session
from app.core.logging import get_logger
from app.core.metrics import RECOVERY_ACTIONS
from app.modules.documents.models import Document, IdempotencyRecord, StorageObject
from app.modules.documents.page_images import page_images_prefix
from app.modules.documents.storage import get_storage
from app.modules.identity.models import RefreshSession
from app.modules.jobs.lifecycle import Claim, fail_task_terminally, lock_run, maybe_finish_parsing
from app.modules.jobs.models import OutboxEvent, ProcessingRun, ProcessingTask
from app.modules.jobs.outbox import pending_event_exists, republish
from app.shared.enums import RunState, StorageObjectStatus, TaskState, TaskType

logger = get_logger(__name__)


def _expired_leases(session: Session, now: datetime) -> int:
    settings = get_settings()
    tasks = list(
        session.execute(
            select(ProcessingTask)
            .where(ProcessingTask.task_state == TaskState.RUNNING, ProcessingTask.lease_expires_at < now)
            .limit(200)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    actions = 0
    for task in tasks:
        if task.attempt_count >= settings.task_max_attempts:
            claim = Claim(
                task.id,
                task.processing_run_id,
                task.task_type,
                task.lease_token or task.id,
                task.attempt_count,
                task.page_start,
                task.page_end,
            )
            fail_task_terminally(session, claim, "LEASE_EXPIRED_MAX_ATTEMPTS", "Worker did not finish the task within its lease")
            RECOVERY_ACTIONS.labels("dead_letter_expired_lease").inc()
        else:
            task.task_state = TaskState.PENDING
            task.lease_token = None
            task.lease_expires_at = None
            republish(session, task)
            RECOVERY_ACTIONS.labels("republish_expired_lease").inc()
        actions += 1
    return actions


def _lost_pending(session: Session, now: datetime) -> int:
    settings = get_settings()
    cutoff = now - timedelta(seconds=settings.task_pending_republish_seconds)
    tasks = list(
        session.execute(
            select(ProcessingTask)
            .join(ProcessingRun, ProcessingRun.id == ProcessingTask.processing_run_id)
            .where(
                ProcessingTask.task_state == TaskState.PENDING,
                ProcessingTask.updated_at < cutoff,
                ProcessingRun.state.not_in(
                    [RunState.CANCELLED, RunState.FAILED, RunState.COMPLETED, RunState.COMPLETED_WITH_WARNINGS, RunState.REQUIRES_REVIEW]
                ),
            )
            .limit(200)
            .with_for_update(of=ProcessingTask, skip_locked=True)
        ).scalars()
    )
    actions = 0
    for task in tasks:
        if pending_event_exists(session, task.id):
            continue
        republish(session, task)
        task.updated_at = now
        RECOVERY_ACTIONS.labels("republish_pending").inc()
        actions += 1
    return actions


def _stuck_parsing(session: Session) -> int:
    runs = session.execute(select(ProcessingRun.id).where(ProcessingRun.state == RunState.PARSING).limit(200)).scalars().all()
    actions = 0
    for run_id in runs:
        open_tasks = session.execute(
            select(func.count()).where(
                ProcessingTask.processing_run_id == run_id,
                ProcessingTask.task_state.in_([TaskState.PENDING, TaskState.RUNNING]),
            )
        ).scalar_one()
        if open_tasks:
            continue
        has_parse = session.execute(
            select(func.count()).where(ProcessingTask.processing_run_id == run_id, ProcessingTask.task_type == TaskType.PARSE_PAGES)
        ).scalar_one()
        if not has_parse:
            continue
        run = lock_run(session, run_id)
        maybe_finish_parsing(session, run)
        RECOVERY_ACTIONS.labels("advance_stuck_parsing").inc()
        actions += 1
    return actions


def recover_stale_work() -> dict[str, int]:
    now = datetime.now(UTC)
    result = {}
    with sync_session() as session:
        result["expired_leases"] = _expired_leases(session, now)
        session.commit()
        result["lost_pending"] = _lost_pending(session, now)
        session.commit()
        result["stuck_parsing"] = _stuck_parsing(session)
        session.commit()
    if any(result.values()):
        logger.info("recovery_actions", extra=result)
    return result


def cleanup_storage() -> dict[str, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    storage = get_storage()
    removed_pending = purged_docs = 0
    with sync_session() as session:
        # Direct uploads stay PENDING while the client sends the file; never cut them short.
        cutoff = now - timedelta(seconds=max(settings.pending_upload_cleanup_seconds, settings.direct_upload_ttl_seconds + 600))
        stale = list(
            session.execute(
                select(StorageObject)
                .where(StorageObject.status == StorageObjectStatus.PENDING, StorageObject.created_at < cutoff)
                .limit(500)
            ).scalars()
        )
        for obj in stale:
            try:
                storage.delete(obj.bucket, obj.key)
            except Exception:  # noqa: BLE001
                logger.warning("pending_object_delete_failed", extra={"key_prefix": obj.key.split("/")[0]})
                continue
            obj.status = StorageObjectStatus.DELETED
            obj.deleted_at = now
            removed_pending += 1
        session.commit()

        retention_cutoff = now - timedelta(days=settings.document_retention_days_after_delete)
        docs = list(
            session.execute(
                select(Document).where(Document.deleted_at.is_not(None), Document.deleted_at < retention_cutoff).limit(100)
            ).scalars()
        )
        for doc in docs:
            objects = list(
                session.execute(
                    select(StorageObject).where(StorageObject.document_id == doc.id, StorageObject.status != StorageObjectStatus.DELETED)
                ).scalars()
            )
            ok = True
            for obj in objects:
                try:
                    storage.delete(obj.bucket, obj.key)
                    obj.status = StorageObjectStatus.DELETED
                    obj.deleted_at = now
                except Exception:  # noqa: BLE001
                    ok = False
            try:  # cached page images are not tracked as storage objects
                storage.delete_prefix(settings.s3_bucket_artifacts, page_images_prefix(doc.organization_id, doc.id))
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                session.delete(doc)
                purged_docs += 1
        session.commit()
        RECOVERY_ACTIONS.labels("purged_documents").inc(purged_docs)
    return {"pending_objects_removed": removed_pending, "documents_purged": purged_docs}


def purge_old_records() -> dict[str, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    with sync_session() as session:
        outbox = session.execute(
            delete(OutboxEvent).where(
                OutboxEvent.published_at.is_not(None), OutboxEvent.published_at < now - timedelta(days=settings.outbox_retention_days)
            )
        ).rowcount  # type: ignore[attr-defined]
        idem = session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.expires_at < now)).rowcount  # type: ignore[attr-defined]
        sessions = session.execute(delete(RefreshSession).where(RefreshSession.expires_at < now - timedelta(days=1))).rowcount  # type: ignore[attr-defined]
        session.commit()
    return {"outbox_events": int(outbox or 0), "idempotency_records": int(idem or 0), "refresh_sessions": int(sessions or 0)}
