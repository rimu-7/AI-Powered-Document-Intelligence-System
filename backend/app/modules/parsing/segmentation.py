"""Invoice-boundary detection and candidate page selection for long documents.

A 1,000-page PDF is never sent to the LLM as a whole. Pages are grouped into
invoice segments:

* A page *starts* a segment when it carries an invoice header signal and either
  shows an invoice number different from the current segment's, or there is no
  current segment.
* A page *continues* the current segment when it has continuation signals
  ("page 2 of 3", "continued", same invoice number) or financial content
  without a new header.
* Pages without any financial signal and no open segment are excluded from
  extraction (they remain fully searchable).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADER_RE = re.compile(r"\b(tax\s+invoice|invoice|credit\s+note|receipt)\b", re.I)
# The label (No/Number/#/:) is required, so a bare "INVOICE" title never
# swallows the following "Invoice No: X" line.
_INVOICE_NO_RE = re.compile(
    r"\b(?:invoice|inv|credit\s+note|receipt)[\s.,]*(?:no\.?|number|num|#|:)[\s.,:#]*([A-Z0-9][A-Z0-9\-/_.]{2,30})",
    re.I,
)
_PAGE_X_OF_Y_RE = re.compile(r"\bpage\s+(\d+)\s*(?:of|/)\s*(\d+)\b", re.I)
_CONTINUED_RE = re.compile(r"\b(continued|cont\.|carried\s+forward|brought\s+forward)\b", re.I)
# Header-block signals that appear on the first page of an invoice, even when
# OCR garbles the invoice number itself.
_START_BLOCK_RE = re.compile(r"\b(bill(?:ed)?\s+to|sold\s+to|invoice\s+to|invoice\s+date|date\s+of\s+issue)\b", re.I)
_FINANCIAL_RE = re.compile(r"\b(total|subtotal|amount|qty|quantity|unit\s+price|tax|vat|balance)\b", re.I)
_STOPWORDS = {"date", "number", "no", "total", "amount", "details", "to", "from"}


@dataclass
class PageText:
    page_number: int
    text: str


@dataclass
class Segment:
    index: int
    pages: list[PageText] = field(default_factory=list)
    invoice_number_hint: str | None = None

    @property
    def page_start(self) -> int:
        return self.pages[0].page_number

    @property
    def page_end(self) -> int:
        return self.pages[-1].page_number

    def text_with_markers(self) -> str:
        return "\n".join(f"<<<PAGE {p.page_number}>>>\n{p.text}" for p in self.pages)


def invoice_number_hint(text: str) -> str | None:
    for match in _INVOICE_NO_RE.finditer(text[:4000]):
        candidate = match.group(1).strip(".-/_")
        if candidate.lower() in _STOPWORDS or not any(ch.isdigit() for ch in candidate):
            continue
        return candidate.upper()
    return None


def segment_pages(pages: list[PageText], max_pages_per_segment: int = 25) -> list[Segment]:
    segments: list[Segment] = []
    current: Segment | None = None
    for page in pages:
        text = page.text or ""
        head = text[:3000]
        has_header = bool(_HEADER_RE.search(head))
        number = invoice_number_hint(head) if has_header else None
        page_marker = _PAGE_X_OF_Y_RE.search(text)
        is_continuation = bool(_CONTINUED_RE.search(head)) or bool(page_marker and int(page_marker.group(1)) > 1)
        has_financial = bool(_FINANCIAL_RE.search(text))
        has_start_block = has_header and bool(_START_BLOCK_RE.search(head)) and not is_continuation

        starts_new = False
        if current is None:
            starts_new = has_header or has_financial
        elif has_header and number and current.invoice_number_hint and number != current.invoice_number_hint:
            starts_new = True
        elif has_header and number and not current.invoice_number_hint and not is_continuation:
            starts_new = len(current.pages) > 0 and bool(page_marker is None or int(page_marker.group(1)) == 1)
        elif has_start_block and number != current.invoice_number_hint:
            # New header block, number unreadable or different: a new invoice.
            starts_new = True
        elif (page_marker and int(page_marker.group(1)) == 1 and has_header) or (
            len(current.pages) >= max_pages_per_segment and has_header
        ):
            starts_new = True

        if starts_new:
            current = Segment(index=len(segments), invoice_number_hint=number)
            segments.append(current)
            current.pages.append(page)
            continue
        if current is not None and (is_continuation or has_financial or has_header):
            current.pages.append(page)
            if number and not current.invoice_number_hint:
                current.invoice_number_hint = number
            continue
        # Non-financial page: closes the open segment.
        current = None
    return segments


def split_for_budget(text: str, max_chars: int, overlap: int = 500) -> list[str]:
    """Token-aware-ish windowing (chars as a conservative token proxy) on line boundaries."""
    if len(text) <= max_chars:
        return [text]
    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            newline = text.rfind("\n", start + max_chars // 2, end)
            if newline != -1:
                end = newline
        windows.append(text[start:end])
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return windows
