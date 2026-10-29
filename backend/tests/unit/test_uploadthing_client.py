from __future__ import annotations

import io
import json
from typing import Any

import httpx
import pytest

from app.modules.documents.uploadthing import (
    UploadThingClient,
    UploadThingCredentials,
    UploadThingError,
    UploadThingUnavailableError,
)
from tests.uploadthing_fake import APP_ID, TOKEN, FakeUploadThing


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.modules.documents.uploadthing.time.sleep", lambda *_: None)


def client(fake: FakeUploadThing, **kw: Any) -> UploadThingClient:
    return UploadThingClient(UploadThingCredentials.from_token(TOKEN), transport=fake.transport(), **kw)


def test_token_parsing() -> None:
    creds = UploadThingCredentials.from_token(TOKEN)
    assert creds.app_id == APP_ID and creds.api_key.startswith("sk_")
    with pytest.raises(UploadThingError):
        UploadThingCredentials.from_token("not-a-token")


def test_upload_download_delete_roundtrip(tmp_path: Any) -> None:
    fake = FakeUploadThing()
    c = client(fake)
    data = b"%PDF-1.7 raw bytes \x00\x01\x02" * 1000
    c.upload(io.BytesIO(data), "o1-d2-abc.pdf", "invoice.pdf", "application/pdf")
    assert fake.files["o1-d2-abc.pdf"] == data  # stored byte-for-byte under our customId
    out = tmp_path / "dl.bin"
    c.download_to_file("o1-d2-abc.pdf", str(out))
    assert out.read_bytes() == data
    assert b"".join(c.iter_object("o1-d2-abc.pdf", 4096)) == data
    assert c.delete(["o1-d2-abc.pdf"]) == 1
    with pytest.raises(UploadThingError) as exc:
        c.download_to_file("o1-d2-abc.pdf", str(out))
    assert exc.value.code == "STORAGE_OBJECT_MISSING"


def test_prepare_sends_custom_id_acl_and_size() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"key": "k", "url": "https://sea1.ingest.uploadthing.com/k"})

    c = UploadThingClient(UploadThingCredentials.from_token(TOKEN), transport=httpx.MockTransport(handler))
    c.prepare_upload("my-id", "a.pdf", 123, "application/pdf", 600)
    assert seen == {
        "fileName": "a.pdf",
        "fileSize": 123,
        "fileType": "application/pdf",
        "customId": "my-id",
        "contentDisposition": "attachment",
        "acl": "public-read",
        "expiresIn": 600,
    }


def test_oversized_body_is_rejected() -> None:
    fake = FakeUploadThing()
    c = client(fake)
    prepared = c.prepare_upload("x", "a.pdf", 5, "application/pdf")
    with pytest.raises(UploadThingError) as exc:
        c.put(prepared, io.BytesIO(b"0123456789"), "a.pdf", "application/pdf")
    assert exc.value.code == "UPLOAD_SIZE_MISMATCH"


def test_transient_errors_retry_then_succeed_and_auth_errors_do_not() -> None:
    fake = FakeUploadThing()
    fake.fail_next = [503, 429]
    c = client(fake, max_retries=3)
    c.upload(io.BytesIO(b"hello"), "id1", "a.csv", "text/csv")
    assert fake.files["id1"] == b"hello"

    fake.fail_next = [503] * 10
    with pytest.raises(UploadThingUnavailableError):
        client(fake, max_retries=2).delete(["id1"])

    fake.fail_next = []
    bad = UploadThingClient(UploadThingCredentials("sk_wrong", APP_ID, ()), transport=fake.transport())
    with pytest.raises(UploadThingError) as exc:
        bad.delete(["id1"])
    assert exc.value.code == "UPLOADTHING_AUTH_FAILED"


def test_public_acl_refuses_presigned_links() -> None:
    with pytest.raises(UploadThingError) as exc:
        client(FakeUploadThing()).signed_read_url("id", 60)
    assert exc.value.code == "PRESIGNED_UNAVAILABLE"
