"""Build the labeled evaluation dataset (deterministic; output is committed).

  uv run python -m evaluation.build_dataset

Writes ``evaluation/dataset/`` with 37 files covering every supported format
(native/scanned/multi-invoice PDF, PNG, JPG, single/multi-page TIFF, XLSX,
XLS, CSV), credit notes, injected arithmetic errors, corrupted files, a
PDF↔PDF comparison pair and a PDF↔spreadsheet reconciliation set, plus
``labels.json`` with the expected outcome of every file.
"""

from __future__ import annotations

import json
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

import pymupdf

from evaluation.synthetic import (
    InvoiceSpec,
    image_bytes,
    invoice_pdf_bytes,
    random_invoice,
    register_csv_bytes,
    register_rows,
    register_xls_bytes,
    register_xlsx_bytes,
    scanned_pdf_bytes,
)

OUT = Path(__file__).parent / "dataset"
SEED = 2026


def _invoice_labels(specs: list[InvoiceSpec]) -> list[dict[str, Any]]:
    return [s.ground_truth() for s in specs]


def build() -> dict[str, Any]:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()
    files: list[dict[str, Any]] = []
    counter = iter(range(1, 10_000))

    def spec(**kw: Any) -> InvoiceSpec:
        return random_invoice(rng, 7000 + next(counter), **kw)

    def add(name: str, data: bytes, kind: str, expect: str, invoices: list[InvoiceSpec] | None = None, **extra: Any) -> None:
        (OUT / name).write_bytes(data)
        files.append({"file": name, "kind": kind, "expect": expect, "invoices": _invoice_labels(invoices or []), **extra})

    # Native PDFs: varied suppliers, currencies, date and number styles.
    for i in range(10):
        s = spec(kind="CREDIT_NOTE") if i in (3, 7) else spec()
        if i in (4, 8):
            s.total_override = s.total_amount + Decimal("10.00")  # injected arithmetic error
        add(f"native_{i + 1:02d}.pdf", invoice_pdf_bytes([s]), "native_pdf", "processed", [s])

    # One PDF with three invoices, the second spanning two pages.
    multi = [spec(), spec(), spec()]
    multi[1].lines = (multi[1].lines * 30)[:26]
    add("multi_invoice.pdf", invoice_pdf_bytes(multi), "multi_invoice_pdf", "processed", multi)

    # Scanned PDFs and images (rendered, rotated, blurred).
    for i in range(4):
        s = spec()
        add(f"scanned_{i + 1:02d}.pdf", scanned_pdf_bytes(invoice_pdf_bytes([s]), seed=i), "scanned_pdf", "processed", [s])
    for i in range(3):
        s = spec()
        add(f"photo_{i + 1:02d}.png", image_bytes(invoice_pdf_bytes([s]), "PNG", seed=10 + i), "png", "processed", [s])
    for i in range(2):
        s = spec()
        add(f"photo_{i + 1:02d}.jpg", image_bytes(invoice_pdf_bytes([s]), "JPEG", seed=20 + i), "jpg", "processed", [s])
    s = spec()
    add("scan_single.tiff", image_bytes(invoice_pdf_bytes([s]), "TIFF", seed=30), "tiff", "processed", [s])
    pair = [spec(), spec()]
    add("scan_multipage.tiff", image_bytes(invoice_pdf_bytes(pair), "TIFF", seed=31), "tiff_multipage", "processed", pair, pages=2)

    # Spreadsheet registers (XLSX with title rows, legacy XLS, CSV).
    reg_specs = [spec() for _ in range(6)]
    rows = register_rows(reg_specs)
    add("register.xlsx", register_xlsx_bytes(rows), "xlsx", "processed", register_rows=len(rows))
    add("register.xls", register_xls_bytes(rows[:4]), "xls", "processed", register_rows=4)
    add("register.csv", register_csv_bytes(rows[:5], delimiter=";"), "csv", "processed", register_rows=5)

    # PDF↔PDF comparison: same invoice, second version has one changed unit price.
    original = spec(date_style="iso")
    add(
        "compare_v1.pdf",
        invoice_pdf_bytes([original]),
        "native_pdf",
        "processed",
        [original],
        comparison_group="pair",
        comparison_side="left",
    )
    revised = InvoiceSpec(**{**original.__dict__, "lines": [type(li)(li.description, li.quantity, li.unit_price) for li in original.lines]})
    revised.lines[0].unit_price += Decimal("5.00")
    add(
        "compare_v2.pdf",
        invoice_pdf_bytes([revised]),
        "native_pdf",
        "processed",
        [revised],
        comparison_group="pair",
        comparison_side="right",
        expected_mismatched_records=1,
    )

    # PDF↔spreadsheet reconciliation: 4 invoices vs a register with 1 changed amount,
    # 1 invoice missing from the register, 1 row with no PDF, 1 duplicate row.
    recon = [spec(date_style="iso") for _ in range(4)]
    for j, r in enumerate(recon):
        add(f"recon_invoice_{j + 1}.pdf", invoice_pdf_bytes([r]), "native_pdf", "processed", [r], reconciliation_role="pdf")
    extra = spec(date_style="iso")
    reg = register_rows([recon[0], recon[1], recon[2], extra])
    reg[1][6] = str(Decimal(reg[1][6]) + Decimal("25.00"))
    reg.append(list(reg[0]))
    add(
        "recon_register.xlsx",
        register_xlsx_bytes(reg),
        "xlsx",
        "processed",
        register_rows=len(reg),
        reconciliation_role="register",
        expected_reconciliation={
            "matched_count": 2,
            "mismatched_count": 1,
            "missing_in_spreadsheet_count": 1,
            "missing_in_pdf_count": 1,
            "duplicate_count": 1,
        },
    )

    # Corrupted / hostile files.
    good = invoice_pdf_bytes([spec()])
    # Truncated: recoverable by repair, so it must be processed AND sent to review.
    add("corrupt_truncated.pdf", good[: len(good) // 3], "corrupt", "review", expected_error="PDF_REPAIRED")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Invoice No: SECRET-1  Total 10.00")
    add(
        "corrupt_encrypted.pdf",
        doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="own"),
        "corrupt",
        "failed",
        expected_error="PDF_ENCRYPTED",
    )
    add(
        "corrupt_fake.pdf",
        b"MZ\x90\x00\x03\x00\x00\x00 this is an executable renamed to .pdf",
        "corrupt",
        "rejected",
        expected_error="CONTENT_SIGNATURE_MISMATCH",
    )
    add("corrupt_workbook.xlsx", b"PK\x03\x04 not really a zip archive", "corrupt", "rejected", expected_error="INVALID_WORKBOOK")
    add("corrupt_image.png", b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4, "corrupt", "failed", expected_error="IMAGE_MALFORMED")

    labels = {"seed": SEED, "generator": "evaluation/synthetic.py", "files": files}
    (OUT / "labels.json").write_text(json.dumps(labels, indent=2, default=str))
    return labels


if __name__ == "__main__":
    labels = build()
    kinds: dict[str, int] = {}
    for f in labels["files"]:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    print(f"{len(labels['files'])} files → {OUT}: {kinds}")
