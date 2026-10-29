"""Deterministic synthetic financial documents with ground truth.

Used by tests, the evaluation harness, and demo-data generation. Documents are
generated, never copied from real customers, so they can be committed and
shared. Ground truth is the exact data used to render each document.
"""

from __future__ import annotations

import csv
import io
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image, ImageFilter

SUPPLIERS = [
    ("ABC Trading Ltd", "12 Market Street, London", "GB123456789"),
    ("Nordic Office Supplies AB", "Kungsgatan 5, Stockholm", "SE556677889901"),
    ("Pacific Components Inc", "400 Harbor Blvd, Oakland CA", "94-1234567"),
    ("Delta Logistics GmbH", "Hafenstrasse 22, Hamburg", "DE811223344"),
    ("Sunrise Foods Pvt Ltd", "21 MG Road, Bengaluru", "29ABCDE1234F1Z5"),
    ("Blue River Consulting LLC", "88 Pine Ave, Denver CO", "84-7654321"),
]
CUSTOMERS = ["Example Corporation", "Globex Retail Ltd", "Initech Services", "Umbrella Health plc", "Stark Manufacturing"]
ITEMS = [
    "Office Equipment",
    "Ergonomic Chair",
    "Printer Toner Cartridge",
    "Consulting Services",
    "Freight Handling",
    "Network Switch 24-port",
    "Annual Software Licence",
    "Paper A4 Box",
    "Monitor 27 inch",
    "Installation Labour",
    "Cleaning Supplies",
    "Training Workshop",
]


@dataclass
class LineSpec:
    description: str
    quantity: Decimal
    unit_price: Decimal

    @property
    def line_total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"), ROUND_HALF_UP)


@dataclass
class InvoiceSpec:
    invoice_number: str
    invoice_date: date
    due_date: date | None
    supplier_name: str
    supplier_address: str
    supplier_tax_id: str | None
    customer_name: str
    currency: str
    tax_rate: Decimal
    lines: list[LineSpec]
    kind: str = "INVOICE"
    date_style: str = "iso"  # iso | dmy | text
    number_style: str = "en"  # en (1,234.56) | eu (1.234,56)
    po_number: str | None = None
    subtotal_override: Decimal | None = None
    total_override: Decimal | None = None
    omit_fields: list[str] = field(default_factory=list)
    injection_text: str | None = None

    @property
    def subtotal(self) -> Decimal:
        if self.subtotal_override is not None:
            return self.subtotal_override
        return sum((li.line_total for li in self.lines), Decimal("0.00"))

    @property
    def tax_amount(self) -> Decimal:
        return (sum((li.line_total for li in self.lines), Decimal("0")) * self.tax_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @property
    def total_amount(self) -> Decimal:
        if self.total_override is not None:
            return self.total_override
        return self.subtotal + self.tax_amount

    def sign(self) -> int:
        return -1 if self.kind == "CREDIT_NOTE" else 1

    def ground_truth(self) -> dict[str, Any]:
        s = self.sign()
        gt = {
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date.isoformat(),
            "payment_due_date": self.due_date.isoformat() if self.due_date else None,
            "supplier_name": self.supplier_name,
            "customer_name": self.customer_name,
            "supplier_tax_id": self.supplier_tax_id,
            "purchase_order_number": self.po_number,
            "currency": self.currency,
            "subtotal": str(s * self.subtotal),
            "tax_amount": str(s * self.tax_amount),
            "total_amount": str(s * self.total_amount),
            "line_items": [
                {
                    "description": li.description,
                    "quantity": str(li.quantity),
                    "unit_price": str(li.unit_price),
                    "line_total": str(s * li.line_total),
                }
                for li in self.lines
            ],
            "document_kind": self.kind,
            "arithmetic_error": self.subtotal_override is not None or self.total_override is not None,
        }
        for name in self.omit_fields:
            gt[name] = None
        return gt


def fmt_amount(value: Decimal, style: str) -> str:
    q = value.quantize(Decimal("0.01"))
    neg = q < 0
    s = f"{abs(q):,.2f}"
    if style == "eu":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-{s}" if neg else s


def fmt_date(d: date, style: str) -> str:
    if style == "dmy":
        return d.strftime("%d/%m/%Y")
    if style == "text":
        return d.strftime("%d %b %Y")
    return d.isoformat()


def random_invoice(rng: random.Random, index: int, **overrides: Any) -> InvoiceSpec:
    supplier = rng.choice(SUPPLIERS)
    currency = {"GB": "GBP", "SE": "SEK", "DE": "EUR", "29": "INR"}.get(supplier[2][:2], "USD")
    issued = date(2026, 1, 1) + timedelta(days=rng.randint(0, 280))
    lines = [
        LineSpec(rng.choice(ITEMS), Decimal(rng.randint(1, 12)), Decimal(rng.randint(500, 250000)) / 100) for _ in range(rng.randint(1, 6))
    ]
    spec = InvoiceSpec(
        invoice_number=f"INV-{2026}-{index:04d}",
        invoice_date=issued,
        due_date=issued + timedelta(days=30),
        supplier_name=supplier[0],
        supplier_address=supplier[1],
        supplier_tax_id=supplier[2],
        customer_name=rng.choice(CUSTOMERS),
        currency=currency,
        tax_rate=rng.choice([Decimal("0.10"), Decimal("0.20"), Decimal("0.05"), Decimal("0.00")]),
        lines=lines,
        date_style=rng.choice(["iso", "dmy", "text"]),
        number_style="eu" if currency in ("EUR", "SEK") and rng.random() < 0.6 else "en",
        po_number=f"PO-{rng.randint(10000, 99999)}" if rng.random() < 0.5 else None,
    )
    for key, value in overrides.items():
        setattr(spec, key, value)
    return spec


# --- Rendering ----------------------------------------------------------------

_X_DESC, _X_QTY, _X_UNIT, _X_TOTAL = 60, 330, 400, 490


def _text(page: pymupdf.Page, x: float, y: float, text: str, size: float = 10, bold: bool = False) -> None:
    page.insert_text((x, y), text, fontsize=size, fontname="hebo" if bold else "helv")


def _right(page: pymupdf.Page, x_right: float, y: float, text: str, size: float = 10, bold: bool = False) -> None:
    font = pymupdf.Font("hebo" if bold else "helv")
    width = font.text_length(text, fontsize=size)
    _text(page, x_right - width, y, text, size, bold)


def render_invoice(doc: pymupdf.Document, spec: InvoiceSpec, lines_per_page: int = 18) -> None:
    title = "CREDIT NOTE" if spec.kind == "CREDIT_NOTE" else "INVOICE"
    s = spec.sign()
    chunks = [spec.lines[i : i + lines_per_page] for i in range(0, len(spec.lines), lines_per_page)] or [[]]
    for page_index, chunk in enumerate(chunks):
        page = doc.new_page(width=595, height=842)
        y = 60
        _text(page, 60, y, spec.supplier_name, 14, bold=True)
        _text(page, 60, y + 16, spec.supplier_address, 9)
        if spec.supplier_tax_id and "supplier_tax_id" not in spec.omit_fields:
            _text(page, 60, y + 28, f"VAT No: {spec.supplier_tax_id}", 9)
        _right(page, 535, y, title, 18, bold=True)
        number_label = "Credit Note No" if spec.kind == "CREDIT_NOTE" else "Invoice No"
        if "invoice_number" not in spec.omit_fields:
            _right(page, 535, y + 24, f"{number_label}: {spec.invoice_number}", 10)
        if "invoice_date" not in spec.omit_fields:
            _right(page, 535, y + 38, f"Invoice Date: {fmt_date(spec.invoice_date, spec.date_style)}", 10)
        if spec.due_date:
            _right(page, 535, y + 52, f"Due Date: {fmt_date(spec.due_date, spec.date_style)}", 10)
        if spec.po_number:
            _right(page, 535, y + 66, f"PO Number: {spec.po_number}", 10)
        if len(chunks) > 1:
            _right(page, 535, 820, f"Page {page_index + 1} of {len(chunks)}", 8)
        if page_index == 0:
            _text(page, 60, 150, "Bill To:", 10, bold=True)
            if "customer_name" not in spec.omit_fields:
                _text(page, 60, 164, spec.customer_name, 10)
            _text(page, 60, 178, "Accounts Payable Department", 9)
            if "currency" not in spec.omit_fields:
                _text(page, 330, 150, f"Currency: {spec.currency}", 10)
        else:
            _text(page, 60, 150, f"{title} {spec.invoice_number} (continued)", 10, bold=True)
        y = 220
        _text(page, _X_DESC, y, "Description", 10, bold=True)
        _right(page, _X_QTY + 30, y, "Qty", 10, bold=True)
        _right(page, _X_UNIT + 60, y, "Unit Price", 10, bold=True)
        _right(page, _X_TOTAL + 45, y, "Amount", 10, bold=True)
        y += 20
        for li in chunk:
            _text(page, _X_DESC, y, li.description, 10)
            _right(page, _X_QTY + 30, y, str(li.quantity), 10)
            _right(page, _X_UNIT + 60, y, fmt_amount(li.unit_price, spec.number_style), 10)
            _right(page, _X_TOTAL + 45, y, fmt_amount(s * li.line_total, spec.number_style), 10)
            y += 18
        if page_index == len(chunks) - 1:
            y += 14
            rate_pct = f"{spec.tax_rate * 100:.0f}"
            rows = [
                ("Subtotal", fmt_amount(s * spec.subtotal, spec.number_style)),
                (f"VAT ({rate_pct}%)", fmt_amount(s * spec.tax_amount, spec.number_style)),
                ("Total Due", f"{spec.currency} {fmt_amount(s * spec.total_amount, spec.number_style)}"),
            ]
            if "subtotal" in spec.omit_fields:
                rows = rows[1:]
            for label, value in rows:
                _text(page, 330, y, label, 10, bold=label == "Total Due")
                _right(page, _X_TOTAL + 45, y, value, 10, bold=label == "Total Due")
                y += 18
            _text(page, 60, y + 30, "Payment terms: 30 days. Thank you for your business.", 9)
            if spec.injection_text:
                _text(page, 60, y + 50, spec.injection_text, 7)


def invoice_pdf_bytes(specs: list[InvoiceSpec]) -> bytes:
    doc = pymupdf.open()
    for spec in specs:
        render_invoice(doc, spec)
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return bytes(data)


def scanned_images(pdf_bytes: bytes, dpi: int = 150, seed: int = 0, skew: float = 0.8) -> list[Image.Image]:
    rng = random.Random(seed)
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        img = img.rotate(rng.uniform(-skew, skew), expand=False, fillcolor=255, resample=Image.Resampling.BICUBIC)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.4))
        images.append(img)
    doc.close()
    return images


def scanned_pdf_bytes(pdf_bytes: bytes, seed: int = 0) -> bytes:
    out = pymupdf.open()
    for img in scanned_images(pdf_bytes, seed=seed):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        page = out.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=buf.getvalue())
    data = out.tobytes(garbage=3, deflate=True)
    out.close()
    return bytes(data)


def image_bytes(pdf_bytes: bytes, fmt: str = "PNG", seed: int = 0) -> bytes:
    images = scanned_images(pdf_bytes, seed=seed)
    buf = io.BytesIO()
    if fmt.upper() == "TIFF":
        images[0].save(buf, format="TIFF", save_all=True, append_images=images[1:], compression="tiff_deflate")
    else:
        images[0].save(buf, format=fmt)
    return buf.getvalue()


REGISTER_HEADERS = ["Invoice No", "Vendor", "Invoice Date", "Currency", "Net Amount", "VAT", "Invoice Total"]


def register_rows(specs: list[InvoiceSpec]) -> list[list[Any]]:
    rows = []
    for spec in specs:
        s = spec.sign()
        rows.append(
            [
                spec.invoice_number,
                spec.supplier_name,
                spec.invoice_date.isoformat(),
                spec.currency,
                str(s * spec.subtotal),
                str(s * spec.tax_amount),
                str(s * spec.total_amount),
            ]
        )
    return rows


def register_xlsx_bytes(rows: list[list[Any]], sheet: str = "AP Register") -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet
    ws.append(["Accounts Payable Register - generated"])
    ws.append([])
    ws.append(REGISTER_HEADERS)
    for row in rows:
        ws.append([Decimal(v) if i >= 4 else v for i, v in enumerate(row)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def register_xls_bytes(rows: list[list[Any]]) -> bytes:
    import xlwt  # dev-only dependency used to produce legacy XLS fixtures

    wb = xlwt.Workbook()
    ws = wb.add_sheet("Register")
    for c, h in enumerate(REGISTER_HEADERS):
        ws.write(0, c, h)
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row):
            ws.write(r, c, float(v) if c >= 4 else v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def register_csv_bytes(rows: list[list[Any]], delimiter: str = ",") -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter)
    writer.writerow(REGISTER_HEADERS)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def build_dataset(out_dir: Path, count: int = 30, seed: int = 7) -> list[dict[str, Any]]:
    """Write an evaluation dataset: PDFs/scans/images + ground_truth.json."""
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    for i in range(count):
        variant = i % 6
        overrides: dict[str, Any] = {}
        if variant == 4:
            overrides["kind"] = "CREDIT_NOTE"
        spec = random_invoice(rng, i + 1, **overrides)
        if variant == 5:
            spec.total_override = spec.total_amount + Decimal("10.00")  # injected arithmetic error
        pdf = invoice_pdf_bytes([spec])
        kind = ["native_pdf", "native_pdf", "scanned_pdf", "png", "native_pdf", "native_pdf"][variant]
        name = f"doc_{i + 1:03d}"
        if kind == "native_pdf":
            path = out_dir / f"{name}.pdf"
            path.write_bytes(pdf)
        elif kind == "scanned_pdf":
            path = out_dir / f"{name}.pdf"
            path.write_bytes(scanned_pdf_bytes(pdf, seed=i))
        else:
            path = out_dir / f"{name}.png"
            path.write_bytes(image_bytes(pdf, "PNG", seed=i))
        manifest.append({"file": path.name, "kind": kind, "invoices": [spec.ground_truth()]})
    (out_dir / "ground_truth.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def spec_to_dict(spec: InvoiceSpec) -> dict[str, Any]:
    return json.loads(json.dumps(asdict(spec), default=str))
