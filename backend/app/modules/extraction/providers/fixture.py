"""Deterministic local extraction provider ("local-rules").

Rule-based label/layout extraction that needs no network access. It is used
for tests, offline development, and deployments where external AI
transmission is disabled. It emits the same ``RawExtraction`` contract as the
hosted LLM provider, so normalization, grounding, and validation are shared.

It handles conventional invoice layouts (label: value pairs, totals blocks,
tabular line items). Unusual layouts produce nulls, never guesses.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.modules.extraction.providers.base import (
    ClassificationResponse,
    ExtractionRequest,
    ProviderResult,
)
from app.modules.extraction.schemas import (
    RawClassification,
    RawExtraction,
    RawField,
    RawInvoice,
    RawLineItem,
    empty_invoice,
)
from app.modules.parsing.classification import classify_text
from app.shared.enums import FileKind
from app.shared.money import detect_currency_token, parse_amount

_PAGE_MARKER_RE = re.compile(r"^<<<PAGE (\d+)>>>$")
_CELL_SPLIT_RE = re.compile(r"\s{2,}|\t")
_AMOUNT_TOKEN_RE = re.compile(
    r"(?<![\w%])[\-\(]?\s*(?:[A-Z]{3}\s?|US\$|[$€£₹৳¥])?\s*\d[\d.,'  ]*\d(?:\s?[A-Z]{3})?\)?(?![\d%])|(?<![\w.])\d(?![\d.,%])"
)

_ID = r"[A-Za-z0-9][A-Za-z0-9\-/_.]*[A-Za-z0-9]|[A-Za-z0-9]"
_LABELS: list[tuple[str, re.Pattern[str]]] = [
    ("invoice_number", re.compile(rf"\b(?:tax\s+)?invoice[\s.,]*(?:no\.?|number|num|#|id)[\s.,:#]*(?P<v>{_ID})", re.I)),
    ("invoice_number", re.compile(rf"\bcredit\s+note[\s.,]*(?:no\.?|number|#)[\s.,:#]*(?P<v>{_ID})", re.I)),
    ("invoice_number", re.compile(rf"\breceipt[\s.,]*(?:no\.?|number|#)[\s.,:#]*(?P<v>{_ID})", re.I)),
    ("payment_due_date", re.compile(r"\b(?:due\s+date|payment\s+due(?:\s+date)?|pay\s+by)\s*[:.]?\s*(?P<v>[A-Za-z0-9].*)", re.I)),
    (
        "invoice_date",
        re.compile(r"\b(?:invoice\s+date|date\s+of\s+issue|issue\s+date|tax\s+point|date)\s*[:.]\s*(?P<v>[A-Za-z0-9].*)", re.I),
    ),
    (
        "purchase_order_number",
        re.compile(rf"\b(?:p\.?\s?o\.?\s*(?:no\.?|number|#)|purchase\s+order(?:\s+(?:no\.?|number))?)[\s.,:#]*(?P<v>{_ID})", re.I),
    ),
    (
        "supplier_tax_id",
        re.compile(
            r"\b(?:vat\s*(?:reg(?:istration)?\.?\s*)?(?:no\.?|number|id)|tax\s*id|tin|gstin|abn|ein)\s*[:#.]?\s*(?P<v>[A-Z0-9](?:[A-Z0-9\-]| (?=[A-Z0-9])){4,28}[A-Z0-9])",
            re.I,
        ),
    ),
    ("currency", re.compile(r"\bcurrency\s*[:.]?\s*(?P<v>[A-Z]{3})\b")),
    ("payment_reference", re.compile(rf"\bpayment\s+ref(?:erence)?\s*[:#.]?\s*(?P<v>{_ID})", re.I)),
    ("supplier_name", re.compile(r"^\s*(?:from|supplier|vendor|seller|issued\s+by|sold\s+by)\s*[:.]\s*(?P<v>.+)", re.I)),
    ("customer_name", re.compile(r"^\s*(?:bill(?:ed)?\s+to|customer|sold\s+to|invoice\s+to|client|ship\s+to)\s*[:.]?\s*(?P<v>.*)", re.I)),
]

_SUBTOTAL_RE = re.compile(r"\b(sub\s*-?\s*total|net\s+(?:total|amount)|total\s+(?:excl\.?|excluding|before|net|ex\.?)\b)", re.I)
_DISCOUNT_RE = re.compile(r"\bdiscount\b", re.I)
_SHIPPING_RE = re.compile(r"\b(shipping|freight|delivery(?:\s+charge)?|postage)\b", re.I)
_TAX_RE = re.compile(r"\b(vat|tax|gst|hst|sales\s+tax)\b(?!\s*(?:id|no\.?|number|reg|registration|point|invoice))", re.I)
_TOTAL_RE = re.compile(
    r"\b(grand\s+total|total\s+due|amount\s+due|balance\s+due|total\s+amount|invoice\s+total|total\s+(?:incl\.?|including)|total\s+payable|total)\b",
    re.I,
)
_ITEM_HEADER_RE = re.compile(r"\b(description|item|product|service|particulars)\b", re.I)
_QTY_HEADER_RE = re.compile(r"\b(qty|quantity|units|hrs|hours)\b", re.I)
_PRICE_HEADER_RE = re.compile(r"\b(unit\s+price|price|rate|amount|total)\b", re.I)
_TAX_INCLUSIVE_RE = re.compile(r"\b(prices?|amounts?)\s+(?:are\s+)?(incl(?:usive|\.|uding)?)\s+(?:of\s+)?(vat|tax|gst)\b", re.I)
_TAX_EXCLUSIVE_RE = re.compile(r"\b(prices?|amounts?)\s+(?:are\s+)?(excl(?:usive|\.|uding)?)\s+(?:of\s+)?(vat|tax|gst)\b", re.I)
_PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_LABEL_ONLY_RE = re.compile(r"^[^:\d]{1,40}:$")  # "Status:", "Invoice Details:"
_REFERENCE_RE = re.compile(r"^(?=[A-Za-z0-9/_.\-]*\d)(?=[A-Za-z0-9/_.\-]*[A-Za-z])[A-Za-z0-9]+(?:[/_.\-][A-Za-z0-9]+)+$")  # INV-2023-00147
_URL_RE = re.compile(r"\bhttps?://|\bwww\.\S+\.\w", re.I)  # browser print headers/footers carry the page URL
_DOCUMENT_TITLES = ("invoice", "taxinvoice", "creditnote", "receipt", "statement", "proformainvoice", "bill", "salesinvoice")


def _is_title(cell: str) -> bool:
    """Document titles, including OCR misreads such as "| NVOICE" or "lNVOICE"."""
    letters = re.sub(r"[^a-z]", "", cell.lower())
    if not letters or len(letters) > 20:
        return False
    return any(letters == t or (len(t) >= 6 and SequenceMatcher(None, letters, t).ratio() >= 0.85) for t in _DOCUMENT_TITLES)


def _is_address_part(cell: str) -> bool:
    return bool(
        cell
        and not _LABEL_ONLY_RE.match(cell)
        and not _REFERENCE_RE.match(cell)
        and not _is_title(cell)
        and not _URL_RE.search(cell)
        and not any(p.search(cell) for _, p in _LABELS)
        and not _TOTAL_RE.search(cell)
        and not _ITEM_HEADER_RE.search(cell)
    )


@dataclass
class _Line:
    page: int
    text: str

    @property
    def cells(self) -> list[str]:
        return [c.strip() for c in _CELL_SPLIT_RE.split(self.text.strip()) if c.strip()]


def _lines(text: str) -> list[_Line]:
    page = 1
    out: list[_Line] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if m := _PAGE_MARKER_RE.match(stripped):
            page = int(m.group(1))
            continue
        if stripped:
            out.append(_Line(page, raw.rstrip()))
    return out


def _column_cell(line: _Line, column: int) -> str:
    """The cell in ``column``; lines with fewer cells contribute their last cell."""
    cells = line.cells
    if not cells:
        return ""
    return cells[column] if column < len(cells) else cells[-1]


def _field(value: str | None, line: _Line | None) -> RawField:
    if not value:
        return RawField(value=None, page=None, evidence=None)
    return RawField(value=value.strip(), page=line.page if line else None, evidence=line.text.strip()[:200] if line else None)


def _amount_tokens(text: str) -> list[str]:
    tokens = []
    for match in _AMOUNT_TOKEN_RE.finditer(text):
        token = match.group(0).strip()
        if parse_amount(token) is not None:
            tokens.append(token)
    return tokens


def _last_amount(line: _Line) -> str | None:
    for cell in reversed(line.cells):
        if _PERCENT_RE.fullmatch(cell.strip()):
            continue
        tokens = _amount_tokens(cell)
        if tokens:
            return tokens[-1]
    return None


class LocalRulesProvider:
    def provider_name(self) -> str:
        return "local-rules"

    def model_name(self) -> str:
        return "local-rules-v1"

    def healthcheck(self) -> bool:
        return True

    def classify_document(self, text: str) -> ClassificationResponse:
        result = classify_text(text, FileKind.PDF)
        doc_type = result.document_type.value
        if doc_type == "SPREADSHEET_REGISTER":
            doc_type = "UNKNOWN"
        return ClassificationResponse(
            classification=RawClassification(document_type=doc_type),  # type: ignore[arg-type]
            model=self.model_name(),
        )

    def extract_invoice(self, request: ExtractionRequest) -> ProviderResult:
        started = time.perf_counter()
        lines = _lines(request.document_text)
        invoice = self._extract(lines)
        has_content = any(getattr(invoice, f).value for f in ("invoice_number", "total_amount", "supplier_name", "subtotal"))
        extraction = RawExtraction(invoices=[invoice] if has_content else [])
        return ProviderResult(
            extraction=extraction,
            model=self.model_name(),
            latency_ms=int((time.perf_counter() - started) * 1000),
            usage={"input_chars": len(request.document_text)},
        )

    # -- internals ---------------------------------------------------------

    def _extract(self, lines: list[_Line]) -> RawInvoice:
        inv = empty_invoice()
        found: dict[str, RawField] = {}
        full_text = "\n".join(line.text for line in lines)

        for idx, line in enumerate(lines):
            for cell_text in [*line.cells, line.text]:
                for name, pattern in _LABELS:
                    if name in found:
                        continue
                    m = pattern.search(cell_text)
                    if not m:
                        continue
                    value = (m.group("v") or "").strip()
                    if name in ("invoice_date",) and re.search(r"\bdue\b", cell_text, re.I):
                        continue
                    if name in ("invoice_date", "payment_due_date"):
                        value = _CELL_SPLIT_RE.split(value)[0]
                    if name in ("supplier_name", "customer_name"):
                        value = _CELL_SPLIT_RE.split(value)[0] if value else ""
                        if value and any(p.search(value) for n, p in _LABELS if n != name):
                            value = ""
                        column = line.cells.index(cell_text) if cell_text in line.cells else 0
                        if not value and idx + 1 < len(lines):
                            nxt = lines[idx + 1]
                            value = _column_cell(nxt, column)
                            if value and not _LABEL_ONLY_RE.match(value):
                                found[name] = _field(value, nxt)
                                self._address(inv, name, lines, idx + 2, column)
                            continue
                        if value:
                            self._address(inv, name, lines, idx + 1, column)
                    if value:
                        found[name] = _field(value, line)

        # Letterhead fallback for the supplier: first meaningful cell of the segment,
        # skipping the document title ("INVOICE" may sit left of the supplier block).
        if "supplier_name" not in found:
            for line_idx, line in enumerate(lines[:8]):
                if _URL_RE.search(line.text):
                    continue  # "Invoice Print   https://..." header added by the browser
                pick = next(
                    (
                        (col, cell)
                        for col, cell in enumerate(line.cells)
                        if re.search(r"[A-Za-z]{3}", cell)
                        and not _is_title(cell)
                        and not _LABEL_ONLY_RE.match(cell)
                        and not _REFERENCE_RE.match(cell)
                        and not any(p.search(cell) for _, p in _LABELS)
                        and not _amount_tokens(cell)
                    ),
                    None,
                )
                if pick is not None:
                    column, name_cell = pick
                    found["supplier_name"] = _field(name_cell, line)
                    self._address(inv, "supplier_name", lines, line_idx + 1, column, multi_column=len(line.cells) > 1)
                    break

        self._totals(lines, found)
        for name, value in found.items():
            setattr(inv, name, value)

        if "currency" not in found:
            inv.currency = self._currency(lines)

        if _TAX_INCLUSIVE_RE.search(full_text):
            inv.amounts_tax_inclusive = True
        elif _TAX_EXCLUSIVE_RE.search(full_text):
            inv.amounts_tax_inclusive = False

        lowered = full_text.lower()
        if "credit note" in lowered or "credit memo" in lowered:
            inv.document_kind = "CREDIT_NOTE"
        elif "invoice" in lowered:
            inv.document_kind = "INVOICE"
        elif "receipt" in lowered:
            inv.document_kind = "RECEIPT"
        inv.line_items = self._line_items(lines)
        return inv

    def _address(self, inv: RawInvoice, name: str, lines: list[_Line], start: int, column: int = 0, *, multi_column: bool = False) -> None:
        """Address lines under a name, read from the name's column.

        In a two-column header the address continues in the same column; a line
        with a single cell is taken as part of it only if it is not a label or a
        reference number (for example the invoice number in the other column).
        """
        parts: list[str] = []
        first: _Line | None = None
        for line in lines[start : start + 3]:
            cell = _column_cell(line, column) if (column or multi_column) else (line.cells[0] if line.cells else "")
            if not _is_address_part(cell):
                break
            first = first or line
            parts.append(cell)
        if parts:
            target = "supplier_address" if name == "supplier_name" else "customer_address"
            setattr(inv, target, RawField(value=", ".join(parts), page=first.page if first else None, evidence=" ".join(parts)[:200]))

    def _totals(self, lines: list[_Line], found: dict[str, RawField]) -> None:
        total_candidates: list[tuple[int, str, _Line]] = []
        for line in lines:
            label = line.cells[0] if line.cells else line.text
            amount = _last_amount(line)
            if amount is None or (len(line.cells) < 2 and not re.search(r"[:]\s*\S", line.text)):
                continue
            # Totals rows are short ("Label   amount" or "Label   rate   amount") and
            # start with the label. Line items ("Freight Handling  3  9.00  27.00")
            # have more cells and must not be read as charges or totals.
            if len(line.cells) > 3:
                continue

            def starts(pattern: re.Pattern[str], text: str = label) -> bool:
                m = pattern.search(text)
                return m is not None and not text[: m.start()].strip(" :*-")

            if starts(_SUBTOTAL_RE):
                found.setdefault("subtotal", _field(amount, line))
            elif starts(_DISCOUNT_RE):
                found.setdefault("discount_amount", _field(amount, line))
            elif starts(_SHIPPING_RE):
                found.setdefault("shipping_amount", _field(amount, line))
            elif starts(_TOTAL_RE) and not _ITEM_HEADER_RE.search(line.text):
                priority = 2 if re.search(r"grand|due|payable|incl|invoice\s+total|total\s+amount", label, re.I) else 1
                total_candidates.append((priority, amount, line))
            elif starts(_TAX_RE):
                found.setdefault("tax_amount", _field(amount, line))
        if total_candidates and "total_amount" not in found:
            best = max(total_candidates, key=lambda c: (c[0], lines.index(c[2])))
            found["total_amount"] = _field(best[1], best[2])

    def _currency(self, lines: list[_Line]) -> RawField:
        # Prefer currency markers on amount lines (totals first).
        ordered = sorted(lines, key=lambda ln: 0 if _TOTAL_RE.search(ln.text) else 1)
        ambiguous: tuple[str, _Line] | None = None
        for line in ordered:
            code, candidates = detect_currency_token(line.text)
            if code:
                token = next((t for t in re.findall(r"\b[A-Z]{3}\b|US\$|[€£₹৳]", line.text) if detect_currency_token(t)[0] == code), code)
                return _field(token, line)
            if candidates and ambiguous is None and _amount_tokens(line.text):
                symbol = "$" if "$" in line.text else ("¥" if "¥" in line.text else None)
                if symbol:
                    ambiguous = (symbol, line)
        if ambiguous:
            return _field(ambiguous[0], ambiguous[1])
        return RawField(value=None, page=None, evidence=None)

    def _line_items(self, lines: list[_Line]) -> list[RawLineItem]:
        items: list[RawLineItem] = []
        in_table = False
        for line in lines:
            text = line.text
            if not in_table:
                if _ITEM_HEADER_RE.search(text) and _QTY_HEADER_RE.search(text) and _PRICE_HEADER_RE.search(text):
                    in_table = True
                continue
            label = line.cells[0] if line.cells else ""
            if _SUBTOTAL_RE.search(label) or (_TOTAL_RE.search(label) and len(line.cells) <= 3) or _TAX_RE.match(label):
                break
            cells = line.cells
            numeric_tail: list[str] = []
            for cell in reversed(cells):
                if _PERCENT_RE.fullmatch(cell):
                    numeric_tail.insert(0, cell)
                    continue
                tokens = _amount_tokens(cell)
                if tokens and len(tokens) == 1 and tokens[0].replace(" ", "") == cell.replace(" ", ""):
                    numeric_tail.insert(0, cell)
                else:
                    break
            desc_cells = cells[: len(cells) - len(numeric_tail)]
            amounts = [c for c in numeric_tail if not _PERCENT_RE.fullmatch(c)]
            rate = next((c for c in numeric_tail if _PERCENT_RE.fullmatch(c)), None)
            if len(amounts) >= 2 and desc_cells:
                qty = amounts[0] if len(amounts) >= 3 else None
                unit = amounts[-2] if len(amounts) >= 3 else amounts[0]
                total = amounts[-1]
                tax_amount = amounts[-2] if len(amounts) >= 4 else None
                if len(amounts) >= 4:
                    unit = amounts[1]
                items.append(
                    RawLineItem(
                        description=" ".join(desc_cells),
                        quantity=qty,
                        unit_price=unit,
                        discount_amount=None,
                        tax_rate=rate,
                        tax_amount=tax_amount,
                        line_total=total,
                        page=line.page,
                        evidence=text.strip()[:200],
                    )
                )
            elif items and desc_cells and not amounts:
                # Wrapped description line.
                prev = items[-1]
                prev.description = f"{prev.description} {' '.join(desc_cells)}".strip()
            elif not cells:
                continue
        return items
