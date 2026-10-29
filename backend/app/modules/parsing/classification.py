"""Deterministic-first document classification.

Scores keyword and layout signals per document type. The reported confidence
is a heuristic margin score in [0, 1] (how dominant the winning type's signals
are), not a calibrated probability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.shared.enums import DocumentType, FileKind

_SIGNALS: dict[DocumentType, list[tuple[re.Pattern[str], float]]] = {
    DocumentType.INVOICE: [
        (re.compile(r"\b(tax\s+)?invoice\b", re.I), 3.0),
        (re.compile(r"\binvoice\s*(no|number|#|date)\b", re.I), 3.0),
        (re.compile(r"\bbill\s+to\b", re.I), 1.5),
        (re.compile(r"\b(amount|balance)\s+due\b", re.I), 1.5),
        (re.compile(r"\bdue\s+date\b", re.I), 1.0),
        (re.compile(r"\bsub\s*-?total\b", re.I), 1.0),
        (re.compile(r"\b(vat|gst|sales\s+tax)\b", re.I), 0.5),
        (re.compile(r"\bpayment\s+terms\b", re.I), 1.0),
    ],
    DocumentType.CREDIT_NOTE: [
        (re.compile(r"\bcredit\s+(note|memo)\b", re.I), 5.0),
        (re.compile(r"\bcredit\s+note\s*(no|number|#)\b", re.I), 3.0),
        (re.compile(r"\brefund\b", re.I), 1.0),
    ],
    DocumentType.RECEIPT: [
        (re.compile(r"\breceipt\b", re.I), 3.0),
        (re.compile(r"\b(cash|change|tendered|card\s+payment|paid)\b", re.I), 1.0),
        (re.compile(r"\bthank\s+you\s+for\s+(your\s+)?(purchase|shopping)\b", re.I), 2.0),
        (re.compile(r"\b(cashier|terminal|pos)\b", re.I), 1.0),
    ],
    DocumentType.FINANCIAL_STATEMENT: [
        (re.compile(r"\b(balance\s+sheet|income\s+statement|profit\s+and\s+loss|cash\s+flow\s+statement)\b", re.I), 4.0),
        (re.compile(r"\bstatement\s+of\s+(account|financial\s+position)\b", re.I), 4.0),
        (re.compile(r"\b(opening|closing)\s+balance\b", re.I), 2.0),
        (re.compile(r"\b(total\s+assets|total\s+liabilities|retained\s+earnings)\b", re.I), 2.0),
    ],
}

MIN_SCORE = 3.0


@dataclass
class ClassificationResult:
    document_type: DocumentType
    confidence: Decimal | None
    method: str
    signals: dict[str, float] = field(default_factory=dict)
    needs_review: bool = False


def classify_text(text: str, file_kind: FileKind, looks_like_register: bool = False) -> ClassificationResult:
    if file_kind.is_spreadsheet:
        if looks_like_register:
            return ClassificationResult(DocumentType.SPREADSHEET_REGISTER, Decimal("0.90"), "header_match")
        return ClassificationResult(DocumentType.UNKNOWN, None, "header_match", needs_review=True)

    sample = text[:200_000]
    scores: dict[str, float] = {}
    for doc_type, patterns in _SIGNALS.items():
        score = 0.0
        for pattern, weight in patterns:
            hits = len(pattern.findall(sample))
            if hits:
                score += weight * min(3, hits)
        scores[doc_type.value] = round(score, 2)

    # A credit note normally also mentions "invoice"; the specific signal wins.
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_type, best = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if scores[DocumentType.CREDIT_NOTE.value] >= 5.0:
        best_type, best = DocumentType.CREDIT_NOTE.value, scores[DocumentType.CREDIT_NOTE.value]
        runner_up = max(v for k, v in scores.items() if k != best_type)
    if best < MIN_SCORE:
        return ClassificationResult(DocumentType.UNKNOWN, None, "keyword_rules", scores, needs_review=True)
    margin = (best - runner_up) / best if best else 0.0
    confidence = Decimal(str(round(min(1.0, 0.5 + margin / 2), 2)))
    return ClassificationResult(
        DocumentType(best_type),
        confidence,
        "keyword_rules",
        scores,
        needs_review=confidence < Decimal("0.6"),
    )
