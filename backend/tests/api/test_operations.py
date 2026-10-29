from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update

from evaluation.synthetic import image_bytes, invoice_pdf_bytes, random_invoice, scanned_pdf_bytes
from tests.conftest import register_org, upload

pytestmark = pytest.mark.integration


async def test_health_probes(client: Any) -> None:
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    ready = await client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["checks"] == {"database": "ok", "redis": "ok", "storage": "ok"}
    startup = await client.get("/health/startup")
    assert startup.status_code == 200 and startup.json()["checks"]["migrations"] == "ok"
    r = await client.get("/health/live", headers={"X-Request-ID": "abcdef123456"})
    assert r.headers["x-request-id"] == "abcdef123456"
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_metrics_endpoint_and_token(client: Any, settings_override: Any) -> None:
    r = await client.get("/metrics")
    assert r.status_code == 200 and "docintel_http_requests_total" in r.text and "docintel_queue_backlog" in r.text
    settings_override(METRICS_TOKEN="metrics-secret-token")
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        assert (await c.get("/metrics")).status_code == 401
        assert (await c.get("/metrics", headers={"Authorization": "Bearer metrics-secret-token"})).status_code == 200


async def test_admin_stats_and_permissions(client: Any, org: dict[str, Any]) -> None:
    r = await client.get("/api/v1/admin/stats", headers=org["headers"])
    assert r.status_code == 200 and "documents_by_status" in r.json()
    pw = "Analyst-Password-7"
    await client.post(
        "/api/v1/users",
        headers=org["headers"],
        json={"email": f"an-{uuid.uuid4().hex[:6]}@example.com", "password": pw, "full_name": "A", "role": "ANALYST"},
    )
    users = (await client.get("/api/v1/users", headers=org["headers"])).json()["items"]
    analyst = next(u for u in users if u["role"] == "ANALYST")
    login = (await client.post("/api/v1/auth/login", json={"email": analyst["email"], "password": pw})).json()
    ah = {"Authorization": f"Bearer {login['access_token']}"}
    assert (await client.get("/api/v1/admin/stats", headers=ah)).status_code == 403
    r = await client.patch(
        f"/api/v1/invoices/{uuid.uuid4()}/corrections",
        headers=ah,
        json={"expected_version": 1, "reason": "xyz", "changes": [{"field_path": "total_amount", "value": "1"}]},
    )
    assert r.status_code == 403
    me = (await client.get("/api/v1/auth/me", headers=org["headers"])).json()["user"]["id"]
    r = await client.patch(f"/api/v1/users/{me}", headers=org["headers"], json={"role": "VIEWER"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SELF_LOCKOUT"


async def test_reject_and_reprocess(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    h = org["headers"]
    spec = random_invoice(random.Random(31), 301)
    spec.total_override = spec.total_amount + 1
    r = await upload(client, h, [("rej.pdf", invoice_pdf_bytes([spec]), "application/pdf")])
    doc_id = r.json()["results"][0]["document_id"]
    pipeline()
    inv = (await client.get(f"/api/v1/documents/{doc_id}/invoices", headers=h)).json()[0]
    r = await client.post(
        f"/api/v1/invoices/{inv['id']}/reject", headers=h, json={"expected_version": inv["version"], "reason": "fraudulent total"}
    )
    assert r.status_code == 200 and r.json()["review_status"] == "REJECTED"
    review = (await client.get("/api/v1/reviews/queue", headers=h, params={"status": "REJECTED"})).json()["items"][0]
    detail = (await client.get(f"/api/v1/reviews/{review['id']}", headers=h)).json()
    assert detail["history"][-1]["action_type"] == "REJECTION"
    r = await client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=h)
    assert r.status_code == 202
    assert (await client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=h)).status_code == 409  # already active
    pipeline()
    invoices = (await client.get(f"/api/v1/documents/{doc_id}/invoices", headers=h, params={"include_superseded": True})).json()
    assert len(invoices) == 2 and sum(1 for i in invoices if i["review_status"] == "REJECTED") == 1
    extractions = (await client.get(f"/api/v1/documents/{doc_id}/extractions", headers=h)).json()
    assert [e["extraction_revision"] for e in extractions] == [2, 1]


async def test_storage_cleanup_and_retention(client: Any, org: dict[str, Any], pipeline: Any, settings_override: Any) -> None:
    from app.core.database import sync_session
    from app.modules.documents.models import Document, StorageObject
    from app.modules.jobs.recovery import cleanup_storage, purge_old_records
    from app.shared.enums import StorageCategory, StorageObjectStatus

    h = org["headers"]
    r = await upload(client, h, [("ret.pdf", invoice_pdf_bytes([random_invoice(random.Random(32), 302)]), "application/pdf")])
    doc_id = uuid.UUID(r.json()["results"][0]["document_id"])
    pipeline()
    assert (await client.delete(f"/api/v1/documents/{doc_id}", headers=h)).status_code == 204
    with sync_session() as s:
        org_id = s.execute(select(Document.organization_id).where(Document.id == doc_id)).scalar_one()
        s.add(
            StorageObject(
                id=uuid.uuid4(),
                organization_id=org_id,
                document_id=None,
                category=StorageCategory.ORIGINAL,
                bucket="test-originals",
                key=f"originals/{org_id}/_/{uuid.uuid4().hex}",
                size_bytes=10,
                status=StorageObjectStatus.PENDING,
                created_at=datetime.now(UTC) - timedelta(hours=3),
            )
        )
        s.execute(update(Document).where(Document.id == doc_id).values(deleted_at=datetime.now(UTC) - timedelta(days=60)))
        s.commit()
    result = cleanup_storage()
    assert result["pending_objects_removed"] >= 1 and result["documents_purged"] >= 1
    with sync_session() as s:
        assert s.get(Document, doc_id) is None
    assert set(purge_old_records()) == {"outbox_events", "idempotency_records", "refresh_sessions"}


@pytest.mark.ocr
async def test_scanned_pdf_png_and_tiff_go_through_ocr(client: Any, pipeline: Any) -> None:
    org = await register_org(client)
    h = org["headers"]
    spec = random_invoice(random.Random(33), 303, date_style="iso")
    pdf = invoice_pdf_bytes([spec])
    files = [
        ("scan.pdf", scanned_pdf_bytes(pdf, seed=1), "application/pdf"),
        ("scan.png", image_bytes(pdf, "PNG", seed=2), "image/png"),
        ("scan.tiff", image_bytes(invoice_pdf_bytes([spec, random_invoice(random.Random(34), 304)]), "TIFF", seed=3), "image/tiff"),
    ]
    results = (await upload(client, h, files)).json()["results"]
    pipeline()
    for res in results:
        job = (await client.get(res["status_url"], headers=h)).json()
        assert job["state"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS", "REQUIRES_REVIEW"), job
        pages = (await client.get(f"/api/v1/documents/{res['document_id']}/pages", headers=h)).json()["items"]
        assert pages[0]["ocr_engine"] == "tesseract" and pages[0]["page_type"] in ("SCANNED", "IMAGE")
        invoices = (await client.get(f"/api/v1/documents/{res['document_id']}/invoices", headers=h)).json()
        assert any(i["invoice_number"] == spec.invoice_number for i in invoices), invoices
    tiff_pages = (await client.get(f"/api/v1/documents/{results[2]['document_id']}/pages", headers=h)).json()
    assert tiff_pages["total"] == 2
