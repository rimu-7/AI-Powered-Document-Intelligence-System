"""Automatic currency resolution: document evidence first, then organization knowledge."""

from __future__ import annotations

from collections import Counter

import pytest

from app.modules.extraction.currency_resolution import (
    LEARN_THRESHOLD,
    OrganizationPolicy,
    apply_decision,
    candidates_for,
    decide_for_organization,
    decide_from_document,
    page_signals,
    rank_candidates,
    resolve_from_document,
)
from app.modules.extraction.schemas import Evidence, NormalizationNote, NormalizedInvoice
from app.shared.enums import CurrencyCode as C
from app.shared.enums import CurrencySource as S
from app.shared.money import AMBIGUOUS_SYMBOLS

DOLLAR = AMBIGUOUS_SYMBOLS["$"]
ALL = candidates_for(None)


def test_candidates_for_printed_markers() -> None:
    assert candidates_for("$") == DOLLAR
    assert candidates_for("kr") == AMBIGUOUS_SYMBOLS["kr"]
    assert candidates_for(None) == tuple(C) and candidates_for("  ") == tuple(C)
    assert candidates_for("USD") == (C.USD,)
    assert candidates_for("Florins") is None  # unknown: left to a reviewer


# --- step 2: the document -------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("123 Business Ave, San Francisco, CA 94107", C.USD),
        ("1 Main St, Toronto, ON M5V 2T6", C.CAD),
        ("10 George St, Sydney NSW 2000", C.AUD),
        ("Unit 4, Harbour Road", None),
        ("Washington Ave 12, Berlin", None),  # a US state in a street name is not evidence
        ("Toronto, ON M5V 2T6, shipping from Buffalo, NY 14201", None),  # two countries: no decision
    ],
)
def test_dollar_from_the_supplier_address(address: str, expected: C | None) -> None:
    decision, _ = decide_from_document("$", DOLLAR, address, "")
    assert (decision.currency if decision else None) == expected
    if decision:
        assert decision.source == S.DOCUMENT_CONTEXT and "supplier's address" in decision.reason


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ("Phone +61 2 9999 0000 · ABN 12 345 678 901", C.AUD),
        ("billing@harbour.co.nz", C.NZD),
        ("www.maple-supplies.ca  GST/HST 123456789RT0001", C.CAD),
        ("UEN 201912345K", C.SGD),
        ("Call +1 415 555 0100", None),  # +1 is shared by the US and Canada
        ("+61 2 9999 0000 and accounts@acme.ca", None),  # two countries: no decision
        ("see https://tools.example.com/invoice", None),  # .com says nothing about a country
    ],
)
def test_dollar_from_phone_domain_and_tax_id(page: str, expected: C | None) -> None:
    decision, signals = decide_from_document("$", DOLLAR, "Unit 4, Harbour Road", page)
    assert (decision.currency if decision else None) == expected
    if expected is None and signals:
        assert len({s.currency for s in signals}) > 1


def test_address_beats_page_signals() -> None:
    decision, _ = decide_from_document("$", DOLLAR, "88 Pine Ave, Denver, CO 80202", "Customer ABN 12 345 678 901")
    assert decision is not None and decision.currency == C.USD


def test_nothing_printed_uses_only_the_supplier_address() -> None:
    decision, _ = decide_from_document(None, ALL, "Hafenstrasse 22, 20457 Hamburg, Germany", "")
    assert decision is not None and decision.currency == C.EUR
    assert decision.reason.startswith("No currency printed; read as EUR")
    # Without an address, phone numbers and domains are not enough.
    decision, _ = decide_from_document(None, ALL, None, "Phone +49 40 123456, www.delta.de")
    assert decision is None


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("5 Donegall Square, Belfast, Northern Ireland", C.GBP),  # not the Republic of Ireland
        ("1 Grafton Street, Dublin, Ireland", C.EUR),
        ("200 Main St, Indianapolis, Indiana", None),  # "Indiana" is not India
    ],
)
def test_country_names_are_matched_as_whole_names(address: str, expected: C | None) -> None:
    decision, _ = decide_from_document(None, ALL, address, "")
    assert (decision.currency if decision else None) == expected


def test_signals_never_leave_the_printed_symbol() -> None:
    # A German phone number cannot turn "$" into euros.
    assert page_signals("+49 40 123456", DOLLAR) == []
    decision, _ = decide_from_document("$", DOLLAR, "Hamburg, Germany", "+49 40 123456")
    assert decision is None


# --- steps 3-6: the organization ---------------------------------------------------------


def test_supplier_history_decides_first() -> None:
    policy = OrganizationPolicy(default_currency=C.CAD, symbol_rules={"$": C.AUD})
    decision = decide_for_organization("$", DOLLAR, {C.USD: 3}, policy)
    assert decision is not None and decision.source == S.SUPPLIER_HISTORY and decision.currency == C.USD
    assert "3 earlier invoices" in decision.reason


def test_supplier_billing_in_several_currencies_needs_a_person() -> None:
    policy = OrganizationPolicy(default_currency=C.USD)
    assert decide_for_organization("$", DOLLAR, {C.USD: 2, C.CAD: 1}, policy) is None


def test_history_outside_the_symbol_is_ignored() -> None:
    policy = OrganizationPolicy(symbol_rules={"$": C.USD})
    decision = decide_for_organization("$", DOLLAR, {C.EUR: 5}, policy)
    assert decision is not None and decision.source == S.ORGANIZATION_RULE and decision.currency == C.USD


def test_rule_then_learned_then_default() -> None:
    choices = {"$": Counter({C.CAD: LEARN_THRESHOLD})}
    rule = decide_for_organization("$", DOLLAR, {}, OrganizationPolicy(C.AUD, {"$": C.USD}, choices))
    learned = decide_for_organization("$", DOLLAR, {}, OrganizationPolicy(C.AUD, {}, choices))
    default = decide_for_organization("$", DOLLAR, {}, OrganizationPolicy(C.AUD, {}, {}))
    assert rule is not None and (rule.source, rule.currency) == (S.ORGANIZATION_RULE, C.USD)
    assert learned is not None and (learned.source, learned.currency) == (S.LEARNED, C.CAD)
    assert default is not None and (default.source, default.currency) == (S.ORGANIZATION_DEFAULT, C.AUD)


def test_learning_needs_enough_and_unanimous_decisions() -> None:
    assert OrganizationPolicy(reviewer_choices={"$": Counter({C.USD: LEARN_THRESHOLD - 1})}).learned("$") is None
    assert OrganizationPolicy(reviewer_choices={"$": Counter({C.USD: 5, C.CAD: 1})}).learned("$") is None
    assert OrganizationPolicy(reviewer_choices={"$": Counter({C.USD: LEARN_THRESHOLD})}).learned("$") == (C.USD, LEARN_THRESHOLD)


def test_default_never_overrides_the_printed_symbol() -> None:
    euro_org = OrganizationPolicy(default_currency=C.EUR)
    assert decide_for_organization("$", DOLLAR, {}, euro_org) is None
    decision = decide_for_organization(None, ALL, {}, euro_org)
    assert decision is not None and decision.currency == C.EUR and decision.reason.startswith("No currency printed")


def test_ranking_puts_the_best_evidence_first() -> None:
    policy = OrganizationPolicy(default_currency=C.CAD, reviewer_choices={"$": Counter({C.AUD: 1})})
    ranked = rank_candidates(DOLLAR, (), {C.NZD: 1}, policy, "$")
    # NZD: supplier history; AUD: a reviewer choice; CAD: the default (ties keep the symbol's order).
    assert ranked[:4] == [C.NZD, C.CAD, C.AUD, C.USD]
    assert sorted(ranked) == sorted(DOLLAR)


# --- applying a decision -------------------------------------------------------------------


def _dollar_invoice(address: str | None = None) -> NormalizedInvoice:
    inv = NormalizedInvoice(segment_index=0, currency_raw="$", supplier_address=address)
    inv.evidence["currency"] = Evidence(
        document_id="d",
        page_number=1,
        supporting_text="$ 1,250.00",
        bounding_box=[1, 2, 3, 4],
        extraction_method="llm",
        support="SUPPORTED",
    )
    if address:
        inv.evidence["supplier_address"] = Evidence(page_number=1, supporting_text=address, extraction_method="llm", support="SUPPORTED")
    inv.alternatives["currency"] = list(DOLLAR)
    inv.notes.append(NormalizationNote(field="currency", code="CURRENCY_AMBIGUOUS", message="ambiguous"))
    return inv


def test_apply_decision_keeps_the_symbol_location_and_explains_itself() -> None:
    inv = _dollar_invoice()
    decision = decide_for_organization("$", DOLLAR, {}, OrganizationPolicy(symbol_rules={"$": C.USD}))
    assert decision is not None
    apply_decision(inv, decision)
    ev = inv.evidence["currency"]
    assert inv.currency == C.USD and inv.currency_source == S.ORGANIZATION_RULE
    assert ev.support == "DERIVED" and ev.reason == decision.reason
    assert ev.bounding_box == [1, 2, 3, 4] and ev.page_number == 1  # still points at the printed "$"
    assert [n.code for n in inv.notes] == ["CURRENCY_INFERRED"]


def test_resolve_from_document_needs_a_grounded_address() -> None:
    inv = _dollar_invoice("123 Business Ave, San Francisco, CA 94107")
    resolve_from_document(inv)
    assert inv.currency == C.USD and inv.currency_source == S.DOCUMENT_CONTEXT

    ungrounded = _dollar_invoice("123 Business Ave, San Francisco, CA 94107")
    ungrounded.evidence["supplier_address"] = Evidence(extraction_method="llm", support="UNSUPPORTED")
    resolve_from_document(ungrounded)
    assert ungrounded.currency is None


def test_resolve_from_document_ranks_when_undecided() -> None:
    inv = _dollar_invoice("Unit 4, Harbour Road")
    resolve_from_document(inv, "Phone +61 2 9999 0000 and accounts@acme.ca")
    assert inv.currency is None
    assert set(inv.alternatives["currency"][:2]) == {C.AUD, C.CAD}


def test_printed_currency_is_left_alone() -> None:
    inv = NormalizedInvoice(
        segment_index=0, currency=C.EUR, currency_raw="€", currency_source=S.PRINTED, supplier_address="Toronto, ON M5V 2T6"
    )
    resolve_from_document(inv, "+1 416 555 0100")
    assert inv.currency == C.EUR and inv.currency_source == S.PRINTED
