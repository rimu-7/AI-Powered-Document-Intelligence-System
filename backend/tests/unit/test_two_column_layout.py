"""Two-column invoice headers as OCR returns them (columns joined on one line).

The text below is the OCR output of a real upload: supplier block on the
right, title "INVOICE" misread as "| NVOICE", customer address next to the
"Invoice Details" column, and only "$" as the currency marker.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.extraction.crosscheck import cross_check
from app.modules.extraction.currency_resolution import resolve_from_document, supplier_country_currency
from app.modules.extraction.grounding import GroundingPage, ground_invoice
from app.modules.extraction.normalization import normalize_invoice
from app.modules.extraction.providers.base import ExtractionRequest
from app.modules.extraction.providers.fixture import LocalRulesProvider, _is_title
from app.modules.extraction.schemas import NormalizedInvoice, RawField, RawInvoice
from app.modules.validation.rules import DuplicateCandidate, rule_duplicates

OCR_TEXT = """| NVOICE        VexaX Solutions Inc.
123 Business Ave
INV-2023-00147        San Francisco, CA 94107
Bill To:        Invoice Details:
Global Tech Enterprises    Invoice #:  INV-2023-00147
456 Corporate Blvd       Invoice Date:  Oct 15, 2023
New York, NY 10001     Due Date:   Nov 14, 2023
Status:
Description        Qty UnitPrice  Amount
Website Design & Development  8  $1200.00 $9600.00
Monthly Website Maintenance   8  $150.00  $1200.00
Premium WordPress Theme   7  $89.00  $623.00
SEO Optimization Package    1  $450.00  $450.00
New Item        8  $320.00 $2560.00
New Item        5  $12.00  $60.00
Subtotal        $14493.00
Tax (8.5%)        $1231.91
Discount        $0.00
Total Amount        $15724.91
"""


def _rules_raw() -> RawInvoice:
    result = LocalRulesProvider().extract_invoice(ExtractionRequest(document_text=OCR_TEXT, text_method="ocr"))
    return result.extraction.invoices[0]


def _normalized(raw: RawInvoice) -> NormalizedInvoice:
    inv = normalize_invoice(raw, segment_index=0, page_start=1, page_end=1)
    ground_invoice(inv, raw, {1: GroundingPage(page_number=1, text=OCR_TEXT, method="ocr")}, "doc")
    return inv


def test_rules_read_each_column_separately() -> None:
    raw = _rules_raw()
    assert raw.supplier_name.value == "VexaX Solutions Inc."
    assert raw.supplier_address.value == "123 Business Ave, San Francisco, CA 94107"
    assert raw.customer_name.value == "Global Tech Enterprises"
    assert raw.customer_address.value == "456 Corporate Blvd, New York, NY 10001"  # stops before "Status:"
    assert raw.invoice_number.value == "INV-2023-00147"
    assert raw.invoice_date.value == "Oct 15, 2023"
    assert raw.payment_due_date.value == "Nov 14, 2023"  # not the ":" after "Due Date"


@pytest.mark.parametrize("cell", ["INVOICE", "| NVOICE", "lNVOICE", "Tax Invoice", "Credit Note", "RECEIPT"])
def test_document_titles_are_not_supplier_names(cell: str) -> None:
    assert _is_title(cell)


@pytest.mark.parametrize("cell", ["VexaX Solutions Inc.", "Invoicely Ltd", "Bill's Plumbing", "Northwind Traders"])
def test_company_names_are_not_titles(cell: str) -> None:
    assert not _is_title(cell)


def test_value_printed_over_two_lines_of_one_column_is_grounded() -> None:
    raw = _rules_raw()
    raw.customer_address = RawField(value="456 Corporate Blvd New York, NY 10001", page=1, evidence=None)
    raw.supplier_address = RawField(value="123 Business Ave, San Francisco, CA 94107", page=1, evidence=None)
    inv = _normalized(raw)
    for name in ("customer_address", "supplier_address"):
        assert inv.evidence[name].support == "SUPPORTED", name
    assert inv.evidence["customer_address"].supporting_text == "456 Corporate Blvd, New York, NY 10001"


def test_text_that_is_not_in_the_source_stays_unsupported() -> None:
    raw = _rules_raw()
    raw.customer_address = RawField(value="456 Corporate Blvd Boston, MA 02110", page=1, evidence=None)
    raw.supplier_address = RawField(value="456 Corporate Blvd San Francisco, CA 94107", page=1, evidence=None)  # mixes columns
    inv = _normalized(raw)
    assert inv.evidence["customer_address"].support == "UNSUPPORTED"
    assert inv.evidence["supplier_address"].support == "UNSUPPORTED"


def test_cross_check_ignores_punctuation_only_differences() -> None:
    rules = _normalized(_rules_raw())
    llm_raw = _rules_raw()
    llm_raw.customer_address = RawField(value="456 Corporate Blvd New York, NY 10001", page=1, evidence=None)
    merged = cross_check(_normalized(llm_raw), rules)
    assert not [n for n in merged.notes if n.code == "EXTRACTOR_DISAGREEMENT"]


def test_dollar_resolved_from_grounded_supplier_address() -> None:
    inv = _normalized(_rules_raw())
    assert inv.currency is None and inv.currency_raw == "$"
    resolve_from_document(inv)
    assert inv.currency == "USD"
    assert inv.evidence["currency"].support == "DERIVED"
    codes = [n.code for n in inv.notes]
    assert "CURRENCY_INFERRED" in codes and "CURRENCY_AMBIGUOUS" not in codes
    assert inv.total_amount == Decimal("15724.91")


def test_dollar_not_resolved_without_supplier_country_evidence() -> None:
    raw = _rules_raw()
    raw.supplier_address = RawField(value=None, page=None, evidence=None)
    inv = _normalized(raw)
    resolve_from_document(inv)
    assert inv.currency is None


def test_dollar_not_resolved_from_an_ungrounded_address() -> None:
    raw = _rules_raw()
    raw.supplier_address = RawField(value="1 Main St, Toronto, ON M5V 2T6", page=1, evidence=None)  # not on the page
    inv = _normalized(raw)
    resolve_from_document(inv)
    assert inv.currency is None


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("123 Business Ave, San Francisco, CA 94107", "USD"),
        ("1 Main St, Toronto, ON M5V 2T6", "CAD"),
        ("10 George St, Sydney NSW 2000", "AUD"),
        ("5 Queen St, Auckland, New Zealand", "NZD"),
        ("Washington Ave 12, Berlin", None),  # a US state name in a street is not evidence
        ("Toronto, ON M5V 2T6, shipping from Buffalo, NY 14201", None),  # two countries: no decision
    ],
)
def test_supplier_country_currency(address: str, expected: str | None) -> None:
    found = supplier_country_currency(address, ("USD", "CAD", "AUD", "NZD", "SGD", "HKD", "MXN"))
    assert (found[0] if found else None) == expected


def test_duplicate_names_the_other_file_and_ignores_unknown_currency() -> None:
    inv = _normalized(_rules_raw())
    resolve_from_document(inv)  # this copy now has USD; the earlier copy had no currency
    other = DuplicateCandidate(
        invoice_id="i",
        document_id="d",
        invoice_date=inv.invoice_date,
        total_amount=inv.total_amount,
        currency=None,
        filename="1_Invoice Print.pdf",
        review_status="APPROVED",
    )
    view = SimpleNamespace(total_amount=inv.total_amount, currency=inv.currency, invoice_date=inv.invoice_date, evidence={})
    (issue,) = rule_duplicates(view, SimpleNamespace(duplicate_candidates=[other]))  # type: ignore[arg-type]
    assert issue.severity == "ERROR"
    assert "'1_Invoice Print.pdf'" in issue.message
    assert issue.details["other_filename"] == "1_Invoice Print.pdf"


BROWSER_PRINT_TEXT = """Invoice Print        https://tools.example.com/invoice-generator
INVOICE
INV-2023-00147
VexaX Solutions Inc.
123 Business Ave
San Francisco, CA 94107
Bill To:
Global Tech Enterprises
456 Corporate Blvd
New York, NY 10001
Invoice Details:
Invoice #:        INV-2023-00147
Subtotal $14493.00
Total Amount $15724.91
"""


def test_browser_print_header_and_title_are_skipped() -> None:
    result = LocalRulesProvider().extract_invoice(ExtractionRequest(document_text=BROWSER_PRINT_TEXT, text_method="native"))
    raw = result.extraction.invoices[0]
    assert raw.supplier_name.value == "VexaX Solutions Inc."
    assert raw.supplier_address.value == "123 Business Ave, San Francisco, CA 94107"
    assert raw.customer_address.value == "456 Corporate Blvd, New York, NY 10001"


NO_SUPPLIER_TEXT = """INVOICE #1098
Date: 2026-07-11
Bill To:
Test Client 98
934 System Drive
Suite 34
Tech City, TC 99999
Item Description  Quantity      Unit Price      Total
System Test Module 3        $281.48      $844.44
A
System Test Module 5        $112.61      $563.05
B
Total Amount Due: $2098.09
"""


def test_table_header_and_customer_are_never_the_supplier() -> None:
    # The page prints no supplier: the item table's header row and the "Bill To"
    # block must not be read as one (they were, and the cross-check took it).
    result = LocalRulesProvider().extract_invoice(ExtractionRequest(document_text=NO_SUPPLIER_TEXT, text_method="native"))
    (raw,) = result.extraction.invoices
    assert raw.supplier_name.value is None and raw.supplier_address.value is None
    assert raw.total_amount.value is not None and "2098.09" in raw.total_amount.value
