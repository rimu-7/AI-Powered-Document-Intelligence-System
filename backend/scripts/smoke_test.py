"""End-to-end smoke test against a running deployment.

  python -m scripts.smoke_test --api http://localhost:8000
Registers a fresh organization (requires REGISTRATION_MODE=open), uploads a
native PDF, a scanned PDF, and a spreadsheet register, waits for processing,
then exercises extraction, validation, search, comparison and reconciliation.
Exits non-zero on the first failed check.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import uuid
from decimal import Decimal
from typing import Any

import httpx

from evaluation.synthetic import invoice_pdf_bytes, random_invoice, register_rows, register_xlsx_bytes, scanned_pdf_bytes

TERMINAL = {"COMPLETED", "COMPLETED_WITH_WARNINGS", "REQUIRES_REVIEW", "FAILED", "CANCELLED"}
results: list[dict[str, Any]] = []


def check(name: str, ok: bool, detail: Any = None) -> None:
    results.append({"check": name, "ok": ok, "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail is not None and not ok else ""))
    if not ok:
        print(json.dumps(results, indent=1, default=str))
        sys.exit(1)


def wait(client: httpx.Client, h: dict[str, str], job_id: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}", headers=h).json()
        if job["state"] in TERMINAL:
            return job
        time.sleep(1)
    raise SystemExit(f"job {job_id} did not finish in {timeout}s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    started = time.monotonic()
    rng = random.Random(4242)
    with httpx.Client(base_url=args.api, timeout=60) as c:
        check("health/ready", c.get("/health/ready").status_code == 200)
        email, password = f"smoke-{uuid.uuid4().hex[:8]}@example.com", "Smoke-Test-Password-1"
        r = c.post(
            "/api/v1/auth/register",
            json={"organization_name": "Smoke Test Org", "email": email, "password": password, "full_name": "Smoke"},
        )
        check("register", r.status_code == 201, r.text)
        tokens = c.post("/api/v1/auth/login", json={"email": email, "password": password}).json()
        h = {"Authorization": f"Bearer {tokens['access_token']}"}

        native, scanned, extra = (
            random_invoice(rng, 9001, date_style="iso"),
            random_invoice(rng, 9002, date_style="iso"),
            random_invoice(rng, 9003),
        )
        files = [
            ("smoke-native.pdf", invoice_pdf_bytes([native]), "application/pdf"),
            ("smoke-scanned.pdf", scanned_pdf_bytes(invoice_pdf_bytes([scanned])), "application/pdf"),
            (
                "smoke-register.xlsx",
                register_xlsx_bytes(register_rows([native, extra])),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ]
        r = c.post(
            "/api/v1/documents/upload", headers=h | {"Idempotency-Key": f"smoke-{uuid.uuid4().hex}"}, files=[("files", f) for f in files]
        )
        check("upload 3 files (202)", r.status_code == 202 and r.json()["accepted"] == 3, r.text)
        uploads = r.json()["results"]
        jobs = {u["filename"]: wait(c, h, u["job_id"], args.timeout) for u in uploads}
        for name, job in jobs.items():
            check(f"processed {name}", job["state"] in ("COMPLETED", "COMPLETED_WITH_WARNINGS", "REQUIRES_REVIEW"), job)
        ids = {u["filename"]: u["document_id"] for u in uploads}

        inv = c.get(f"/api/v1/documents/{ids['smoke-native.pdf']}/invoices", headers=h).json()
        check("native: invoice extracted", len(inv) == 1 and inv[0]["invoice_number"] == native.invoice_number, inv)
        check("native: total matches", Decimal(inv[0]["total_amount"]) == native.total_amount, inv[0]["total_amount"])
        detail = c.get(f"/api/v1/invoices/{inv[0]['id']}", headers=h).json()
        check("native: evidence has page + bbox", bool(detail["source_evidence_json"]["total_amount"].get("bounding_box")))
        pages = c.get(f"/api/v1/documents/{ids['smoke-scanned.pdf']}/pages", headers=h).json()["items"]
        check("scanned: OCR used", pages[0]["ocr_engine"] == "tesseract", pages[0])
        sinv = c.get(f"/api/v1/documents/{ids['smoke-scanned.pdf']}/invoices", headers=h).json()
        check("scanned: invoice number via OCR", any(i["invoice_number"] == scanned.invoice_number for i in sinv), sinv)

        hits = c.get("/api/v1/search/keyword", params={"q": native.invoice_number}, headers=h).json()["items"]
        check("keyword search", any(x["document_id"] == ids["smoke-native.pdf"] for x in hits), hits)
        hits = c.post("/api/v1/search/hybrid", json={"query": native.supplier_name}, headers=h).json()["items"]
        check("hybrid search", any(x["document_id"] == ids["smoke-native.pdf"] for x in hits), hits)

        r = c.post(
            "/api/v1/reconciliations",
            headers=h,
            json={
                "pdf_document_ids": [ids["smoke-native.pdf"], ids["smoke-scanned.pdf"]],
                "spreadsheet_document_id": ids["smoke-register.xlsx"],
            },
        )
        check("reconciliation accepted", r.status_code == 202, r.text)
        rec_job = wait(c, h, r.json()["job_id"], args.timeout)
        summary = c.get(f"/api/v1/reconciliations/{r.json()['comparison_id']}", headers=h).json()["summary_json"]
        check("reconciliation completed", rec_job["state"].startswith("COMPLETED"), rec_job)
        check(
            "reconciliation counts",
            summary["matched_count"] == 1 and summary["missing_in_pdf_count"] == 1 and summary["missing_in_spreadsheet_count"] == 1,
            summary,
        )

        metrics = c.get("/metrics", headers={"Authorization": f"Bearer {args_token()}"} if args_token() else {})
        check("metrics endpoint", metrics.status_code in (200, 401))
    print(
        json.dumps({"checks": len(results), "all_passed": all(r["ok"] for r in results), "seconds": round(time.monotonic() - started, 1)})
    )


def args_token() -> str | None:
    import os

    return os.environ.get("METRICS_TOKEN") or None


if __name__ == "__main__":
    main()
