from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.shared.dates import parse_date
from app.shared.money import detect_currency_token, parse_amount, quantize_money, to_decimal
from app.shared.text import normalize_invoice_number, normalize_supplier, safe_display_filename


@pytest.mark.parametrize(
    ("raw", "expected", "ambiguous"),
    [
        ("1,234.56", "1234.56", False),
        ("1.234,56", "1234.56", False),
        ("1 234,56", "1234.56", False),
        ("1'234.56", "1234.56", False),
        ("(1,234.56)", "-1234.56", False),
        ("-12.50", "-12.50", False),
        ("12.50-", "-12.50", False),
        ("USD 1,000.00", "1000.00", False),
        ("€ 5,00", "5.00", False),
        ("12,34,567.00", "1234567.00", False),
        ("1.234.567", "1234567", False),
        ("1,234", "1234", True),
        ("0,123", "0.123", False),
        ("1,23", "1.23", False),
    ],
)
def test_parse_amount_formats(raw: str, expected: str, ambiguous: bool) -> None:
    parsed = parse_amount(raw)
    assert parsed is not None
    assert parsed.value == Decimal(expected)
    assert parsed.ambiguous is ambiguous


@pytest.mark.parametrize("raw", ["abc", "1.2.3", "", "12,3,4", "--5"])
def test_parse_amount_rejects_garbage(raw: str) -> None:
    assert parse_amount(raw) is None


def test_decimal_hint_resolves_ambiguity() -> None:
    p = parse_amount("1,234", decimal_hint=",")
    assert p is not None and p.value == Decimal("1.234") and not p.ambiguous


def test_floats_are_rejected_for_money() -> None:
    with pytest.raises(TypeError):
        to_decimal(1.1)
    assert to_decimal("1.10") == Decimal("1.10")


def test_currency_detection_is_conservative() -> None:
    assert detect_currency_token("Total EUR 10")[0] == "EUR"
    assert detect_currency_token("€10")[0] == "EUR"
    code, candidates = detect_currency_token("$10.00")
    assert code is None and "USD" in candidates and "CAD" in candidates
    code, candidates = detect_currency_token("¥ 500")
    assert code is None and set(candidates) == {"JPY", "CNY"}


def test_quantize_uses_currency_minor_units() -> None:
    assert quantize_money(Decimal("1.005"), "JPY") == Decimal("1")
    assert quantize_money(Decimal("1.0005"), "BHD") == Decimal("1.000")
    assert quantize_money(Decimal("2.345"), "USD") == Decimal("2.34")  # banker's rounding


@given(st.decimals(min_value=Decimal("-99999999.99"), max_value=Decimal("99999999.99"), places=2))
def test_amount_roundtrip_en_and_eu(value: Decimal) -> None:
    en = f"{value:,.2f}"
    eu = en.replace(",", "X").replace(".", ",").replace("X", ".")
    for text in (en, eu):
        parsed = parse_amount(text)
        assert parsed is not None
        assert parsed.value == value


@pytest.mark.parametrize(
    ("raw", "expected", "ambiguous"),
    [
        ("2026-10-28", date(2026, 10, 28), False),
        ("28/10/2026", date(2026, 10, 28), False),
        ("10/28/2026", date(2026, 10, 28), False),
        ("28 Oct 2026", date(2026, 10, 28), False),
        ("October 28, 2026", date(2026, 10, 28), False),
        ("03/04/2026", date(2026, 4, 3), True),
    ],
)
def test_parse_date(raw: str, expected: date, ambiguous: bool) -> None:
    parsed = parse_date(raw, day_first=True)
    assert parsed is not None and parsed.value == expected and parsed.ambiguous is ambiguous


def test_parse_date_rejects_impossible_and_respects_policy() -> None:
    assert parse_date("31/02/2026") is None
    parsed = parse_date("03/04/2026", day_first=False)
    assert parsed is not None and parsed.value == date(2026, 3, 4)


def test_normalization_keys() -> None:
    assert normalize_invoice_number("INV-2026-001") == normalize_invoice_number("2026/001")
    assert normalize_invoice_number("No. 00123") == "00123"
    assert normalize_supplier("ABC Trading Ltd.") == normalize_supplier("A.B.C. Trading Limited") == "abc trading"
    assert normalize_supplier("Müller & Söhne GmbH") == "muller and sohne"


def test_safe_display_filename_strips_paths_and_controls() -> None:
    assert safe_display_filename("../../etc/passwd") == "passwd"
    assert safe_display_filename("C:\\temp\\inv\u0000oice.pdf") == "invoice.pdf"
    assert safe_display_filename("<script>.pdf") == "_script_.pdf"
    assert safe_display_filename("") == "upload"
