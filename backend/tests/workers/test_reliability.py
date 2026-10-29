"""Failure-recovery behaviour of the job system (real PostgreSQL, in-process workers)."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text, update

from app.core.database import sync_session
from app.core.exceptions import TransientProcessingError
from app.modules.documents.models import DocumentPage
from app.modules.extraction.models import InvoiceRecord
from app.modules.jobs.models import OutboxEvent, ProcessingRun, ProcessingTask
from app.modules.validation.models import ValidationIssue
from app.shared.enums import PageStatus, RunState, TaskState, TaskType
from app.workers.dispatcher import dispatch_batch
from app.workers.tasks import RetryRequested, execute_stage
from evaluation.synthetic import invoice_pdf_bytes, random_invoice
from tests.conftest import InlinePublisher, upload

pytestmark = pytest.mark.integration

DONE = (RunState.COMPLETED, RunState.COMPLETED_WITH_WARNINGS, RunState.REQUIRES_REVIEW)


def _publish_all() -> list[str]:
    publisher = InlinePublisher()
    with sync_session() as s:
        dispatch_batch(s, publisher, 100)
    return publisher.task_ids


def _run(task_ids: list[str]) -> None:
    for tid in task_ids:
        for _ in range(10):
            try:
                execute_stage(tid)
                break
            except RetryRequested:
                continue


def _drive_until(task_type: TaskType) -> list[str]:
    """Run the pipeline but stop before executing ``task_type``; return its task ids."""
    for _ in range(50):
        ids = _publish_all()
        if not ids:
            return []
        with sync_session() as s:
            types = {
                str(t.id): t.task_type
                for t in s.execute(select(ProcessingTask).where(ProcessingTask.id.in_([uuid.UUID(i) for i in ids]))).scalars()
            }
        stop = [i for i in ids if types[i] == task_type]
        _run([i for i in ids if types[i] != task_type])
        if stop:
            return stop
    raise AssertionError("stage not reached")


async def _upload_pdf(client: Any, org: dict[str, Any], seed: int, pages: int = 1) -> dict[str, Any]:
    spec = random_invoice(random.Random(seed), seed, date_style="iso")
    if pages > 1:
        spec.lines = (spec.lines * 40)[: 18 * pages]
    r = await upload(client, org["headers"], [(f"doc-{seed}.pdf", invoice_pdf_bytes([spec]), "application/pdf")])
    assert r.status_code == 202, r.text
    return r.json()["results"][0]


def _counts(document_id: str) -> tuple[int, int, int]:
    with sync_session() as s:
        invoices = s.execute(
            select(func.count()).where(InvoiceRecord.document_id == uuid.UUID(document_id), InvoiceRecord.superseded_at.is_(None))
        ).scalar_one()
        issues = s.execute(
            select(func.count()).where(ValidationIssue.document_id == uuid.UUID(document_id), ValidationIssue.resolution_status == "OPEN")
        ).scalar_one()
        pages = s.execute(select(func.count()).where(DocumentPage.document_id == uuid.UUID(document_id))).scalar_one()
    return invoices, issues, pages


def _run_state(job_id: str) -> RunState:
    with sync_session() as s:
        return s.execute(select(ProcessingRun.state).where(ProcessingRun.id == uuid.UUID(job_id))).scalar_one()


async def test_duplicate_delivery_is_idempotent(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    res = await _upload_pdf(client, org, 501)
    extract_ids = _drive_until(TaskType.EXTRACT)
    _run(extract_ids)
    _run(extract_ids)  # redelivered message: task already DONE → skipped
    pipeline()
    before = _counts(res["document_id"])
    # Force re-execution of every stage of this run (simulates redelivery after a crash
    # between work and acknowledgement): reset tasks to PENDING and run them again.
    with sync_session() as s:
        s.execute(
            update(ProcessingTask)
            .where(ProcessingTask.processing_run_id == uuid.UUID(res["job_id"]), ProcessingTask.task_type.in_([TaskType.VALIDATE]))
            .values(task_state=TaskState.PENDING)
        )
        s.execute(update(ProcessingRun).where(ProcessingRun.id == uuid.UUID(res["job_id"])).values(state=RunState.VALIDATING))
        tid = s.execute(
            select(ProcessingTask.id).where(
                ProcessingTask.processing_run_id == uuid.UUID(res["job_id"]), ProcessingTask.task_type == TaskType.VALIDATE
            )
        ).scalar_one()
        s.commit()
    _run([str(tid)])
    with sync_session() as s:
        s.execute(
            update(ProcessingTask)
            .where(ProcessingTask.processing_run_id == uuid.UUID(res["job_id"]), ProcessingTask.task_type == TaskType.INDEX)
            .values(task_state=TaskState.DONE)
        )
        s.commit()
    pipeline()
    after = _counts(res["document_id"])
    assert before == after and before[0] == 1


async def test_worker_crash_mid_batch_recovers_without_duplicates(
    client: Any, org: dict[str, Any], pipeline: Any, settings_override: Any
) -> None:
    from app.modules.jobs.lifecycle import claim_task
    from app.modules.jobs.recovery import recover_stale_work

    res = await _upload_pdf(client, org, 502, pages=3)
    parse_ids = _drive_until(TaskType.PARSE_PAGES)
    # A worker claims the batch and dies (no completion, lease left behind).
    with sync_session() as s:
        claim = claim_task(s, uuid.UUID(parse_ids[0]))
        assert claim is not None
    # The redelivered message is ignored while the lease is valid...
    assert execute_stage(parse_ids[0]) == "skipped"
    # ...and after the lease expires, the recovery sweeper re-publishes it.
    with sync_session() as s:
        s.execute(
            update(ProcessingTask)
            .where(ProcessingTask.id == uuid.UUID(parse_ids[0]))
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        s.commit()
    assert recover_stale_work()["expired_leases"] == 1
    pipeline()
    assert _run_state(res["job_id"]) in DONE
    invoices, _, pages = _counts(res["document_id"])
    assert invoices == 1 and pages == 3


async def test_lost_broker_message_is_republished(client: Any, org: dict[str, Any], pipeline: Any, settings_override: Any) -> None:
    from app.modules.jobs.recovery import recover_stale_work

    res = await _upload_pdf(client, org, 503)
    lost = _publish_all()  # published, then Redis "restarts" and the messages are gone
    assert lost
    settings_override(TASK_PENDING_REPUBLISH_SECONDS="0")
    with sync_session() as s:
        s.execute(
            update(ProcessingTask)
            .where(ProcessingTask.id.in_([uuid.UUID(t) for t in lost]))
            .values(updated_at=datetime.now(UTC) - timedelta(minutes=10))
        )
        s.commit()
    assert recover_stale_work()["lost_pending"] >= 1
    pipeline()
    assert _run_state(res["job_id"]) in DONE


async def test_outbox_publish_failure_backs_off_and_recovers(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    res = await _upload_pdf(client, org, 504)
    failing = InlinePublisher()
    failing.fail = True
    with sync_session() as s:
        assert dispatch_batch(s, failing, 100) == 0
        event = s.execute(select(OutboxEvent).where(OutboxEvent.aggregate_id == uuid.UUID(res["job_id"]))).scalars().first()
        assert event is not None and event.published_at is None and event.attempt_count == 1 and event.available_at > datetime.now(UTC)
        s.execute(update(OutboxEvent).where(OutboxEvent.id == event.id).values(available_at=datetime.now(UTC)))
        s.commit()
    pipeline()
    assert _run_state(res["job_id"]) in DONE


async def test_transient_error_retries_then_succeeds(
    client: Any, org: dict[str, Any], pipeline: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.workers import pipeline as pl

    calls = {"n": 0}
    original = pl.HANDLERS[TaskType.EXTRACT]

    def flaky(claim: Any) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientProcessingError("LLM timeout", code="LLM_TRANSIENT")
        original(claim)

    monkeypatch.setitem(pl.HANDLERS, TaskType.EXTRACT, flaky)
    res = await _upload_pdf(client, org, 505)
    pipeline()
    assert calls["n"] == 3
    assert _run_state(res["job_id"]) in DONE
    with sync_session() as s:
        task = s.execute(
            select(ProcessingTask).where(
                ProcessingTask.processing_run_id == uuid.UUID(res["job_id"]), ProcessingTask.task_type == TaskType.EXTRACT
            )
        ).scalar_one()
        assert task.attempt_count == 3 and [e["code"] for e in task.error_history_json] == ["LLM_TRANSIENT", "LLM_TRANSIENT"]


async def test_retries_exhausted_dead_letters_and_admin_replay(
    client: Any, org: dict[str, Any], pipeline: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.workers import pipeline as pl

    original = pl.HANDLERS[TaskType.EXTRACT]

    def down(claim: Any) -> None:
        raise TransientProcessingError("provider down", code="LLM_TRANSIENT")

    monkeypatch.setitem(pl.HANDLERS, TaskType.EXTRACT, down)
    res = await _upload_pdf(client, org, 506)
    pipeline()
    assert _run_state(res["job_id"]) == RunState.FAILED
    job = (await client.get(f"/api/v1/jobs/{res['job_id']}", headers=org["headers"])).json()
    assert job["error_code"] == "LLM_TRANSIENT" and job["failed_tasks"][0]["attempt_count"] == 5
    dead = (await client.get("/api/v1/admin/dead-letter", headers=org["headers"])).json()
    assert any(d["job"]["id"] == res["job_id"] for d in dead["items"])

    monkeypatch.setitem(pl.HANDLERS, TaskType.EXTRACT, original)
    r = await client.post(f"/api/v1/jobs/{res['job_id']}/retry", headers=org["headers"])
    assert r.status_code == 202
    new_job = r.json()["job_id"]
    pipeline()
    assert _run_state(new_job) in DONE
    # The retry reused checkpointed pages: no new parse batch was needed.
    with sync_session() as s:
        parse = s.execute(
            select(func.count()).where(
                ProcessingTask.processing_run_id == uuid.UUID(new_job), ProcessingTask.task_type == TaskType.PARSE_PAGES
            )
        ).scalar_one()
    assert parse == 0


async def test_malformed_and_encrypted_pdfs_fail_cleanly(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    import pymupdf

    r = await upload(client, org["headers"], [("broken.pdf", b"%PDF-1.4\n1 0 obj << >> garbage", "application/pdf")])
    broken = r.json()["results"][0]
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    enc = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="owner")
    r = await upload(client, org["headers"], [("locked.pdf", enc, "application/pdf")])
    locked = r.json()["results"][0]
    pipeline()
    for res, code in ((broken, "PDF_MALFORMED"), (locked, "PDF_ENCRYPTED")):
        job = (await client.get(f"/api/v1/jobs/{res['job_id']}", headers=org["headers"])).json()
        assert job["state"] == "FAILED" and job["error_code"] == code
        assert job["failed_tasks"][0]["attempt_count"] == 1  # permanent errors are not retried
        assert "Traceback" not in (job["sanitized_error_message"] or "")


async def test_partial_page_failure_completes_with_warnings(
    client: Any, org: dict[str, Any], pipeline: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.exceptions import PermanentProcessingError
    from app.workers import pipeline as pl

    original = pl.process_pdf_page

    def sometimes(doc: Any, page_number: int, ocr: Any) -> Any:
        if page_number == 2:
            raise PermanentProcessingError("corrupt page", code="PDF_PAGE_CORRUPT")
        return original(doc, page_number, ocr)

    monkeypatch.setattr(pl, "process_pdf_page", sometimes)
    res = await _upload_pdf(client, org, 507, pages=3)
    pipeline()
    job = (await client.get(f"/api/v1/jobs/{res['job_id']}", headers=org["headers"])).json()
    assert job["pages_total"] == 3 and job["pages_failed"] == 1 and job["pages_completed"] == 2
    assert job["state"] in ("COMPLETED_WITH_WARNINGS", "REQUIRES_REVIEW")
    issues = (await client.get(f"/api/v1/documents/{res['document_id']}/validations", headers=org["headers"])).json()["items"]
    assert any(i["rule_code"] == "PAGES_FAILED" for i in issues)
    with sync_session() as s:
        status = s.execute(
            select(DocumentPage.processing_status).where(
                DocumentPage.document_id == uuid.UUID(res["document_id"]), DocumentPage.page_number == 2
            )
        ).scalar_one()
    assert status == PageStatus.FAILED


async def test_cancel_stops_processing(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    res = await _upload_pdf(client, org, 508)
    r = await client.post(f"/api/v1/jobs/{res['job_id']}/cancel", headers=org["headers"])
    assert r.status_code == 200 and r.json()["state"] == "CANCELLED"
    pipeline()
    assert _run_state(res["job_id"]) == RunState.CANCELLED
    assert (await client.post(f"/api/v1/jobs/{res['job_id']}/cancel", headers=org["headers"])).status_code == 409


async def test_database_unavailable_is_classified_transient() -> None:
    from sqlalchemy.exc import OperationalError

    from app.workers.tasks import _classify

    retryable, code, _ = _classify(OperationalError("select 1", {}, Exception("connection refused")))
    assert retryable and code == "DATABASE_UNAVAILABLE"
    retryable, code, _ = _classify(TransientProcessingError("x", code="STORAGE_UNAVAILABLE"))
    assert retryable and code == "STORAGE_UNAVAILABLE"


async def test_audit_log_is_append_only(configured: Any) -> None:
    from sqlalchemy.exc import DBAPIError

    with sync_session() as s:
        with pytest.raises(DBAPIError):
            s.execute(text("UPDATE audit_events SET action = 'tampered'"))
        s.rollback()
        with pytest.raises(DBAPIError):
            s.execute(text("DELETE FROM audit_events"))
        s.rollback()


async def test_many_invoices_in_one_document_with_review_tasks(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    """Regression: the partial-index upsert must survive psycopg prepared statements (>5 executions)."""
    from decimal import Decimal

    rng = random.Random(509)
    specs = [random_invoice(rng, 9500 + i, date_style="iso") for i in range(12)]
    for s in specs:
        s.total_override = s.total_amount + Decimal("1.00")  # every invoice needs review
    r = await upload(client, org["headers"], [("many.pdf", invoice_pdf_bytes(specs), "application/pdf")])
    res = r.json()["results"][0]
    pipeline()
    assert _run_state(res["job_id"]) == RunState.REQUIRES_REVIEW
    queue = (await client.get("/api/v1/reviews/queue", headers=org["headers"], params={"limit": 50})).json()
    assert sum(1 for t in queue["items"] if t["document_id"] == res["document_id"]) == 12


async def test_sql_errors_are_permanent_not_transient() -> None:
    from sqlalchemy.exc import IntegrityError, ProgrammingError

    from app.workers.tasks import _classify

    for exc in (IntegrityError("x", {}, Exception("dup")), ProgrammingError("x", {}, Exception("bad sql"))):
        retryable, code, _ = _classify(exc)
        assert not retryable and code == "DATABASE_ERROR"
