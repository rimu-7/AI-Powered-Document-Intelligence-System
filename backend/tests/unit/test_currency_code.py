"""CurrencyCode is the single list of accepted ISO 4217 codes."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.shared.enums import CurrencyCode
from app.shared.money import (
    AMBIGUOUS_SYMBOLS,
    CURRENCY_MINOR_UNITS,
    UNAMBIGUOUS_SYMBOLS,
    detect_currency_token,
    minor_units,
    to_currency_code,
)


def test_every_code_has_minor_units() -> None:
    assert set(CURRENCY_MINOR_UNITS) == set(CurrencyCode)
    assert all(len(c.value) == 3 and c.value.isupper() for c in CurrencyCode)


def test_symbol_tables_only_name_enum_members() -> None:
    assert all(isinstance(c, CurrencyCode) for c in UNAMBIGUOUS_SYMBOLS.values())
    assert all(isinstance(c, CurrencyCode) for codes in AMBIGUOUS_SYMBOLS.values() for c in codes)


def test_migration_constraint_matches_the_enum() -> None:
    # The DB CHECK constraint must accept exactly the enum. A new code needs a new migration.
    path = Path(__file__).parents[2] / "alembic/versions/20261029_0003_invoice_currency_enum.py"
    spec = importlib.util.spec_from_file_location("currency_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.CURRENCY_CODES) == {c.value for c in CurrencyCode}


@pytest.mark.parametrize(
    ("value", "expected"),
    [("USD", CurrencyCode.USD), ("usd", CurrencyCode.USD), (" eur ", CurrencyCode.EUR), (CurrencyCode.GBP, CurrencyCode.GBP)],
)
def test_to_currency_code_accepts_codes(value: object, expected: CurrencyCode) -> None:
    assert to_currency_code(value) is expected


@pytest.mark.parametrize("value", [None, "", "$", "US", "USDX", "XYZ", "Dollar", 840])
def test_to_currency_code_rejects_everything_else(value: object) -> None:
    assert to_currency_code(value) is None


def test_detection_returns_enum_members() -> None:
    code, candidates = detect_currency_token("Total USD 10")
    assert code is CurrencyCode.USD and candidates == (CurrencyCode.USD,)
    code, candidates = detect_currency_token("$10")
    assert code is None and CurrencyCode.USD in candidates and CurrencyCode.EUR not in candidates


def test_minor_units() -> None:
    assert minor_units("JPY") == 0 and minor_units("kwd") == 3 and minor_units(None) == 2 and minor_units("XYZ") == 2
