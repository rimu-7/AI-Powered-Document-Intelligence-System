"""Evidence grounding: verify every extracted value against the source text.

A value is SUPPORTED only if it can be found on the cited page (or anywhere in
the segment). Values that cannot be located are UNSUPPORTED (possible
hallucination) and the reviewer is told so; no evidence is invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.modules.extraction.schemas import (
    AMOUNT_FIELDS,
    INVOICE_FIELDS,
    Evidence,
    NormalizedInvoice,
    RawField,
    RawInvoice,
)
from app.shared.money import parse_amount
from app.shared.text import normalize_for_grounding

_NUMBER_RE = re.compile(r"[\-\(]?\d[\d.,'  ]*\d\)?|\d")


@dataclass
class GroundingPage:
    page_number: int
    text: str
    lines: list[dict[str, Any]] = field(default_factory=list)  # {"text", "bbox"}
    method: str = "native"
    _norm: str | None = None
    _amounts: set[Decimal] | None = None

    @property
    def normalized(self) -> str:
        if self._norm is None:
            self._norm = normalize_for_grounding(self.text)
        return self._norm

    @property
    def amounts(self) -> set[Decimal]:
        if self._amounts is None:
            values: set[Decimal] = set()
            for token in _NUMBER_RE.findall(self.text):
                for hint in (None, ".", ","):
                    parsed = parse_amount(token.strip(), decimal_hint=hint)
                    if parsed is not None:
                        values.add(abs(parsed.value).normalize())
            self._amounts = values
        return self._amounts


def _locate_line(page: GroundingPage, needle_norm: str) -> dict[str, Any] | None:
    if not needle_norm:
        return None
    for line in page.lines:
        if needle_norm in normalize_for_grounding(str(line.get("text", ""))):
            return line
    return None


def _value_on_page(page: GroundingPage, field_name: str, value: Any, raw_value: str | None) -> bool:
    if value is None:
        return False
    if field_name in AMOUNT_FIELDS or isinstance(value, Decimal):
        if isinstance(value, Decimal) and abs(value).normalize() in page.amounts:
            return True
    needle = normalize_for_grounding(raw_value or str(value))
    return bool(needle) and needle in page.normalized


def ground_field(
    field_name: str,
    value: Any,
    raw: RawField | None,
    pages: dict[int, GroundingPage],
    document_id: str | None,
    raw_value: str | None = None,
) -> Evidence | None:
    if value is None:
        return None
    raw_value = raw_value if raw_value is not None else (raw.value if raw else None)
    cited = raw.page if raw and raw.page in pages else None
    order = ([cited] if cited else []) + [p for p in pages if p != cited]
    for page_number in order:
        page = pages[page_number]
        if not _value_on_page(page, field_name, value, raw_value):
            continue
        evidence_text = raw.evidence if raw and raw.evidence else None
        line = None
        if evidence_text and normalize_for_grounding(evidence_text) in page.normalized:
            line = _locate_line(page, normalize_for_grounding(evidence_text))
        else:
            evidence_text = None
        if line is None:
            line = _locate_line(page, normalize_for_grounding(raw_value or str(value)))
        if evidence_text is None and line is not None:
            evidence_text = str(line.get("text", ""))[:200]
        return Evidence(
            document_id=document_id,
            page_number=page_number,
            supporting_text=evidence_text,
            bounding_box=list(line["bbox"]) if line and line.get("bbox") else None,
            extraction_method=page.method,
            support="SUPPORTED",
        )
    return Evidence(
        document_id=document_id,
        page_number=cited,
        supporting_text=None,
        extraction_method=pages[order[0]].method if order else "unknown",
        support="UNSUPPORTED",
    )


def ground_invoice(inv: NormalizedInvoice, raw: RawInvoice, pages: dict[int, GroundingPage], document_id: str | None) -> None:
    for name in INVOICE_FIELDS:
        value = getattr(inv, name)
        raw_field: RawField = getattr(raw, name)
        raw_value = raw_field.value
        if name == "currency" and value is not None:
            raw_value = inv.currency_raw or value
        evidence = ground_field(name, value, raw_field, pages, document_id, raw_value=raw_value)
        if evidence is not None:
            inv.evidence[name] = evidence
    for li, raw_li in zip(inv.line_items, raw.line_items, strict=False):
        probe = li.line_total if li.line_total is not None else li.description
        if probe is None:
            continue
        rf = RawField(value=raw_li.line_total or raw_li.description, page=raw_li.page, evidence=raw_li.evidence)
        li.evidence = ground_field("line_total" if li.line_total is not None else "description", probe, rf, pages, document_id)
