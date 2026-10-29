"""Validation rules. Pure functions over an ``InvoiceView``; no database access.

Every issue carries a machine-readable code, severity, the exact mathematical
reason (expected vs actual, formula, tolerance), and source evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.modules.validation.financial import (
    check_line,
    expected_total_candidates,
    line_sum_tolerance,
    within,
)
from app.shared.enums import SEVERITY_ORDER, DocumentType, Severity, ValidationOutcome
from app.shared.money import ISO_CURRENCIES, money_str


@dataclass
class LineView:
    position: int
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    discount_amount: Decimal | None
    tax_rate: Decimal | None
    tax_amount: Decimal | None
    line_total: Decimal | None
    evidence: dict[str, Any] | None = None


@dataclass
class InvoiceView:
    document_type: DocumentType
    invoice_number: str | None
    invoice_date: date | None
    invoice_date_raw: str | None
    payment_due_date: date | None
    supplier_name: str | None
    customer_name: str | None
    currency: str | None
    currency_raw: str | None
    subtotal: Decimal | None
    discount_amount: Decimal | None
    shipping_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    amounts_tax_inclusive: bool | None
    line_items: list[LineView]
    evidence: dict[str, Any] = field(default_factory=dict)
    field_support: dict[str, str] = field(default_factory=dict)
    notes: list[dict[str, Any]] = field(default_factory=list)
    alternatives: dict[str, Any] = field(default_factory=dict)
    extraction_confidence: Decimal | None = None
    corrected_fields: list[str] = field(default_factory=list)


@dataclass
class DuplicateCandidate:
    invoice_id: str
    document_id: str
    invoice_date: date | None
    total_amount: Decimal | None
    currency: str | None
    same_file: bool = False


@dataclass
class ValidationContext:
    tolerance: Decimal
    today: date
    future_date_policy: str = "warn"
    future_grace_days: int = 1
    low_confidence_threshold: Decimal = Decimal("0.6")
    duplicate_candidates: list[DuplicateCandidate] = field(default_factory=list)


@dataclass
class IssueDraft:
    rule_code: str
    severity: Severity
    message: str
    field_path: str | None = None
    expected: Any = None
    actual: Any = None
    details: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)


REQUIRED_SEVERITY = {
    "invoice_number": Severity.ERROR,
    "invoice_date": Severity.ERROR,
    "supplier_name": Severity.ERROR,
    "total_amount": Severity.ERROR,
    "currency": Severity.ERROR,
    "customer_name": Severity.WARNING,
    "subtotal": Severity.WARNING,
    "tax_amount": Severity.WARNING,
}

# Warnings that still require a human decision.
REVIEW_TRIGGER_RULES = {
    "LOW_EXTRACTION_CONFIDENCE",
    "UNGROUNDED_VALUE",
    "DUPLICATE_INVOICE",
    "INVALID_CURRENCY",
    "AMBIGUOUS_VALUE",
    "CONFLICTING_VALUES",
}


def _ev(view: InvoiceView, name: str) -> dict[str, Any]:
    ev = view.evidence.get(name)
    return dict(ev) if isinstance(ev, dict) else {}


def _m(value: Decimal | None) -> str | None:
    return money_str(value)


def rule_required_fields(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    issues = []
    for name, severity in REQUIRED_SEVERITY.items():
        if getattr(view, name) is not None:
            continue
        if view.document_type == DocumentType.RECEIPT and name in ("customer_name", "invoice_number", "subtotal"):
            severity = Severity.INFO
        if name == "currency" and view.currency_raw:
            continue  # reported by INVALID_CURRENCY with more detail
        issues.append(
            IssueDraft(
                "REQUIRED_FIELD_MISSING",
                severity,
                f"Required field '{name}' was not found in the document",
                field_path=name,
            )
        )
    return issues


def rule_dates(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    issues: list[IssueDraft] = []
    for note in view.notes:
        if note.get("code") == "DATE_UNPARSEABLE":
            issues.append(IssueDraft("INVALID_DATE", Severity.ERROR, note.get("message", "Unparseable date"), field_path=note.get("field")))
        elif note.get("code") == "DATE_AMBIGUOUS" and note.get("field") not in view.corrected_fields:
            issues.append(
                IssueDraft(
                    "AMBIGUOUS_VALUE",
                    Severity.WARNING,
                    note.get("message", "Ambiguous date"),
                    field_path=note.get("field"),
                    details={"alternatives": view.alternatives.get(str(note.get("field")))},
                    evidence=_ev(view, str(note.get("field"))),
                )
            )
    if view.invoice_date:
        limit = ctx.today + timedelta(days=ctx.future_grace_days)
        if view.invoice_date > limit and ctx.future_date_policy != "allow":
            issues.append(
                IssueDraft(
                    "INVALID_DATE",
                    Severity.ERROR if ctx.future_date_policy == "error" else Severity.WARNING,
                    f"Invoice date {view.invoice_date.isoformat()} is in the future",
                    field_path="invoice_date",
                    expected=f"<= {limit.isoformat()}",
                    actual=view.invoice_date.isoformat(),
                    evidence=_ev(view, "invoice_date"),
                )
            )
        if view.invoice_date.year < 1990:
            issues.append(
                IssueDraft(
                    "INVALID_DATE",
                    Severity.WARNING,
                    "Invoice date is implausibly old",
                    field_path="invoice_date",
                    actual=view.invoice_date.isoformat(),
                )
            )
        if view.payment_due_date and view.payment_due_date < view.invoice_date:
            issues.append(
                IssueDraft(
                    "INVALID_DATE",
                    Severity.WARNING,
                    "Payment due date is before the invoice date",
                    field_path="payment_due_date",
                    expected=f">= {view.invoice_date.isoformat()}",
                    actual=view.payment_due_date.isoformat(),
                )
            )
    return issues


def rule_currency(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    issues: list[IssueDraft] = []
    if view.currency is None and view.currency_raw:
        issues.append(
            IssueDraft(
                "INVALID_CURRENCY",
                Severity.WARNING,
                f"Currency '{view.currency_raw}' is ambiguous or unknown; confirm the ISO 4217 code",
                field_path="currency",
                actual=view.currency_raw,
                details={"candidates": view.alternatives.get("currency")},
                evidence=_ev(view, "currency"),
            )
        )
    elif view.currency is not None and view.currency not in ISO_CURRENCIES:
        issues.append(
            IssueDraft(
                "INVALID_CURRENCY",
                Severity.ERROR,
                f"'{view.currency}' is not a supported ISO 4217 code",
                field_path="currency",
                actual=view.currency,
            )
        )
    if any(n.get("code") == "CURRENCY_CONFLICT" for n in view.notes) and "currency" not in view.corrected_fields:
        issues.append(
            IssueDraft(
                "CURRENCY_CONFLICT",
                Severity.ERROR,
                "Amounts in this invoice carry inconsistent currency labels",
                field_path="currency",
                details={"labels": view.alternatives.get("currency_conflict")},
            )
        )
    return issues


def rule_lines(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    issues: list[IssueDraft] = []
    for li in view.line_items:
        path = f"line_items[{li.position - 1}].line_total"
        if li.quantity is None or li.unit_price is None or li.line_total is None:
            if li.line_total is not None and (li.quantity is not None or li.unit_price is not None):
                issues.append(
                    IssueDraft(
                        "UNSUPPORTED_CALCULATION",
                        Severity.INFO,
                        f"Line {li.position}: quantity or unit price missing; line total not verifiable",
                        field_path=path,
                    )
                )
            continue
        check = check_line(li.quantity, li.unit_price, li.line_total, view.currency, ctx.tolerance, li.discount_amount, li.tax_amount)
        if not check.ok and view.document_type == DocumentType.CREDIT_NOTE:
            # Credit notes often print positive unit prices with negative amounts.
            flipped = check_line(
                li.quantity, li.unit_price, -li.line_total, view.currency, ctx.tolerance, li.discount_amount, li.tax_amount
            )
            if flipped.ok:
                continue
        if not check.ok:
            issues.append(
                IssueDraft(
                    "LINE_TOTAL_MISMATCH",
                    Severity.ERROR,
                    f"Line {li.position}: {li.quantity} × {li.unit_price}"
                    + (f" − {li.discount_amount}" if li.discount_amount else "")
                    + f" = {check.expected}, but the document shows {li.line_total}",
                    field_path=path,
                    expected=_m(check.expected),
                    actual=_m(check.actual),
                    details={"formula": check.model, "difference": _m(check.difference), "tolerance": _m(ctx.tolerance)},
                    evidence=li.evidence or {},
                )
            )
    return issues


def rule_subtotal(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    lines = [li for li in view.line_items if li.line_total is not None]
    if not lines:
        if view.subtotal is not None or view.total_amount is not None:
            return [
                IssueDraft(
                    "UNSUPPORTED_CALCULATION",
                    Severity.INFO,
                    "No line items extracted; subtotal cannot be reconciled with line items",
                    field_path="subtotal",
                )
            ]
        return []
    line_sum = sum((li.line_total for li in lines if li.line_total is not None), Decimal(0))
    tol = line_sum_tolerance(ctx.tolerance, len(lines))
    shipping, discount = view.shipping_amount or Decimal(0), view.discount_amount or Decimal(0)
    if view.amounts_tax_inclusive is True:
        if view.total_amount is None:
            return [
                IssueDraft(
                    "UNSUPPORTED_CALCULATION",
                    Severity.INFO,
                    "Tax-inclusive lines but no total to reconcile against",
                    field_path="total_amount",
                )
            ]
        expected = line_sum + shipping - discount
        if within(expected, view.total_amount, tol):
            return []
        return [
            IssueDraft(
                "SUBTOTAL_MISMATCH",
                Severity.ERROR,
                f"Tax-inclusive line items sum to {expected} (incl. shipping/discount) but the total is {view.total_amount}",
                field_path="total_amount",
                expected=_m(expected),
                actual=_m(view.total_amount),
                details={
                    "formula": "Σ line_total + shipping − discount",
                    "difference": _m(view.total_amount - expected),
                    "tolerance": _m(tol),
                },
                evidence=_ev(view, "total_amount"),
            )
        ]
    if view.subtotal is None:
        return [
            IssueDraft("UNSUPPORTED_CALCULATION", Severity.INFO, "Subtotal missing; line items cannot be reconciled", field_path="subtotal")
        ]
    if within(line_sum, view.subtotal, tol):
        return []
    # Discount may already be applied inside the subtotal.
    if discount and within(line_sum - discount, view.subtotal, tol):
        return []
    if (
        view.amounts_tax_inclusive is None
        and view.total_amount is not None
        and within(line_sum + shipping - discount, view.total_amount, tol)
    ):
        return [
            IssueDraft(
                "UNSUPPORTED_CALCULATION",
                Severity.INFO,
                "Line items match the gross total, so they appear tax-inclusive; subtotal not compared",
                field_path="subtotal",
            )
        ]
    return [
        IssueDraft(
            "SUBTOTAL_MISMATCH",
            Severity.ERROR,
            f"Line items sum to {line_sum} but the subtotal is {view.subtotal}",
            field_path="subtotal",
            expected=_m(line_sum),
            actual=_m(view.subtotal),
            details={"formula": "Σ line_total", "difference": _m(view.subtotal - line_sum), "tolerance": _m(tol), "line_count": len(lines)},
            evidence=_ev(view, "subtotal"),
        )
    ]


_PERCENT_RE = re.compile(r"(\d{1,2}(?:[.,]\d{1,3})?)\s*%")


def rule_tax(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    if view.tax_amount is None:
        return []
    issues: list[IssueDraft] = []
    line_taxes = [li.tax_amount for li in view.line_items if li.tax_amount is not None]
    if line_taxes and len(line_taxes) == len(view.line_items):
        total_line_tax = sum(line_taxes, Decimal(0))
        tol = line_sum_tolerance(ctx.tolerance, len(line_taxes))
        if not within(total_line_tax, view.tax_amount, tol):
            issues.append(
                IssueDraft(
                    "TAX_MISMATCH",
                    Severity.ERROR,
                    f"Line-level taxes sum to {total_line_tax} but the tax amount is {view.tax_amount}",
                    field_path="tax_amount",
                    expected=_m(total_line_tax),
                    actual=_m(view.tax_amount),
                    details={"formula": "Σ line tax_amount", "difference": _m(view.tax_amount - total_line_tax), "tolerance": _m(tol)},
                    evidence=_ev(view, "tax_amount"),
                )
            )
        return issues
    # Only a rate printed on the tax line itself is used; rates are never assumed.
    evidence_text = str(_ev(view, "tax_amount").get("supporting_text") or "")
    rates = _PERCENT_RE.findall(evidence_text)
    if len(set(rates)) == 1 and view.subtotal is not None and view.amounts_tax_inclusive is not True:
        rate = Decimal(rates[0].replace(",", ".")) / 100
        base = view.subtotal - (view.discount_amount or Decimal(0))
        expected = (base * rate).quantize(Decimal("0.01"))
        alt = (view.subtotal * rate).quantize(Decimal("0.01"))
        tol = ctx.tolerance * 2
        if not (within(expected, view.tax_amount, tol) or within(alt, view.tax_amount, tol)):
            issues.append(
                IssueDraft(
                    "TAX_MISMATCH",
                    Severity.ERROR,
                    f"Printed rate {rates[0]}% of {base} = {expected}, but the tax amount is {view.tax_amount}",
                    field_path="tax_amount",
                    expected=_m(expected),
                    actual=_m(view.tax_amount),
                    details={
                        "formula": "(subtotal − discount) × printed_rate",
                        "rate": str(rate),
                        "difference": _m(view.tax_amount - expected),
                        "tolerance": _m(tol),
                    },
                    evidence=_ev(view, "tax_amount"),
                )
            )
    elif len(set(rates)) > 1:
        issues.append(
            IssueDraft(
                "UNSUPPORTED_CALCULATION",
                Severity.INFO,
                "Multiple tax rates on the tax line; per-rate breakdown not available",
                field_path="tax_amount",
            )
        )
    return issues


def rule_total(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    if view.total_amount is None:
        return []
    if view.subtotal is None:
        return [
            IssueDraft("UNSUPPORTED_CALCULATION", Severity.INFO, "Subtotal missing; total cannot be verified", field_path="total_amount")
        ]
    if view.tax_amount is None and view.amounts_tax_inclusive is not True:
        if within(view.subtotal + (view.shipping_amount or 0) - (view.discount_amount or 0), view.total_amount, ctx.tolerance):
            return []
        return [
            IssueDraft(
                "UNSUPPORTED_CALCULATION", Severity.WARNING, "Tax amount missing; total cannot be fully verified", field_path="total_amount"
            )
        ]
    tax = view.tax_amount
    if (
        view.amounts_tax_inclusive is True
        and view.subtotal is not None
        and tax is not None
        and within(view.subtotal, view.total_amount, ctx.tolerance)
    ):
        return []  # subtotal printed gross; tax is a breakdown, not an addition
    candidates = expected_total_candidates(view.subtotal, tax, view.discount_amount, view.shipping_amount)
    for _model, expected in candidates:
        if within(expected, view.total_amount, ctx.tolerance * 2):
            return []
    model, expected = candidates[0]
    return [
        IssueDraft(
            "TOTAL_MISMATCH",
            Severity.ERROR,
            f"{view.subtotal} − {view.discount_amount or 0} + {view.shipping_amount or 0} + {tax or 0} = {expected}, but the total is {view.total_amount}",
            field_path="total_amount",
            expected=_m(expected),
            actual=_m(view.total_amount),
            details={"formula": model, "difference": _m(view.total_amount - expected), "tolerance": _m(ctx.tolerance * 2)},
            evidence=_ev(view, "total_amount"),
        )
    ]


def rule_negative(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    issues: list[IssueDraft] = []
    is_credit = view.document_type == DocumentType.CREDIT_NOTE
    for name in ("subtotal", "tax_amount", "total_amount"):
        value = getattr(view, name)
        if value is None:
            continue
        if value < 0 and not is_credit:
            issues.append(
                IssueDraft(
                    "NEGATIVE_AMOUNT",
                    Severity.WARNING,
                    f"'{name}' is negative on a document that is not a credit note",
                    field_path=name,
                    actual=_m(value),
                    evidence=_ev(view, name),
                )
            )
    if is_credit and view.total_amount is not None and view.total_amount > 0:
        issues.append(
            IssueDraft(
                "NEGATIVE_AMOUNT",
                Severity.INFO,
                "Credit note total is printed as a positive amount (sign convention)",
                field_path="total_amount",
                actual=_m(view.total_amount),
            )
        )
    return issues


def rule_duplicates(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    issues: list[IssueDraft] = []
    for cand in ctx.duplicate_candidates:
        same_amount = (
            cand.total_amount is not None
            and view.total_amount is not None
            and cand.total_amount == view.total_amount
            and cand.currency == view.currency
        )
        same_date = cand.invoice_date == view.invoice_date
        if same_amount and same_date and cand.same_file:
            severity, message = Severity.CRITICAL, "Identical file and invoice already submitted (exact duplicate)"
        elif same_amount and same_date:
            severity, message = (
                Severity.ERROR,
                "Same supplier, invoice number, date and total already exist in another document (likely duplicate)",
            )
        elif same_amount:
            severity, message = Severity.WARNING, "Same supplier, invoice number and total exist with a different date"
        else:
            severity, message = (
                Severity.WARNING,
                "Same supplier and invoice number exist with different amounts (possible revision or reused number)",
            )
        issues.append(
            IssueDraft(
                "DUPLICATE_INVOICE",
                severity,
                message,
                field_path="invoice_number",
                details={
                    "other_invoice_id": cand.invoice_id,
                    "other_document_id": cand.document_id,
                    "other_total": _m(cand.total_amount),
                    "other_date": cand.invoice_date.isoformat() if cand.invoice_date else None,
                },
                evidence=_ev(view, "invoice_number"),
            )
        )
    return issues


_FINANCIAL_FIELDS = {"invoice_number", "subtotal", "tax_amount", "total_amount", "currency", "invoice_date", "supplier_name"}


def rule_grounding(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    issues: list[IssueDraft] = []
    for name, support in view.field_support.items():
        if support != "UNSUPPORTED" or name in view.corrected_fields:
            continue
        issues.append(
            IssueDraft(
                "UNGROUNDED_VALUE",
                Severity.ERROR if name in _FINANCIAL_FIELDS else Severity.WARNING,
                f"Extracted value for '{name}' could not be found in the source text",
                field_path=name,
                actual=str(getattr(view, name, None)),
            )
        )
    for note in view.notes:
        code = note.get("code")
        if note.get("field") in view.corrected_fields:
            continue
        if code == "AMOUNT_AMBIGUOUS":
            issues.append(IssueDraft("AMBIGUOUS_VALUE", Severity.WARNING, note.get("message", ""), field_path=note.get("field")))
        elif code == "CONFLICTING_VALUES":
            issues.append(
                IssueDraft(
                    "CONFLICTING_VALUES",
                    Severity.WARNING,
                    note.get("message", ""),
                    field_path=note.get("field"),
                    details={"alternatives": view.alternatives.get(str(note.get("field")))},
                )
            )
        elif code == "CROSS_CHECK_APPLIED":
            issues.append(
                IssueDraft("CROSS_CHECK_APPLIED", Severity.INFO, note.get("message", ""), details={"method": "rules cross-check"})
            )
        elif code == "EXTRACTOR_DISAGREEMENT":
            issues.append(
                IssueDraft(
                    "EXTRACTOR_DISAGREEMENT",
                    Severity.WARNING,
                    note.get("message", ""),
                    field_path=note.get("field"),
                    details={"alternatives": view.alternatives.get(str(note.get("field")))},
                )
            )
        elif code == "EXTRACTION_FALLBACK":
            issues.append(
                IssueDraft("EXTRACTION_FALLBACK", Severity.WARNING, note.get("message", ""), details={"method": "deterministic rules"})
            )
        elif code == "AMOUNT_UNPARSEABLE":
            issues.append(IssueDraft("UNSUPPORTED_CALCULATION", Severity.WARNING, note.get("message", ""), field_path=note.get("field")))
    return issues


def rule_confidence(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    if view.extraction_confidence is None or view.corrected_fields:
        return []
    if view.extraction_confidence < ctx.low_confidence_threshold:
        return [
            IssueDraft(
                "LOW_EXTRACTION_CONFIDENCE",
                Severity.WARNING,
                f"Heuristic extraction score {view.extraction_confidence} is below {ctx.low_confidence_threshold}",
                details={"score": str(view.extraction_confidence), "threshold": str(ctx.low_confidence_threshold), "calibrated": False},
            )
        ]
    return []


RULES = (
    rule_required_fields,
    rule_dates,
    rule_currency,
    rule_lines,
    rule_subtotal,
    rule_tax,
    rule_total,
    rule_negative,
    rule_duplicates,
    rule_grounding,
    rule_confidence,
)


def run_rules(view: InvoiceView, ctx: ValidationContext) -> list[IssueDraft]:
    issues: list[IssueDraft] = []
    for rule in RULES:
        issues.extend(rule(view, ctx))
    return issues


def outcome_for(issues: list[IssueDraft]) -> ValidationOutcome:
    if not issues:
        return ValidationOutcome.PASSED
    worst = max(SEVERITY_ORDER[i.severity] for i in issues)
    if worst >= SEVERITY_ORDER[Severity.CRITICAL]:
        return ValidationOutcome.FAILED
    if worst >= SEVERITY_ORDER[Severity.ERROR]:
        return ValidationOutcome.REQUIRES_REVIEW
    if any(i.severity == Severity.WARNING and i.rule_code in REVIEW_TRIGGER_RULES for i in issues):
        return ValidationOutcome.REQUIRES_REVIEW
    if worst >= SEVERITY_ORDER[Severity.WARNING]:
        return ValidationOutcome.PASSED_WITH_WARNINGS
    return ValidationOutcome.PASSED
