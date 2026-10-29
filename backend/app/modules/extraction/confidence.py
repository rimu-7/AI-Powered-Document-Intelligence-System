"""Heuristic extraction-confidence score.

This is NOT a calibrated probability. It summarises observable signals:
required-field coverage, the share of values grounded in the source text, OCR
recognition quality, and normalization ambiguities. It is used only to route
documents to human review (LOW_EXTRACTION_CONFIDENCE).
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.extraction.schemas import INVOICE_FIELDS, REQUIRED_FIELDS, NormalizedInvoice

_AMBIGUITY_CODES = {
    "DATE_AMBIGUOUS",
    "AMOUNT_AMBIGUOUS",
    "CURRENCY_AMBIGUOUS",
    "CURRENCY_CONFLICT",
    "AMOUNT_UNPARSEABLE",
    "DATE_UNPARSEABLE",
}


def heuristic_confidence(inv: NormalizedInvoice) -> Decimal:
    required_present = sum(1 for f in REQUIRED_FIELDS if getattr(inv, f) is not None)
    coverage = required_present / len(REQUIRED_FIELDS)
    non_null = [f for f in INVOICE_FIELDS if getattr(inv, f) is not None]
    supported = sum(1 for f in non_null if inv.evidence.get(f) and inv.evidence[f].support == "SUPPORTED")
    grounding = supported / len(non_null) if non_null else 0.0
    ocr = inv.ocr_confidence if inv.ocr_confidence is not None else 1.0
    ambiguity_penalty = min(0.2, 0.05 * sum(1 for n in inv.notes if n.code in _AMBIGUITY_CODES))
    score = 0.45 * coverage + 0.35 * grounding + 0.2 * max(0.0, min(1.0, ocr)) - ambiguity_penalty
    return Decimal(str(round(max(0.0, min(1.0, score)), 2)))
