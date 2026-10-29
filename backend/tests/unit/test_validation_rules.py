from __future__ import annotations

from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.validation.rules import (
    DuplicateCandidate,
    InvoiceView,
    LineView,
    ValidationContext,
    outcome_for,
    run_rules,
)
from app.shared.enums import DocumentType, Severity, ValidationOutcome

CTX = ValidationContext(tolerance=Decimal("0.01"), today=date(2026, 10, 29))


def view(**kw: object) -> InvoiceView:
    lines = kw.pop(
        "line_items",
        [
            LineView(1, "Chair", Decimal("2"), Decimal("500.00"), None, None, None, Decimal("1000.00")),
            LineView(2, "Desk", Decimal("1"), Decimal("250.50"), None, None, None, Decimal("250.50")),
        ],
    )
    base: dict[str, object] = {
        "document_type": DocumentType.INVOICE,
        "invoice_number": "INV-1",
        "invoice_date": date(2026, 10, 1),
        "invoice_date_raw": "2026-10-01",
        "payment_due_date": date(2026, 10, 31),
        "supplier_name": "ABC Ltd",
        "customer_name": "Example Corp",
        "currency": "USD",
        "currency_raw": "USD",
        "subtotal": Decimal("1250.50"),
        "discount_amount": None,
        "shipping_amount": None,
        "tax_amount": Decimal("125.05"),
        "total_amount": Decimal("1375.55"),
        "amounts_tax_inclusive": None,
        "line_items": lines,
        "evidence": {"tax_amount": {"supporting_text": "VAT (10%)   125.05"}},
        "field_support": {},
    }
    base.update(kw)
    return InvoiceView(**base)  # type: ignore[arg-type]


def codes(v: InvoiceView, ctx: ValidationContext = CTX) -> dict[str, Severity]:
    return {i.rule_code: i.severity for i in run_rules(v, ctx)}


def test_consistent_invoice_passes() -> None:
    issues = run_rules(view(), CTX)
    assert issues == []
    assert outcome_for(issues) == ValidationOutcome.PASSED


def test_total_mismatch_reports_exact_math() -> None:
    issues = run_rules(view(total_amount=Decimal("1385.55")), CTX)
    total = next(i for i in issues if i.rule_code == "TOTAL_MISMATCH")
    assert total.expected == "1375.55" and total.actual == "1385.55"
    assert total.details["difference"] == "10.00"
    assert outcome_for(issues) == ValidationOutcome.REQUIRES_REVIEW


def test_line_and_subtotal_mismatch() -> None:
    bad_line = [LineView(1, "Chair", Decimal("2"), Decimal("500.00"), None, None, None, Decimal("900.00"))]
    c = codes(view(line_items=bad_line, subtotal=Decimal("900.00"), tax_amount=Decimal("90.00"), total_amount=Decimal("990.00")))
    assert c["LINE_TOTAL_MISMATCH"] == Severity.ERROR
    c = codes(view(subtotal=Decimal("1300.00"), total_amount=Decimal("1430.00"), tax_amount=Decimal("130.00")))
    assert "SUBTOTAL_MISMATCH" in c


def test_tax_uses_only_printed_rate() -> None:
    c = codes(view(tax_amount=Decimal("100.00"), total_amount=Decimal("1350.50")))
    assert "TAX_MISMATCH" in c
    # Without a printed rate, the tax is not judged against an invented percentage.
    c = codes(view(tax_amount=Decimal("100.00"), total_amount=Decimal("1350.50"), evidence={}))
    assert "TAX_MISMATCH" not in c


def test_rounding_within_tolerance_is_accepted() -> None:
    assert "TOTAL_MISMATCH" not in codes(view(total_amount=Decimal("1375.56")))


def test_required_fields_and_currency() -> None:
    c = codes(view(invoice_number=None, currency=None, currency_raw="$"))
    assert c["REQUIRED_FIELD_MISSING"] == Severity.ERROR
    assert c["INVALID_CURRENCY"] == Severity.WARNING
    assert "INVALID_CURRENCY" in codes(view(currency="XYZ"))


def test_future_date_policy() -> None:
    assert codes(view(invoice_date=date(2027, 1, 1), payment_due_date=None))["INVALID_DATE"] == Severity.WARNING
    strict = ValidationContext(tolerance=Decimal("0.01"), today=date(2026, 10, 29), future_date_policy="error")
    assert codes(view(invoice_date=date(2027, 1, 1), payment_due_date=None), strict)["INVALID_DATE"] == Severity.ERROR


def test_credit_note_negative_amounts_are_legitimate() -> None:
    lines = [LineView(1, "Return", Decimal("1"), Decimal("-100.00"), None, None, None, Decimal("-100.00"))]
    v = view(
        document_type=DocumentType.CREDIT_NOTE,
        line_items=lines,
        subtotal=Decimal("-100.00"),
        tax_amount=Decimal("-10.00"),
        total_amount=Decimal("-110.00"),
    )
    assert run_rules(v, CTX) == []
    v2 = view(line_items=lines, subtotal=Decimal("-100.00"), tax_amount=Decimal("-10.00"), total_amount=Decimal("-110.00"))
    assert codes(v2)["NEGATIVE_AMOUNT"] == Severity.WARNING


def test_tax_inclusive_lines() -> None:
    lines = [LineView(1, "Item", Decimal("1"), Decimal("110.00"), None, None, None, Decimal("110.00"))]
    v = view(
        line_items=lines,
        amounts_tax_inclusive=True,
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("10.00"),
        total_amount=Decimal("110.00"),
        evidence={},
    )
    assert run_rules(v, CTX) == []


def test_discount_and_shipping() -> None:
    v = view(discount_amount=Decimal("50.00"), shipping_amount=Decimal("20.00"), total_amount=Decimal("1345.55"))
    assert "TOTAL_MISMATCH" not in codes(v)


def test_duplicates() -> None:
    dup = DuplicateCandidate("i2", "d2", date(2026, 10, 1), Decimal("1375.55"), "USD")
    ctx = ValidationContext(tolerance=Decimal("0.01"), today=date(2026, 10, 29), duplicate_candidates=[dup])
    assert codes(view(), ctx)["DUPLICATE_INVOICE"] == Severity.ERROR
    same_file = DuplicateCandidate("i2", "d2", date(2026, 10, 1), Decimal("1375.55"), "USD", same_file=True)
    ctx = ValidationContext(tolerance=Decimal("0.01"), today=date(2026, 10, 29), duplicate_candidates=[same_file])
    issues = run_rules(view(), ctx)
    assert outcome_for(issues) == ValidationOutcome.FAILED
    revision = DuplicateCandidate("i3", "d3", date(2026, 10, 1), Decimal("999.00"), "USD")
    ctx = ValidationContext(tolerance=Decimal("0.01"), today=date(2026, 10, 29), duplicate_candidates=[revision])
    assert codes(view(), ctx)["DUPLICATE_INVOICE"] == Severity.WARNING


def test_ungrounded_and_low_confidence_require_review() -> None:
    issues = run_rules(view(field_support={"total_amount": "UNSUPPORTED"}), CTX)
    assert {i.rule_code for i in issues} == {"UNGROUNDED_VALUE"}
    assert outcome_for(issues) == ValidationOutcome.REQUIRES_REVIEW
    issues = run_rules(view(extraction_confidence=Decimal("0.3")), CTX)
    assert outcome_for(issues) == ValidationOutcome.REQUIRES_REVIEW
    # Human-corrected fields are not flagged as ungrounded.
    issues = run_rules(view(field_support={"total_amount": "UNSUPPORTED"}, corrected_fields=["total_amount"]), CTX)
    assert issues == []


def test_missing_data_is_unsupported_not_mismatch() -> None:
    c = codes(view(subtotal=None, line_items=[]))
    assert "TOTAL_MISMATCH" not in c and "UNSUPPORTED_CALCULATION" in c


money = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("50000"), places=2)


@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(st.integers(1, 50), money), min_size=1, max_size=8), st.sampled_from(["0", "0.05", "0.1", "0.2"]))
def test_property_consistent_invoices_never_flag_arithmetic(lines: list[tuple[int, Decimal]], rate: str) -> None:
    items = [
        LineView(i + 1, f"item {i}", Decimal(q), p, None, None, None, (Decimal(q) * p).quantize(Decimal("0.01")))
        for i, (q, p) in enumerate(lines)
    ]
    subtotal = sum((li.line_total for li in items if li.line_total is not None), Decimal(0))
    tax = (subtotal * Decimal(rate)).quantize(Decimal("0.01"))
    v = view(
        line_items=items,
        subtotal=subtotal,
        tax_amount=tax,
        total_amount=subtotal + tax,
        evidence={"tax_amount": {"supporting_text": f"VAT ({Decimal(rate) * 100:.0f}%) {tax}"}},
    )
    arithmetic = {"LINE_TOTAL_MISMATCH", "SUBTOTAL_MISMATCH", "TAX_MISMATCH", "TOTAL_MISMATCH"}
    assert not arithmetic & set(codes(v))


@settings(max_examples=200, deadline=None)
@given(money, st.decimals(min_value=Decimal("0.03"), max_value=Decimal("100000"), places=2), st.booleans())
def test_property_total_perturbation_beyond_tolerance_is_detected(subtotal: Decimal, delta: Decimal, up: bool) -> None:
    tax = (subtotal * Decimal("0.1")).quantize(Decimal("0.01"))
    total = subtotal + tax + (delta if up else -delta)
    v = view(line_items=[], subtotal=subtotal, tax_amount=tax, total_amount=total, evidence={})
    assert "TOTAL_MISMATCH" in codes(v)


def test_credit_note_positive_unit_price_negative_amount_is_accepted() -> None:
    lines = [LineView(1, "Return", Decimal("2"), Decimal("50.00"), None, None, None, Decimal("-100.00"))]
    v = view(
        document_type=DocumentType.CREDIT_NOTE,
        line_items=lines,
        subtotal=Decimal("-100.00"),
        tax_amount=Decimal("-10.00"),
        total_amount=Decimal("-110.00"),
        evidence={},
    )
    assert "LINE_TOTAL_MISMATCH" not in codes(v)
    # The same line on a normal invoice is still a mismatch.
    assert "LINE_TOTAL_MISMATCH" in codes(
        view(line_items=lines, subtotal=Decimal("-100.00"), tax_amount=Decimal("-10.00"), total_amount=Decimal("-110.00"), evidence={})
    )
