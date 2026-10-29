"""Cross-tenant access must be impossible and must not reveal resource existence."""

from __future__ import annotations

import random
from typing import Any

import pytest

from evaluation.synthetic import invoice_pdf_bytes, random_invoice
from tests.conftest import register_org, upload

pytestmark = pytest.mark.integration


async def test_tenant_isolation_across_all_resources(client: Any, pipeline: Any) -> None:
    a = await register_org(client, "Tenant A")
    b = await register_org(client, "Tenant B")
    spec = random_invoice(random.Random(77), 777, supplier_name="Zyxwvut Secret Supplies Ltd")
    r = await upload(client, a["headers"], [("secret.pdf", invoice_pdf_bytes([spec]), "application/pdf")])
    res = r.json()["results"][0]
    pipeline()
    doc_id, job_id = res["document_id"], res["job_id"]
    inv_id = (await client.get(f"/api/v1/documents/{doc_id}/invoices", headers=a["headers"])).json()[0]["id"]
    other = await upload(
        client, a["headers"], [("other.pdf", invoice_pdf_bytes([random_invoice(random.Random(78), 778)]), "application/pdf")]
    )
    pipeline()
    cmp = await client.post(
        "/api/v1/comparisons",
        headers=a["headers"],
        json={"left_document_id": doc_id, "right_document_id": other.json()["results"][0]["document_id"]},
    )
    comparison_id = cmp.json()["comparison_id"]
    pipeline()

    bh = b["headers"]
    for path in (
        f"/api/v1/documents/{doc_id}",
        f"/api/v1/documents/{doc_id}/download",
        f"/api/v1/documents/{doc_id}/pages",
        f"/api/v1/documents/{doc_id}/text",
        f"/api/v1/documents/{doc_id}/invoices",
        f"/api/v1/documents/{doc_id}/validations",
        f"/api/v1/jobs/{job_id}",
        f"/api/v1/invoices/{inv_id}",
        f"/api/v1/invoices/{inv_id}/line-items",
        f"/api/v1/comparisons/{comparison_id}",
        f"/api/v1/comparisons/{comparison_id}/findings",
    ):
        r = await client.get(path, headers=bh)
        assert r.status_code == 404, (path, r.status_code)  # 404, not 403: existence is not revealed

    assert (await client.post(f"/api/v1/jobs/{job_id}/retry", headers=bh)).status_code == 404
    assert (await client.delete(f"/api/v1/documents/{doc_id}", headers=bh)).status_code == 404
    r = await client.patch(
        f"/api/v1/invoices/{inv_id}/corrections",
        headers=bh,
        json={"expected_version": 1, "reason": "steal", "changes": [{"field_path": "total_amount", "value": "1.00"}]},
    )
    assert r.status_code == 404
    r = await client.post(
        "/api/v1/comparisons", headers=bh, json={"left_document_id": doc_id, "right_document_id": other.json()["results"][0]["document_id"]}
    )
    assert r.status_code == 404

    # Lists only contain the caller's own data.
    assert (await client.get("/api/v1/documents", headers=bh)).json()["total"] == 0
    assert (await client.get("/api/v1/jobs", headers=bh)).json()["total"] == 0
    assert (await client.get("/api/v1/reviews/queue", headers=bh)).json()["total"] == 0

    # Search (keyword, semantic, hybrid) never returns another tenant's chunks.
    for method, path, kwargs in (
        ("get", "/api/v1/search/keyword", {"params": {"q": "Zyxwvut"}}),
        ("post", "/api/v1/search/semantic", {"json": {"query": "Zyxwvut Secret Supplies"}}),
        ("post", "/api/v1/search/hybrid", {"json": {"query": "Zyxwvut Secret Supplies"}}),
    ):
        own = await getattr(client, method)(path, headers=a["headers"], **kwargs)
        assert any(hit["document_id"] == doc_id for hit in own.json()["items"]), path
        theirs = await getattr(client, method)(path, headers=bh, **kwargs)
        assert theirs.status_code == 200 and theirs.json()["items"] == [], path


async def test_client_supplied_org_id_is_ignored(client: Any) -> None:
    a = await register_org(client)
    r = await client.get("/api/v1/documents", headers=a["headers"], params={"organization_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 200


async def test_cross_tenant_foreign_keys_rejected_by_database(configured: Any) -> None:
    """Composite FKs make it impossible to attach a page to another tenant's document."""
    import uuid

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.core.database import sync_session

    with sync_session() as s:
        doc = s.execute(text("SELECT id, organization_id FROM documents LIMIT 1")).first()
        other_org = s.execute(text("SELECT id FROM organizations WHERE id <> :o LIMIT 1"), {"o": doc.organization_id}).scalar_one()
        with pytest.raises(IntegrityError):
            s.execute(
                text(
                    "INSERT INTO document_pages (id, organization_id, document_id, page_number, character_count, processing_status, parser_version, metadata_json, created_at) VALUES (:id, :org, :doc, 99, 0, 'DONE', '1', '{}', now())"
                ),
                {"id": uuid.uuid4(), "org": other_org, "doc": doc.id},
            )
        s.rollback()
