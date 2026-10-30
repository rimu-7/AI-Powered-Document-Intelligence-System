"""End-to-end: upload → pipeline (in-process workers) → extraction, validation,
search, comparison, reconciliation, review."""

from __future__ import annotations

import random
from decimal import Decimal
from typing import Any

import pytest

from evaluation.synthetic import invoice_pdf_bytes, random_invoice, register_rows, register_xlsx_bytes
from tests.conftest import upload

pytestmark = pytest.mark.integration


async def _upload_and_process(client: Any, headers: dict[str, str], pipeline: Any, name: str, data: bytes, ctype: str) -> dict[str, Any]:
    r = await upload(client, headers, [(name, data, ctype)])
    assert r.status_code == 202, r.text
    result = r.json()["results"][0]
    assert result["status"] == "accepted"
    pipeline()
    job = (await client.get(result["status_url"], headers=headers)).json()
    return {"doc_id": result["document_id"], "job": job, "upload": result}


async def test_native_invoice_end_to_end(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    h = org["headers"]
    spec = random_invoice(random.Random(11), 101)
    out = await _upload_and_process(client, h, pipeline, "invoice-101.pdf", invoice_pdf_bytes([spec]), "application/pdf")
    job = out["job"]
    assert job["state"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS"), job
    assert Decimal(job["progress_percent"]) == 100 and job["pages_completed"] == 1
    states = [s["to"] for s in job["stage_history_json"]]
    assert states[:6] == ["PREPROCESSING", "PARSING", "EXTRACTING", "VALIDATING", "INDEXING", job["state"]]

    doc = (await client.get(f"/api/v1/documents/{out['doc_id']}", headers=h)).json()
    assert doc["document_type"] == "INVOICE" and doc["page_count"] == 1 and doc["validation_outcome"] == "PASSED"

    invoices = (await client.get(f"/api/v1/documents/{out['doc_id']}/invoices", headers=h)).json()
    assert len(invoices) == 1
    inv = (await client.get(f"/api/v1/invoices/{invoices[0]['id']}", headers=h)).json()
    assert inv["invoice_number"] == spec.invoice_number
    assert Decimal(inv["total_amount"]) == spec.total_amount
    assert inv["source_evidence_json"]["total_amount"]["page_number"] == 1
    assert inv["source_evidence_json"]["total_amount"]["bounding_box"]
    assert len(inv["line_items"]) == len(spec.lines)
    assert inv["machine_values"]["invoice_number"] == spec.invoice_number

    pages = (await client.get(f"/api/v1/documents/{out['doc_id']}/pages", headers=h)).json()
    assert pages["items"][0]["page_type"] == "NATIVE_TEXT"
    text = (await client.get(f"/api/v1/documents/{out['doc_id']}/text", headers=h)).json()
    assert spec.invoice_number in text[0]["text"]

    img = await client.get(f"/api/v1/documents/{out['doc_id']}/pages/1/image", params={"width": 500}, headers=h)
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp", img.text
    assert img.content[:4] == b"RIFF" and img.content[8:12] == b"WEBP"
    again = await client.get(
        f"/api/v1/documents/{out['doc_id']}/pages/1/image", params={"width": 600}, headers={**h, "If-None-Match": img.headers["etag"]}
    )
    assert again.status_code == 304  # 500 and 600 both round up to the cached 640 px image
    missing = await client.get(f"/api/v1/documents/{out['doc_id']}/pages/9/image", headers=h)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "PAGE_NOT_FOUND"

    dl = await client.get(f"/api/v1/documents/{out['doc_id']}/download", headers=h)
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF") and "attachment" in dl.headers["content-disposition"]

    # Search: keyword, semantic and hybrid all find the invoice.
    r = await client.get("/api/v1/search/keyword", params={"q": spec.supplier_name.split()[0]}, headers=h)
    assert r.status_code == 200 and any(hit["document_id"] == out["doc_id"] for hit in r.json()["items"])
    item = next(hit for hit in r.json()["items"] if hit["document_id"] == out["doc_id"])
    assert item["score_kind"] == "ts_rank_cd" and item["snippet"]
    for mode in ("semantic", "hybrid"):
        r = await client.post(f"/api/v1/search/{mode}", json={"query": spec.lines[0].description}, headers=h)
        assert r.status_code == 200, r.text
        assert any(hit["document_id"] == out["doc_id"] for hit in r.json()["items"])
    r = await client.get(
        "/api/v1/search/keyword", params={"q": spec.invoice_number, "currency": spec.currency, "amount_min": "0"}, headers=h
    )
    assert any(hit["document_id"] == out["doc_id"] for hit in r.json()["items"])
    other = "JPY" if spec.currency != "JPY" else "EUR"
    r = await client.get("/api/v1/search/keyword", params={"q": spec.invoice_number, "currency": other}, headers=h)
    assert all(hit["document_id"] != out["doc_id"] for hit in r.json()["items"])
    r = await client.get("/api/v1/search/keyword", params={"q": spec.invoice_number, "currency": "ZZZ"}, headers=h)
    assert r.status_code == 422  # not a CurrencyCode
    assert (await client.get("/api/v1/search/keyword", params={"q": "  "}, headers=h)).json()["error"]["code"] == "EMPTY_QUERY"
    r = await client.post("/api/v1/search/hybrid", json={"query": "x", "filters": {"colour": "red"}}, headers=h)
    assert r.status_code == 422


async def test_arithmetic_error_goes_to_review_and_correction_flow(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    h = org["headers"]
    spec = random_invoice(random.Random(12), 102)
    spec.total_override = spec.total_amount + Decimal("10.00")
    out = await _upload_and_process(client, h, pipeline, "bad-total.pdf", invoice_pdf_bytes([spec]), "application/pdf")
    assert out["job"]["state"] == "REQUIRES_REVIEW"
    inv = (await client.get(f"/api/v1/documents/{out['doc_id']}/invoices", headers=h)).json()[0]
    issues = (await client.get(f"/api/v1/invoices/{inv['id']}/validations", headers=h)).json()["items"]
    total_issue = next(i for i in issues if i["rule_code"] == "TOTAL_MISMATCH")
    assert Decimal(total_issue["actual_value_json"]) - Decimal(total_issue["expected_value_json"]) == Decimal("10.00")

    queue = (await client.get("/api/v1/reviews/queue", headers=h)).json()
    review = next(x for x in queue["items"] if x["invoice_record_id"] == inv["id"])
    assert "TOTAL_MISMATCH" in review["reason_codes_json"]
    assert (await client.post(f"/api/v1/reviews/{review['id']}/claim", headers=h)).status_code == 200

    # Approval is blocked while ERROR issues are open.
    r = await client.post(f"/api/v1/invoices/{inv['id']}/approve", headers=h, json={"expected_version": inv["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "BLOCKING_ISSUES"

    # Currency corrections must be a CurrencyCode.
    r = await client.patch(
        f"/api/v1/invoices/{inv['id']}/corrections",
        headers=h,
        json={"expected_version": inv["version"], "reason": "fix", "changes": [{"field_path": "currency", "value": "$"}]},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_CORRECTION_VALUE"

    # Stale version is rejected (optimistic locking).
    corrected_total = str(spec.subtotal + spec.tax_amount)
    r = await client.patch(
        f"/api/v1/invoices/{inv['id']}/corrections",
        headers=h,
        json={
            "expected_version": inv["version"] + 5,
            "reason": "fix",
            "changes": [{"field_path": "total_amount", "value": corrected_total}],
        },
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "VERSION_CONFLICT"
    r = await client.patch(
        f"/api/v1/invoices/{inv['id']}/corrections",
        headers=h,
        json={
            "expected_version": inv["version"],
            "reason": "Total misprinted; confirmed with supplier",
            "changes": [{"field_path": "total_amount", "value": corrected_total}],
        },
    )
    assert r.status_code == 200, r.text
    corrected = r.json()
    assert corrected["invoice"]["version"] == inv["version"] + 1
    assert corrected["invoice"]["review_status"] == "IN_REVIEW"
    assert corrected["invoice"]["corrected_fields_json"] == ["total_amount"]
    # Machine output is preserved unchanged.
    assert Decimal(corrected["invoice"]["machine_values"]["total_amount"]) == spec.total_override

    pipeline()  # revalidation job
    reval = (await client.get(corrected["status_url"], headers=h)).json()
    assert reval["job_type"] == "REVALIDATION" and reval["state"] in ("REQUIRES_REVIEW", "COMPLETED")
    open_issues = (await client.get(f"/api/v1/invoices/{inv['id']}/validations", headers=h)).json()["items"]
    assert not any(i["rule_code"] == "TOTAL_MISMATCH" for i in open_issues)

    current = (await client.get(f"/api/v1/invoices/{inv['id']}", headers=h)).json()
    r = await client.post(
        f"/api/v1/invoices/{inv['id']}/approve", headers=h, json={"expected_version": current["version"], "reason": "verified"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["review_status"] == "APPROVED" and r.json()["approved_by"]
    history = (await client.get(f"/api/v1/invoices/{inv['id']}/history", headers=h)).json()
    assert [a["action_type"] for a in history] == ["ASSIGNMENT", "CORRECTION", "APPROVAL"]
    assert Decimal(history[1]["old_value_json"]) == spec.total_override
    doc = (await client.get(f"/api/v1/documents/{out['doc_id']}", headers=h)).json()
    assert doc["status"] == "COMPLETED"
    audit = (await client.get("/api/v1/admin/audit-events", params={"resource_id": inv["id"]}, headers=h)).json()
    assert {"invoice.corrected", "invoice.approved"} <= {e["action"] for e in audit["items"]}


async def test_duplicate_invoice_and_file_detection(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    h = org["headers"]
    data = invoice_pdf_bytes([random_invoice(random.Random(13), 103)])
    await _upload_and_process(client, h, pipeline, "a.pdf", data, "application/pdf")
    second = await _upload_and_process(client, h, pipeline, "a-copy.pdf", data, "application/pdf")
    assert second["upload"]["duplicate_of_document_ids"]
    issues = (await client.get(f"/api/v1/documents/{second['doc_id']}/validations", headers=h)).json()["items"]
    codes = {(i["rule_code"], i["severity"]) for i in issues}
    assert ("DUPLICATE_FILE", "WARNING") in codes
    assert ("DUPLICATE_INVOICE", "CRITICAL") in codes
    dup = next(i for i in issues if i["rule_code"] == "DUPLICATE_INVOICE")
    assert dup["details_json"]["other_filename"] == "a.pdf" and "'a.pdf'" in dup["message"]
    assert second["job"]["state"] == "REQUIRES_REVIEW"


async def test_pdf_to_pdf_comparison(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    h = org["headers"]
    spec = random_invoice(random.Random(14), 104)
    left = await _upload_and_process(client, h, pipeline, "left.pdf", invoice_pdf_bytes([spec]), "application/pdf")
    spec.lines[0].unit_price += Decimal("1.00")
    right = await _upload_and_process(client, h, pipeline, "right.pdf", invoice_pdf_bytes([spec]), "application/pdf")
    r = await client.post("/api/v1/comparisons", headers=h, json={"left_document_id": left["doc_id"], "right_document_id": right["doc_id"]})
    assert r.status_code == 202, r.text
    accepted = r.json()
    pipeline()
    comparison = (await client.get(f"/api/v1/comparisons/{accepted['comparison_id']}", headers=h)).json()
    assert comparison["status"] == "COMPLETED"
    assert comparison["summary_json"]["mismatched_count"] == 1
    findings = (
        await client.get(f"/api/v1/comparisons/{accepted['comparison_id']}/findings", headers=h, params={"finding_status": "MISMATCH"})
    ).json()["items"]
    fields = {f["field_name"] for f in findings}
    assert {"subtotal", "total_amount", "__record__"} <= fields
    total = next(f for f in findings if f["field_name"] == "total_amount")
    assert total["evidence_json"]["left"]["field"]["page_number"] == 1


async def test_pdf_to_spreadsheet_reconciliation(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    h = org["headers"]
    rng = random.Random(15)
    specs = [random_invoice(rng, 200 + i) for i in range(3)]
    pdf_ids = []
    for spec in specs[:2]:
        pdf_ids.append(
            (await _upload_and_process(client, h, pipeline, f"{spec.invoice_number}.pdf", invoice_pdf_bytes([spec]), "application/pdf"))[
                "doc_id"
            ]
        )
    rows = register_rows([specs[0], specs[2]])  # specs[1] missing from the register
    rows[0][6] = str(Decimal(rows[0][6]) + Decimal("5.00"))  # amount differs
    rows.append(list(rows[1]))  # duplicate row
    sheet = await _upload_and_process(
        client, h, pipeline, "register.xlsx", register_xlsx_bytes(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert sheet["job"]["state"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS"), sheet["job"]
    sdoc = (await client.get(f"/api/v1/documents/{sheet['doc_id']}", headers=h)).json()
    assert sdoc["document_type"] == "SPREADSHEET_REGISTER"
    suggestions = (await client.get(f"/api/v1/documents/{sheet['doc_id']}/spreadsheet/mapping-suggestions", headers=h)).json()
    mapping = suggestions[0]["suggested_mapping"]
    assert mapping["invoice_number"] == "Invoice No" and mapping["total_amount"] == "Invoice Total"

    r = await client.post(
        "/api/v1/reconciliations",
        headers=h | {"Idempotency-Key": "recon-key-0001"},
        json={"pdf_document_ids": pdf_ids, "spreadsheet_document_id": sheet["doc_id"], "column_mapping": mapping},
    )
    assert r.status_code == 202, r.text
    replay = await client.post(
        "/api/v1/reconciliations",
        headers=h | {"Idempotency-Key": "recon-key-0001"},
        json={"pdf_document_ids": pdf_ids, "spreadsheet_document_id": sheet["doc_id"], "column_mapping": mapping},
    )
    assert replay.json() == r.json() and replay.headers.get("Idempotent-Replay") == "true"
    rid = r.json()["comparison_id"]
    pipeline()
    recon = (await client.get(f"/api/v1/reconciliations/{rid}", headers=h)).json()
    s = recon["summary_json"]
    assert recon["status"] == "COMPLETED"
    assert s["mismatched_count"] == 1
    assert s["missing_in_spreadsheet_count"] == 1
    assert s["missing_in_pdf_count"] == 1
    assert s["duplicate_count"] == 1
    findings = (await client.get(f"/api/v1/reconciliations/{rid}/findings", headers=h, params={"records_only": True})).json()["items"]
    missing_pdf = next(f for f in findings if f["status"] == "MISSING_LEFT")
    assert missing_pdf["evidence_json"]["right"]["sheet_name"] == "AP Register" and missing_pdf["evidence_json"]["right"]["row_number"] >= 4
    csv_out = await client.get(f"/api/v1/reconciliations/{rid}/export.csv", headers=h)
    assert csv_out.status_code == 200 and csv_out.text.startswith('"position"')

    # Bad mapping is rejected with suggestions.
    r = await client.post(
        "/api/v1/reconciliations",
        headers=h,
        json={"pdf_document_ids": pdf_ids, "spreadsheet_document_id": sheet["doc_id"], "column_mapping": {"invoice_number": "Nope"}},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_COLUMN_MAPPING"

    # Correcting an invoice marks the reconciliation stale.
    inv = (await client.get(f"/api/v1/documents/{pdf_ids[0]}/invoices", headers=h)).json()[0]
    r = await client.patch(
        f"/api/v1/invoices/{inv['id']}/corrections",
        headers=h,
        json={
            "expected_version": inv["version"],
            "reason": "supplier typo",
            "changes": [{"field_path": "supplier_name", "value": inv["supplier_name"] + " "}],
        },
    )
    assert r.status_code == 200 and r.json()["stale_comparisons"] >= 1
    assert (await client.get(f"/api/v1/reconciliations/{rid}", headers=h)).json()["status"] == "STALE"


async def test_upload_rejections_and_idempotency(client: Any, org: dict[str, Any], settings_override: Any) -> None:
    h = org["headers"]
    r = await upload(client, h, [("evil.pdf", b"MZ\x90\x00binary", "application/pdf"), ("x.exe", b"MZ", "application/octet-stream")])
    assert r.status_code == 422
    assert [x["error"]["code"] for x in r.json()["results"]] == ["CONTENT_SIGNATURE_MISMATCH", "UNSUPPORTED_FILE_TYPE"]

    data = invoice_pdf_bytes([random_invoice(random.Random(16), 105)])
    headers = h | {"Idempotency-Key": "upload-key-00001"}
    first = await client.post("/api/v1/documents/upload", headers=headers, files=[("files", ("i.pdf", data, "application/pdf"))])
    again = await client.post("/api/v1/documents/upload", headers=headers, files=[("files", ("i.pdf", data, "application/pdf"))])
    assert first.status_code == 202 and again.status_code == 202
    assert again.json() == first.json() and again.headers["Idempotent-Replay"] == "true"
    other = await client.post("/api/v1/documents/upload", headers=headers, files=[("files", ("other.pdf", data + b" ", "application/pdf"))])
    assert other.status_code == 422 and other.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_request_size_limit(client: Any, org: dict[str, Any], settings_override: Any) -> None:
    settings_override(UPLOAD_MAX_REQUEST_BYTES="2048", UPLOAD_MAX_FILE_BYTES="1024")
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        r = await c.post(
            "/api/v1/documents/upload", headers=org["headers"], files=[("files", ("big.csv", b"a,b\n" + b"1,2\n" * 2000, "text/csv"))]
        )
        assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
        r = await c.post(
            "/api/v1/documents/upload", headers=org["headers"], files=[("files", ("mid.csv", b"a,b\n" + b"1,2\n" * 300, "text/csv"))]
        )
        assert r.status_code == 422 and r.json()["results"][0]["error"]["code"] == "FILE_TOO_LARGE"


async def test_delete_removes_from_search_and_access(client: Any, org: dict[str, Any], pipeline: Any) -> None:
    h = org["headers"]
    spec = random_invoice(random.Random(17), 106)
    out = await _upload_and_process(client, h, pipeline, "del.pdf", invoice_pdf_bytes([spec]), "application/pdf")
    assert (await client.delete(f"/api/v1/documents/{out['doc_id']}", headers=h)).status_code == 204
    assert (await client.get(f"/api/v1/documents/{out['doc_id']}", headers=h)).status_code == 404
    r = await client.get("/api/v1/search/keyword", params={"q": spec.invoice_number}, headers=h)
    assert all(hit["document_id"] != out["doc_id"] for hit in r.json()["items"])
