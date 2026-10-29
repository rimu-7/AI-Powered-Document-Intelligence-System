"""Originals stored in UploadThing (fake server): multipart, raw-body and direct uploads,
end-to-end processing, downloads, rejection cleanup, tenant isolation."""

from __future__ import annotations

import random
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.modules.documents import uploadthing
from evaluation.synthetic import invoice_pdf_bytes, random_invoice
from tests.conftest import register_org
from tests.uploadthing_fake import TOKEN, FakeUploadThing

pytestmark = pytest.mark.integration


@pytest.fixture
def fake_ut(settings_override: Any) -> Iterator[FakeUploadThing]:
    settings_override(ORIGINALS_STORAGE="uploadthing", UPLOADTHING_TOKEN=TOKEN)
    fake = FakeUploadThing()
    uploadthing._client = uploadthing.UploadThingClient(uploadthing.UploadThingCredentials.from_token(TOKEN), transport=fake.transport())
    yield fake
    uploadthing.reset_uploadthing()


@pytest.fixture
async def ut_client(fake_ut: FakeUploadThing) -> Any:
    from app.main import create_app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://testserver") as c:
        yield c


def _pdf(seed: int) -> tuple[bytes, Any]:
    spec = random_invoice(random.Random(seed), seed, date_style="iso")
    return invoice_pdf_bytes([spec]), spec


async def _invoice(client: Any, h: dict[str, str], doc_id: str) -> dict[str, Any]:
    invoices = (await client.get(f"/api/v1/documents/{doc_id}/invoices", headers=h)).json()
    assert len(invoices) == 1, invoices
    return invoices[0]


async def test_multipart_upload_stores_raw_original_in_uploadthing(ut_client: Any, fake_ut: FakeUploadThing, pipeline: Any) -> None:
    org = await register_org(ut_client)
    h = org["headers"]
    data, spec = _pdf(701)
    r = await ut_client.post("/api/v1/documents/upload", headers=h, files=[("files", ("inv.pdf", data, "application/pdf"))])
    assert r.status_code == 202, r.text
    doc_id = r.json()["results"][0]["document_id"]
    doc = (await ut_client.get(f"/api/v1/documents/{doc_id}", headers=h)).json()
    assert len(fake_ut.files) == 1
    stored_key, stored = next(iter(fake_ut.files.items()))
    assert stored == data and "/" not in stored_key and doc_id.replace("-", "") in stored_key
    pipeline()  # workers download the original from UploadThing
    inv = await _invoice(ut_client, h, doc_id)
    assert inv["invoice_number"] == spec.invoice_number and Decimal(inv["total_amount"]) == spec.total_amount
    dl = await ut_client.get(f"/api/v1/documents/{doc_id}/download", headers=h)
    assert dl.status_code == 200 and dl.content == data
    r = await ut_client.get(f"/api/v1/documents/{doc_id}/download", headers=h, params={"mode": "presigned"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "PRESIGNED_UNAVAILABLE"
    assert doc["sha256"]


async def test_raw_body_upload(ut_client: Any, fake_ut: FakeUploadThing, pipeline: Any) -> None:
    org = await register_org(ut_client)
    h = org["headers"]
    data, spec = _pdf(702)
    r = await ut_client.post(
        "/api/v1/documents/upload/raw",
        params={"filename": "raw-invoice.pdf"},
        headers=h | {"Content-Type": "application/octet-stream"},
        content=data,
    )
    assert r.status_code == 202, r.text
    doc_id = r.json()["results"][0]["document_id"]
    assert data in fake_ut.files.values()
    pipeline()
    assert (await _invoice(ut_client, h, doc_id))["invoice_number"] == spec.invoice_number
    # Content is checked, not the name: an executable called .pdf is rejected and not stored.
    before = len(fake_ut.files)
    r = await ut_client.post("/api/v1/documents/upload/raw", params={"filename": "evil.pdf"}, headers=h, content=b"MZ\x90\x00binary")
    assert r.status_code == 422 and r.json()["results"][0]["error"]["code"] == "CONTENT_SIGNATURE_MISMATCH"
    assert len(fake_ut.files) == before
    r = await ut_client.post("/api/v1/documents/upload/raw", headers=h, content=data)
    assert r.status_code == 422  # filename is required


async def test_direct_upload_flow(ut_client: Any, fake_ut: FakeUploadThing, pipeline: Any) -> None:
    org = await register_org(ut_client)
    h = org["headers"]
    data, spec = _pdf(703)
    r = await ut_client.post("/api/v1/documents/direct-uploads", headers=h, json={"filename": "direct.pdf", "size": len(data)})
    assert r.status_code == 201, r.text
    ticket = r.json()
    # Completing before the file arrives is a clear, retryable error.
    r = await ut_client.post(ticket["complete_url"], headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "UPLOAD_NOT_RECEIVED"
    # The client uploads straight to UploadThing (our API is not involved).
    with httpx.Client(transport=fake_ut.transport()) as ut:
        put = ut.put(ticket["upload_url"], files={"file": ("direct.pdf", data, "application/pdf")})
    assert put.status_code == 200
    r = await ut_client.post(ticket["complete_url"], headers=h)
    assert r.status_code == 202, r.text
    result = r.json()["results"][0]
    assert result["status"] == "accepted" and result["document_id"] == ticket["document_id"]
    again = await ut_client.post(ticket["complete_url"], headers=h)  # idempotent
    assert again.status_code == 202 and again.json()["results"][0]["job_id"] == result["job_id"]
    pipeline()
    assert (await _invoice(ut_client, h, ticket["document_id"]))["invoice_number"] == spec.invoice_number
    # Another tenant cannot complete (or even see) this upload.
    other = await register_org(ut_client)
    assert (await ut_client.post(ticket["complete_url"], headers=other["headers"])).status_code == 404


async def test_direct_upload_rejects_bad_content_and_cleans_up(ut_client: Any, fake_ut: FakeUploadThing) -> None:
    org = await register_org(ut_client)
    h = org["headers"]
    payload = b"MZ\x90\x00 not a pdf at all"
    ticket = (
        await ut_client.post("/api/v1/documents/direct-uploads", headers=h, json={"filename": "fake.pdf", "size": len(payload)})
    ).json()
    with httpx.Client(transport=fake_ut.transport()) as ut:
        assert ut.put(ticket["upload_url"], files={"file": ("fake.pdf", payload, "application/pdf")}).status_code == 200
    assert payload in fake_ut.files.values()
    r = await ut_client.post(ticket["complete_url"], headers=h)
    assert r.status_code == 422 and r.json()["results"][0]["error"]["code"] == "CONTENT_SIGNATURE_MISMATCH"
    assert payload not in fake_ut.files.values()  # rejected file deleted from UploadThing
    assert (await ut_client.post(ticket["complete_url"], headers=h)).json()["error"]["code"] == "UPLOAD_DISCARDED"
    # Validation of the request itself.
    r = await ut_client.post("/api/v1/documents/direct-uploads", headers=h, json={"filename": "x.exe", "size": 10})
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    r = await ut_client.post("/api/v1/documents/direct-uploads", headers=h, json={"filename": "x.pdf", "size": 10**12})
    assert r.status_code == 422 and r.json()["error"]["code"] == "FILE_TOO_LARGE"


async def test_uploadthing_outage_is_reported_and_leaves_nothing(
    ut_client: Any, fake_ut: FakeUploadThing, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.modules.documents.uploadthing.time.sleep", lambda *_: None)
    org = await register_org(ut_client)
    fake_ut.fail_next = [503] * 20
    data, _ = _pdf(704)
    r = await ut_client.post("/api/v1/documents/upload", headers=org["headers"], files=[("files", ("a.pdf", data, "application/pdf"))])
    assert r.status_code == 422 and r.json()["results"][0]["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert (await ut_client.get("/api/v1/documents", headers=org["headers"])).json()["total"] == 0


async def test_direct_upload_unavailable_with_s3_originals(client: Any, org: dict[str, Any]) -> None:
    r = await client.post("/api/v1/documents/direct-uploads", headers=org["headers"], json={"filename": "a.pdf", "size": 10})
    assert r.status_code == 409 and r.json()["error"]["code"] == "DIRECT_UPLOAD_UNAVAILABLE"
