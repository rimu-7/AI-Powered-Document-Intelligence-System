"""End-to-end evaluation against a running deployment, through the public API.

  uv run python -m evaluation.evaluate --api http://localhost:8000

Uploads every file in ``evaluation/dataset`` (multipart, as a client would),
waits for the background jobs, then scores the API's results against
``labels.json``:

* document outcomes: success rate, failure rate, correct handling of corrupted files
* extraction: per-field precision / recall / F1, invoice detection, line items
* validation: detection of injected arithmetic errors, review-flag rate
* spreadsheets: rows parsed
* cross-verification: PDF↔PDF comparison and PDF↔spreadsheet reconciliation counts
* processing time per document type (from job timestamps)

Writes ``evaluation/results/evaluation-<timestamp>.json`` and ``.md``.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

DATASET = Path(__file__).parent / "dataset"
RESULTS = Path(__file__).parent / "results"
SUCCESS = {"COMPLETED", "COMPLETED_WITH_WARNINGS", "REQUIRES_REVIEW"}
TERMINAL = SUCCESS | {"FAILED", "CANCELLED"}
FIELDS = ("invoice_number", "invoice_date", "supplier_name", "customer_name", "currency", "subtotal", "tax_amount", "total_amount")
AMOUNTS = {"subtotal", "tax_amount", "total_amount"}
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".tiff": "image/tiff",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
}


def norm(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in AMOUNTS or field == "line_total":
        return Decimal(str(value)).normalize()
    return " ".join(str(value).split()).casefold()


def key(number: Any) -> str:
    return "".join(ch for ch in str(number or "").upper() if ch.isalnum())


class Client:
    def __init__(self, api: str) -> None:
        self.http = httpx.Client(base_url=api.rstrip("/") + "/api/v1", timeout=120)
        self.h: dict[str, str] = {}

    def login_new_org(self) -> None:
        email, password = f"eval-{uuid.uuid4().hex[:8]}@example.com", "Evaluation-Password-1"
        self.http.post(
            "/auth/register", json={"organization_name": "Evaluation", "email": email, "password": password, "full_name": "Evaluator"}
        ).raise_for_status()
        token = self.http.post("/auth/login", json={"email": email, "password": password}).raise_for_status().json()["access_token"]
        self.h = {"Authorization": f"Bearer {token}"}

    def get(self, path: str, **kw: Any) -> Any:
        r = self.http.get(path, headers=self.h, **kw)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, **kw: Any) -> httpx.Response:
        return self.http.post(path, headers=self.h, **kw)

    def wait(self, job_id: str, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            job = self.get(f"/jobs/{job_id}")
            if job["state"] in TERMINAL or time.monotonic() > deadline:
                return dict(job)
            time.sleep(1.0)


def seconds(job: dict[str, Any]) -> float | None:
    if not job.get("completed_at"):
        return None
    return (datetime.fromisoformat(job["completed_at"]) - datetime.fromisoformat(job["created_at"])).total_seconds()


def pct(a: float, b: float) -> float | None:
    return round(100 * a / b, 1) if b else None


def run(api: str, timeout: float) -> dict[str, Any]:
    labels = json.loads((DATASET / "labels.json").read_text())["files"]
    c = Client(api)
    c.login_new_org()
    started = time.monotonic()

    # 1. Upload (batches of 10 files per request).
    uploads: dict[str, dict[str, Any]] = {}
    for i in range(0, len(labels), 10):
        batch = labels[i : i + 10]
        files = [("files", (f["file"], (DATASET / f["file"]).read_bytes(), CONTENT_TYPES[Path(f["file"]).suffix])) for f in batch]
        r = c.post("/documents/upload", files=files)
        for item in r.json()["results"]:
            uploads[item["filename"]] = item

    # 2. Wait for processing.
    jobs: dict[str, dict[str, Any]] = {}
    for name, item in uploads.items():
        if item["status"] == "accepted":
            jobs[name] = c.wait(item["job_id"], timeout)

    # 3. Cross-verification jobs.
    doc_of = {name: item.get("document_id") for name, item in uploads.items()}
    cross: dict[str, Any] = {}
    pair = sorted((f for f in labels if f.get("comparison_group")), key=lambda f: f["comparison_side"])
    if len(pair) == 2:
        r = c.post("/comparisons", json={"left_document_id": doc_of[pair[0]["file"]], "right_document_id": doc_of[pair[1]["file"]]})
        if r.status_code == 202:
            job = c.wait(r.json()["job_id"], timeout)
            cross["pdf_pdf"] = {
                "state": job["state"],
                "summary": c.get(f"/comparisons/{r.json()['comparison_id']}")["summary_json"],
                "expected_mismatched_records": pair[1]["expected_mismatched_records"],
            }
        else:
            cross["pdf_pdf"] = {"error": r.json()}
    recon_pdfs = [doc_of[f["file"]] for f in labels if f.get("reconciliation_role") == "pdf"]
    register = next(f for f in labels if f.get("reconciliation_role") == "register")
    r = c.post("/reconciliations", json={"pdf_document_ids": recon_pdfs, "spreadsheet_document_id": doc_of[register["file"]]})
    if r.status_code == 202:
        job = c.wait(r.json()["job_id"], timeout)
        summary = c.get(f"/reconciliations/{r.json()['comparison_id']}")["summary_json"]
        expected = register["expected_reconciliation"]
        cross["pdf_spreadsheet"] = {
            "state": job["state"],
            "summary": summary,
            "expected": expected,
            "all_counts_correct": all(summary.get(k) == v for k, v in expected.items()),
        }
    else:
        cross["pdf_spreadsheet"] = {"error": r.json()}
    wall = time.monotonic() - started

    # 4. Score.
    docs: list[dict[str, Any]] = []
    field_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_kind_acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    inv_expected = inv_found = inv_matched = inv_exact = 0
    line_expected = line_found = 0
    arith = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    times: dict[str, list[float]] = defaultdict(list)
    pages_total = 0
    for label in labels:
        name = label["file"]
        up = uploads.get(name, {"status": "missing"})
        job = jobs.get(name)
        state = job["state"] if job else ("REJECTED_AT_UPLOAD" if up["status"] == "rejected" else "NOT_UPLOADED")
        error = (job or {}).get("error_code") or (up.get("error") or {}).get("code")
        row: dict[str, Any] = {"file": name, "kind": label["kind"], "expected": label["expect"], "state": state, "error_code": error}
        if job:
            t = seconds(job)
            row["seconds"] = round(t, 2) if t is not None else None
            if t is not None and state in SUCCESS:
                times[label["kind"]].append(t)
                pages_total += job.get("pages_total") or 0
        if label["expect"] == "processed":
            row["outcome_ok"] = state in SUCCESS
        elif label["expect"] == "review":
            doc_issues = (
                {i["rule_code"] for i in c.get(f"/documents/{doc_of[name]}/validations", params={"limit": 200})["items"]}
                if state in SUCCESS
                else set()
            )
            row["outcome_ok"] = state == "REQUIRES_REVIEW" and label.get("expected_error") in doc_issues
        else:
            row["outcome_ok"] = (
                state == "FAILED" if label["expect"] == "failed" else state == "REJECTED_AT_UPLOAD"
            ) and error == label.get("expected_error")
        if label.get("register_rows") and state in SUCCESS:
            tables = c.get(f"/documents/{doc_of[name]}/tables")["items"]
            row["rows_parsed"] = sum(t["row_count"] for t in tables)
            row["rows_expected"] = label["register_rows"]
        if label["invoices"] and state in SUCCESS:
            extracted = c.get(f"/documents/{doc_of[name]}/invoices")
            row["invoices_expected"], row["invoices_found"] = len(label["invoices"]), len(extracted)
            row["requires_review"] = state == "REQUIRES_REVIEW"
            inv_expected += len(label["invoices"])
            inv_found += len(extracted)
            remaining = list(extracted)
            for truth in label["invoices"]:
                match = next((e for e in remaining if key(e["invoice_number"]) == key(truth["invoice_number"])), None)
                if match is None and len(label["invoices"]) == 1 and remaining:
                    match = remaining[0]
                for field in FIELDS:
                    t, p = norm(field, truth.get(field)), norm(field, match.get(field)) if match else None
                    s = field_stats[field]
                    s["truth"] += t is not None
                    s["predicted"] += p is not None
                    s["correct"] += p is not None and p == t
                    per_kind_acc[label["kind"]][0] += p is not None and p == t
                    per_kind_acc[label["kind"]][1] += t is not None
                if match is None:
                    continue
                remaining.remove(match)
                inv_matched += 1
                inv_exact += all(norm(f, truth.get(f)) == norm(f, match.get(f)) for f in FIELDS)
                lines = c.get(f"/invoices/{match['id']}/line-items")
                predicted_totals = [norm("line_total", li["line_total"]) for li in lines if li["line_total"] is not None]
                for li in truth["line_items"]:
                    line_expected += 1
                    if norm("line_total", li["line_total"]) in predicted_totals:
                        line_found += 1
                        predicted_totals.remove(norm("line_total", li["line_total"]))
                issues = {i["rule_code"] for i in c.get(f"/invoices/{match['id']}/validations", params={"limit": 200})["items"]}
                flagged = bool(issues & {"TOTAL_MISMATCH", "SUBTOTAL_MISMATCH", "LINE_TOTAL_MISMATCH", "TAX_MISMATCH"})
                positive = bool(truth.get("arithmetic_error"))
                arith["tp" if positive and flagged else "fn" if positive else "fp" if flagged else "tn"] += 1
        docs.append(row)

    processable = [d for d in docs if d["expected"] == "processed"]
    corrupt = [d for d in docs if d["expected"] != "processed"]
    accepted_jobs = [d for d in docs if d["state"] not in ("REJECTED_AT_UPLOAD", "NOT_UPLOADED")]
    fields = {}
    for f, s in field_stats.items():
        precision = s["correct"] / s["predicted"] if s["predicted"] else None
        recall = s["correct"] / s["truth"] if s["truth"] else None
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
        fields[f] = {
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
            "n": s["truth"],
        }
    all_times = [t for ts in times.values() for t in ts]
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "api": api,
        "dataset": {
            "files": len(labels),
            "kinds": {k: sum(1 for f in labels if f["kind"] == k) for k in sorted({f["kind"] for f in labels})},
        },
        "documents": {
            "success_rate_pct": pct(sum(d["outcome_ok"] for d in processable), len(processable)),
            "failure_rate_pct": pct(sum(d["state"] == "FAILED" for d in accepted_jobs), len(accepted_jobs)),
            "unexpected_failures": [d["file"] for d in processable if not d["outcome_ok"]],
            "corrupted_files_handled_correctly": f"{sum(d['outcome_ok'] for d in corrupt)}/{len(corrupt)}",
            "requires_review": sum(1 for d in docs if d.get("requires_review")),
        },
        "extraction": {
            "micro_f1": _micro_f1(field_stats),
            "fields": fields,
            "accuracy_by_kind_pct": {k: pct(v[0], v[1]) for k, v in per_kind_acc.items()},
            "invoice_detection": {
                "expected": inv_expected,
                "found": inv_found,
                "matched": inv_matched,
                "recall_pct": pct(inv_matched, inv_expected),
            },
            "invoices_all_fields_correct_pct": pct(inv_exact, inv_matched),
            "line_total_recall_pct": pct(line_found, line_expected),
        },
        "validation": {
            "arithmetic_error_detection": {
                **arith,
                "recall_pct": pct(arith["tp"], arith["tp"] + arith["fn"]),
                "false_positive_rate_pct": pct(arith["fp"], arith["fp"] + arith["tn"]),
            }
        },
        "spreadsheets": [{k: d[k] for k in ("file", "rows_parsed", "rows_expected")} for d in docs if "rows_parsed" in d],
        "cross_verification": cross,
        "processing_time_seconds": {
            "by_kind": {
                k: {"n": len(v), "mean": round(statistics.mean(v), 2), "p50": round(statistics.median(v), 2), "max": round(max(v), 2)}
                for k, v in sorted(times.items())
            },
            "overall_mean": round(statistics.mean(all_times), 2) if all_times else None,
            "overall_p95": round(sorted(all_times)[max(0, int(len(all_times) * 0.95) - 1)], 2) if all_times else None,
            "wall_clock_total": round(wall, 1),
            "pages_processed": pages_total,
        },
        "per_document": docs,
    }
    return report


def _micro_f1(stats: dict[str, dict[str, int]]) -> float | None:
    correct = sum(s["correct"] for s in stats.values())
    predicted = sum(s["predicted"] for s in stats.values())
    truth = sum(s["truth"] for s in stats.values())
    if not predicted or not truth:
        return None
    p, r = correct / predicted, correct / truth
    return round(2 * p * r / (p + r), 4) if p + r else 0.0


def markdown(report: dict[str, Any], provider: str) -> str:
    d, e, v, t = (
        report["documents"],
        report["extraction"],
        report["validation"]["arithmetic_error_detection"],
        report["processing_time_seconds"],
    )
    lines = [
        f"# Evaluation run — {report['timestamp'][:19]}Z ({provider})",
        "",
        f"Dataset: {report['dataset']['files']} files {report['dataset']['kinds']}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Document success rate (valid files processed) | {d['success_rate_pct']}% |",
        f"| Job failure rate (all accepted jobs, incl. corrupted files) | {d['failure_rate_pct']}% |",
        f"| Corrupted files handled correctly | {d['corrupted_files_handled_correctly']} |",
        f"| Extraction micro-F1 (8 header fields) | {e['micro_f1']} |",
        f"| Invoices detected | {e['invoice_detection']['matched']}/{e['invoice_detection']['expected']} |",
        f"| Invoices with all 8 fields correct | {e['invoices_all_fields_correct_pct']}% |",
        f"| Line-item totals recovered | {e['line_total_recall_pct']}% |",
        f"| Arithmetic errors detected | {v['tp']}/{v['tp'] + v['fn']} (false-positive rate {v['false_positive_rate_pct']}%) |",
        f"| PDF↔spreadsheet reconciliation counts correct | {report['cross_verification'].get('pdf_spreadsheet', {}).get('all_counts_correct')} |",
        f"| Mean / p95 processing time per document | {t['overall_mean']} s / {t['overall_p95']} s |",
        f"| Wall clock for the whole dataset | {t['wall_clock_total']} s |",
        "",
        "| Field | Precision | Recall | F1 |",
        "|---|---|---|---|",
        *[f"| {k} | {x['precision']} | {x['recall']} | {x['f1']} |" for k, x in e["fields"].items()],
        "",
        "| Document type | Field accuracy | Mean time (s) | n |",
        "|---|---|---|---|",
        *[f"| {k} | {e['accuracy_by_kind_pct'].get(k)}% | {x['mean']} | {x['n']} |" for k, x in t["by_kind"].items()],
    ]
    if d["unexpected_failures"]:
        lines += ["", f"Unexpected failures: {', '.join(d['unexpected_failures'])}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--label", default="", help="free text recorded in the report (e.g. provider/model)")
    args = parser.parse_args()
    report = run(args.api, args.timeout)
    report["label"] = args.label
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (RESULTS / f"evaluation-{stamp}.json").write_text(json.dumps(report, indent=2, default=str))
    md = markdown(report, args.label or "system")
    (RESULTS / f"evaluation-{stamp}.md").write_text(md)
    print(md)
    print(f"written: evaluation/results/evaluation-{stamp}.json")


if __name__ == "__main__":
    main()
