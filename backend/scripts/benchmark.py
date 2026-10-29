"""Throughput benchmark against a running deployment.

  python -m scripts.benchmark --api http://localhost:8000 [--native-pages 1000] [--scanned-pages 50]

Generates synthetic documents, uploads them, waits for completion, and
records wall-clock time, pages/second, stage timings (from the job's stage
history) and peak container memory (sampled via ``docker stats`` when
available). Results are written to evaluation/results/benchmark-<timestamp>.json.
Numbers describe this machine and configuration only.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from evaluation.synthetic import InvoiceSpec, invoice_pdf_bytes, random_invoice, scanned_pdf_bytes

TERMINAL = {"COMPLETED", "COMPLETED_WITH_WARNINGS", "REQUIRES_REVIEW", "FAILED", "CANCELLED"}


def build_native(pages: int, pages_per_invoice: int = 4) -> tuple[bytes, list[InvoiceSpec]]:
    rng = random.Random(1000)
    specs = []
    for i in range(pages // pages_per_invoice):
        spec = random_invoice(rng, 50_000 + i, date_style="iso")
        spec.lines = (spec.lines * 200)[: 18 * pages_per_invoice - 4]
        specs.append(spec)
    return invoice_pdf_bytes(specs), specs


def build_scanned(pages: int) -> bytes:
    rng = random.Random(2000)
    specs = [random_invoice(rng, 60_000 + i, date_style="iso") for i in range(pages)]
    return scanned_pdf_bytes(invoice_pdf_bytes(specs), seed=7)


class MemorySampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.peak: dict[str, float] = {}
        self.stop = threading.Event()

    @staticmethod
    def _mib(value: str) -> float:
        value = value.strip()
        units = {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "kB": 1 / 1000, "MB": 1, "GB": 1000, "B": 1 / (1024 * 1024)}
        for unit, factor in units.items():
            if value.endswith(unit):
                return float(value[: -len(unit)]) * factor
        return 0.0

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                out = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.MemUsage}}"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                ).stdout
            except (OSError, subprocess.TimeoutExpired):
                return
            for line in out.splitlines():
                name, _, usage = line.partition("|")
                if "docintel" in name:
                    mib = self._mib(usage.split("/")[0])
                    self.peak[name] = max(self.peak.get(name, 0.0), mib)
            time.sleep(2)


def run_one(client: httpx.Client, h: dict[str, str], name: str, data: bytes, timeout: float) -> dict[str, Any]:
    t0 = time.monotonic()
    r = client.post("/api/v1/documents/upload", headers=h, files=[("files", (name, data, "application/pdf"))])
    r.raise_for_status()
    res = r.json()["results"][0]
    upload_s = time.monotonic() - t0
    deadline = time.monotonic() + timeout
    job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        job = client.get(res["status_url"], headers=h).json()
        if job["state"] in TERMINAL:
            break
        time.sleep(2)
    total_s = time.monotonic() - t0
    history = job.get("stage_history_json", [])
    stages: dict[str, float] = {}
    for prev, cur in zip(history, history[1:], strict=False):
        stages[prev["to"]] = round((datetime.fromisoformat(cur["at"]) - datetime.fromisoformat(prev["at"])).total_seconds(), 2)
    invoices = client.get(f"/api/v1/documents/{res['document_id']}/invoices", headers=h).json()
    return {
        "file": name,
        "bytes": len(data),
        "state": job.get("state"),
        "pages_total": job.get("pages_total"),
        "pages_completed": job.get("pages_completed"),
        "pages_failed": job.get("pages_failed"),
        "upload_seconds": round(upload_s, 2),
        "end_to_end_seconds": round(total_s, 2),
        "pages_per_second": round((job.get("pages_completed") or 0) / total_s, 2) if total_s else None,
        "stage_seconds": stages,
        "invoices_extracted": len(invoices),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--native-pages", type=int, default=1000)
    parser.add_argument("--scanned-pages", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args()

    native, specs = build_native(args.native_pages)
    scanned = build_scanned(args.scanned_pages) if args.scanned_pages else b""
    sampler = MemorySampler()
    sampler.start()
    with httpx.Client(base_url=args.api, timeout=300) as client:
        email, password = f"bench-{uuid.uuid4().hex[:8]}@example.com", "Benchmark-Password-1"
        client.post(
            "/api/v1/auth/register", json={"organization_name": "Benchmark", "email": email, "password": password, "full_name": "Bench"}
        ).raise_for_status()
        token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        runs = [run_one(client, h, f"native-{args.native_pages}p.pdf", native, args.timeout)]
        runs[0]["invoices_expected"] = len(specs)
        if scanned:
            runs.append(run_one(client, h, f"scanned-{args.scanned_pages}p.pdf", scanned, args.timeout))
            runs[-1]["invoices_expected"] = args.scanned_pages
    sampler.stop.set()
    sampler.join(5)
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "machine": {"platform": platform.platform(), "processor": platform.machine(), "cpu_count": __import__("os").cpu_count()},
        "note": "Single local Docker Compose stack; synthetic documents; results are specific to this machine and configuration.",
        "runs": runs,
        "peak_container_memory_mib": {k: round(v, 1) for k, v in sorted(sampler.peak.items())},
    }
    out = Path("evaluation/results") / f"benchmark-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"written: {out}")


if __name__ == "__main__":
    main()
