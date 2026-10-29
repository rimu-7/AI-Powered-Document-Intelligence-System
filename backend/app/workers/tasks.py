"""Celery task entry points.

``docintel.run_stage`` executes one pipeline stage task. Error policy:
* TransientProcessingError / DB / storage connectivity / soft time limit →
  retry with exponential backoff + jitter while attempts < TASK_MAX_ATTEMPTS.
* PermanentProcessingError → no retry; the task is dead-lettered (FAILED with
  error history) and the run fails (page batches fail only their pages).
* Unexpected exceptions are retried like transient errors, then dead-lettered
  as INTERNAL_ERROR. Admins can replay failed runs via the API.
"""

from __future__ import annotations

import random
import time
import uuid
from typing import Any

from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from app.core.config import get_settings
from app.core.database import sync_session
from app.core.exceptions import ProcessingError
from app.core.logging import document_id_var, get_logger, job_id_var, stage_var
from app.core.metrics import STAGE_DURATION, TASK_RETRIES
from app.modules.jobs.lifecycle import claim_task, fail_task_terminally, record_task_error
from app.workers.celery_app import celery_app
from app.workers.pipeline import HANDLERS, LeaseLost

logger = get_logger(__name__)


def _backoff(attempt: int) -> int:
    settings = get_settings()
    base = settings.task_retry_backoff_base_seconds * (2 ** max(0, attempt - 1))
    return int(min(settings.task_retry_backoff_max_seconds, base) + random.uniform(0, settings.task_retry_backoff_base_seconds))


def _classify(exc: BaseException) -> tuple[bool, str, str]:
    """Return (retryable, code, sanitized message)."""
    if isinstance(exc, ProcessingError):
        return exc.retryable, exc.code, exc.message
    if isinstance(exc, SoftTimeLimitExceeded):
        return True, "TIME_LIMIT_EXCEEDED", "Task exceeded its soft time limit"
    if isinstance(exc, OperationalError | InterfaceError) or (isinstance(exc, DBAPIError) and exc.connection_invalidated):
        return True, "DATABASE_UNAVAILABLE", "Database temporarily unavailable"
    if isinstance(exc, DBAPIError):
        # Integrity/programming/data errors are defects, not outages: do not retry.
        return False, "DATABASE_ERROR", type(exc.orig).__name__ if exc.orig is not None else type(exc).__name__
    if isinstance(exc, ConnectionError | TimeoutError):
        return True, "DEPENDENCY_UNAVAILABLE", type(exc).__name__
    return True, "INTERNAL_ERROR", type(exc).__name__


def execute_stage(task_id: str) -> str:
    """Claim and run one stage task, applying the retry/dead-letter policy.

    Raises ``RetryRequested`` when the caller should schedule a retry.
    """
    tid = uuid.UUID(task_id)
    with sync_session() as session:
        claim = claim_task(session, tid)
    if claim is None:
        logger.info("stage_skipped_not_claimable", extra={"task_id": task_id})
        return "skipped"
    job_id_var.set(str(claim.run_id))
    stage_var.set(claim.task_type.value)
    started = time.perf_counter()
    outcome = "ok"
    try:
        HANDLERS[claim.task_type](claim)
        return outcome
    except LeaseLost:
        outcome = "lease_lost"
        logger.warning("stage_lease_lost", extra={"task_id": task_id})
        return outcome
    except Exception as exc:
        retryable, code, message = _classify(exc)
        settings = get_settings()
        logger.warning(
            "stage_failed",
            extra={"task_id": task_id, "error_code": code, "retryable": retryable, "attempt": claim.attempt},
            exc_info=code == "INTERNAL_ERROR",
        )
        if retryable and claim.attempt < settings.task_max_attempts:
            outcome = "retry"
            try:
                with sync_session() as session:
                    record_task_error(session, claim.task_id, code, message, release=True)
                    session.commit()
            except Exception:  # noqa: BLE001 - DB may be the failing dependency; the lease sweeper recovers
                logger.warning("record_task_error_failed", extra={"task_id": task_id})
            TASK_RETRIES.labels(claim.task_type.value, code).inc()
            raise RetryRequested(_backoff(claim.attempt)) from exc
        outcome = "failed"
        with sync_session() as session:
            fail_task_terminally(session, claim, code, message)
            session.commit()
        return outcome
    finally:
        duration = time.perf_counter() - started
        STAGE_DURATION.labels(claim.task_type.value, outcome).observe(duration)
        logger.info("stage_finished", extra={"task_id": task_id, "outcome": outcome, "duration_ms": round(duration * 1000, 1)})


class RetryRequested(Exception):
    def __init__(self, countdown: int) -> None:
        super().__init__(f"retry in {countdown}s")
        self.countdown = countdown


@celery_app.task(name="docintel.run_stage", bind=True, acks_late=True, max_retries=None)
def run_stage(
    self: Any,
    task_id: str,
    run_id: str | None = None,
    task_type: str | None = None,
    queue: str | None = None,
) -> str:
    try:
        return execute_stage(task_id)
    except RetryRequested as retry:
        raise self.retry(countdown=retry.countdown, queue=queue) from None
    finally:
        job_id_var.set(None)
        document_id_var.set(None)
        stage_var.set(None)


@celery_app.task(name="docintel.maintenance.recover", acks_late=True)
def recover() -> dict[str, int]:
    from app.modules.jobs.recovery import recover_stale_work

    return recover_stale_work()


@celery_app.task(name="docintel.maintenance.cleanup", acks_late=True)
def cleanup() -> dict[str, int]:
    from app.modules.jobs.recovery import cleanup_storage

    return cleanup_storage()


@celery_app.task(name="docintel.maintenance.purge", acks_late=True)
def purge() -> dict[str, int]:
    from app.modules.jobs.recovery import purge_old_records

    return purge_old_records()
