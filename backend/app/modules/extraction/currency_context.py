"""Resolve an ambiguous currency symbol from the supplier's country.

"$" alone could be USD, CAD, AUD and others, so normalization leaves the
currency empty. When the supplier's address *as printed on the document*
(grounded, not guessed) clearly places the supplier in one country, and that
country's currency is one of the symbol's candidates, the currency is set to it.
The value is marked DERIVED and an INFO note says exactly why, so a reviewer
can see and override it. Without clear evidence nothing is changed.
"""

from __future__ import annotations

import re

from app.modules.extraction.schemas import Evidence, NormalizationNote, NormalizedInvoice
from app.shared.enums import CurrencyCode
from app.shared.money import AMBIGUOUS_SYMBOLS

_US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|"
    "RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|PR"
)
_CA_PROVINCES = "AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT"
_AU_STATES = "NSW|VIC|QLD|WA|SA|TAS|ACT|NT"

# (currency, country label, pattern). Patterns need a structured postcode or the
# country name, so a street called "Washington Ave" does not count.
_COUNTRY_RULES: list[tuple[CurrencyCode, str, re.Pattern[str]]] = [
    (
        CurrencyCode.USD,
        "the United States",
        re.compile(rf"\b(?:{_US_STATES})\s+\d{{5}}(?:-\d{{4}})?\b|\b(?:USA|U\.S\.A\.|United States)\b"),
    ),
    (CurrencyCode.CAD, "Canada", re.compile(rf"\b(?:{_CA_PROVINCES})\s+[A-Z]\d[A-Z]\s?\d[A-Z]\d\b|\bCanada\b")),
    (CurrencyCode.AUD, "Australia", re.compile(rf"\b(?:{_AU_STATES})\s+\d{{4}}\b|\bAustralia\b")),
    (CurrencyCode.NZD, "New Zealand", re.compile(r"\bNew Zealand\b")),
    (CurrencyCode.SGD, "Singapore", re.compile(r"\bSingapore\b")),
    (CurrencyCode.HKD, "Hong Kong", re.compile(r"\bHong Kong\b")),
    (CurrencyCode.MXN, "Mexico", re.compile(r"\bM[eé]xico\b")),
    (CurrencyCode.JPY, "Japan", re.compile(r"\bJapan\b|日本")),
    (CurrencyCode.CNY, "China", re.compile(r"\b(?:China|PRC)\b|中国")),
    (CurrencyCode.SEK, "Sweden", re.compile(r"\bSweden\b|\bSverige\b")),
    (CurrencyCode.NOK, "Norway", re.compile(r"\bNorway\b|\bNorge\b")),
    (CurrencyCode.DKK, "Denmark", re.compile(r"\bDenmark\b|\bDanmark\b")),
]


def supplier_country_currency(address: str, candidates: tuple[CurrencyCode, ...]) -> tuple[CurrencyCode, str, str] | None:
    """(currency, country, matched text) if exactly one candidate country matches."""
    hits = {(code, label, m.group(0)) for code, label, pattern in _COUNTRY_RULES if code in candidates and (m := pattern.search(address))}
    codes = {h[0] for h in hits}
    if len(codes) != 1:
        return None
    return sorted(hits)[0]


def infer_currency(inv: NormalizedInvoice) -> None:
    symbol = (inv.currency_raw or "").strip()
    if inv.currency is not None or symbol not in AMBIGUOUS_SYMBOLS or not inv.supplier_address:
        return
    address_ev = inv.evidence.get("supplier_address")
    if address_ev is None or address_ev.support != "SUPPORTED":
        return
    found = supplier_country_currency(inv.supplier_address, AMBIGUOUS_SYMBOLS[symbol])
    if found is None:
        return
    code, country, matched = found
    inv.currency = code
    inv.evidence["currency"] = Evidence(
        document_id=address_ev.document_id,
        page_number=address_ev.page_number,
        supporting_text=f"{symbol} · supplier address: {inv.supplier_address}"[:200],
        bounding_box=address_ev.bounding_box,
        extraction_method="derived",
        support="DERIVED",
    )
    inv.notes = [n for n in inv.notes if not (n.field == "currency" and n.code == "CURRENCY_AMBIGUOUS")]
    inv.notes.append(
        NormalizationNote(
            field="currency",
            code="CURRENCY_INFERRED",
            message=f"'{symbol}' read as {code} because the supplier's address is in {country} ({matched})",
        )
    )
