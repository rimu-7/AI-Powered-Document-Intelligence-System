"""Decide an invoice's currency when the document does not print it unambiguously.

Evidence is tried strongest first; the first step with exactly one answer wins:

1. PRINTED               an ISO code or a single-currency symbol (normalization)
2. DOCUMENT_CONTEXT      the supplier's country: from the grounded supplier
                         address, or, for an ambiguous symbol, from phone
                         prefixes, web/e-mail domains and tax-ID labels on the page
3. SUPPLIER_HISTORY      this supplier's earlier invoices whose currency was
                         printed or set by a reviewer
4. ORGANIZATION_RULE     an admin rule for the symbol ("$" means USD)
5. LEARNED               reviewers resolved the symbol the same way at least
                         LEARN_THRESHOLD times and never differently
6. ORGANIZATION_DEFAULT  the organization's default currency

No step overrides what is printed: "$" can become USD, CAD, AUD, … but never
EUR. Every automatic decision is marked DERIVED, carries its reason, and adds a
non-blocking CURRENCY_INFERRED note, so a reviewer sees why and can change it.
When nothing decides, the candidates are ranked by the evidence seen so the
reviewer can confirm the most likely one with a single click.

This module is pure (no database); ``currency_policy`` supplies the history and
organization settings and applies decisions to stored invoices.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from app.modules.extraction.schemas import Evidence, NormalizationNote, NormalizedInvoice
from app.shared.enums import CurrencyCode, CurrencySource
from app.shared.money import AMBIGUOUS_SYMBOLS, detect_currency_token

C = CurrencyCode

# Reviewer decisions needed before a symbol is resolved the same way automatically.
LEARN_THRESHOLD = 2

_US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|"
    "RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|PR"
)
_CA_PROVINCES = "AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT"
_AU_STATES = "NSW|VIC|QLD|WA|SA|TAS|ACT|NT"

_EURO_COUNTRIES = (
    "Germany|Deutschland|France|Italy|Italia|Spain|España|Espana|Netherlands|Nederland|Belgium|België|Belgique|Austria|"
    "Österreich|Osterreich|(?<!Northern )Ireland|Portugal|Finland|Suomi|Greece|Luxembourg|Slovakia|Slovenia|Estonia|"
    "Latvia|Lithuania|Croatia|Malta|Cyprus"
)

# (currency, country as written in a sentence, pattern). A pattern needs the
# country's name or a structured postcode, so "Washington Ave" is not evidence.
_COUNTRY_RULES: list[tuple[CurrencyCode, str, re.Pattern[str]]] = [
    (C.USD, "the United States", re.compile(rf"\b(?:{_US_STATES})\s+\d{{5}}(?:-\d{{4}})?\b|\b(?:USA|U\.S\.A\.|United States)\b")),
    (C.CAD, "Canada", re.compile(rf"\b(?:{_CA_PROVINCES})\s+[A-Z]\d[A-Z]\s?\d[A-Z]\d\b|\bCanada\b")),
    (C.AUD, "Australia", re.compile(rf"\b(?:{_AU_STATES})\s+\d{{4}}\b|\bAustralia\b")),
    (C.NZD, "New Zealand", re.compile(r"\bNew Zealand\b|\bAotearoa\b")),
    (C.SGD, "Singapore", re.compile(r"\bSingapore\b")),
    (C.HKD, "Hong Kong", re.compile(r"\bHong Kong\b")),
    (C.MXN, "Mexico", re.compile(r"\bM[eé]xico\b")),
    (C.ARS, "Argentina", re.compile(r"\bArgentina\b")),
    (C.CLP, "Chile", re.compile(r"\bChile\b")),
    (C.COP, "Colombia", re.compile(r"\bColombia\b")),
    (C.PEN, "Peru", re.compile(r"\bPer[uú]\b")),
    (C.BRL, "Brazil", re.compile(r"\bBra[sz]il\b")),
    (C.JPY, "Japan", re.compile(r"\bJapan\b|日本")),
    (C.CNY, "China", re.compile(r"\b(?:China|PRC)\b|中国")),
    (C.KRW, "South Korea", re.compile(r"\b(?:South Korea|Republic of Korea)\b|대한민국")),
    (C.TWD, "Taiwan", re.compile(r"\bTaiwan\b")),
    (C.SEK, "Sweden", re.compile(r"\bSweden\b|\bSverige\b")),
    (C.NOK, "Norway", re.compile(r"\bNorway\b|\bNorge\b")),
    (C.DKK, "Denmark", re.compile(r"\bDenmark\b|\bDanmark\b")),
    (C.ISK, "Iceland", re.compile(r"\bIceland\b|\bÍsland\b")),
    (C.INR, "India", re.compile(r"\bIndia\b|\bBharat\b")),
    (C.PKR, "Pakistan", re.compile(r"\bPakistan\b")),
    (C.LKR, "Sri Lanka", re.compile(r"\bSri Lanka\b")),
    (C.BDT, "Bangladesh", re.compile(r"\bBangladesh\b")),
    (C.ZAR, "South Africa", re.compile(r"\bSouth Africa\b")),
    (C.GBP, "the United Kingdom", re.compile(r"\b(?:United Kingdom|Great Britain|England|Scotland|Wales|Northern Ireland|UK|U\.K\.)\b")),
    (C.CHF, "Switzerland", re.compile(r"\b(?:Switzerland|Schweiz|Suisse|Svizzera)\b")),
    (C.EUR, "the euro area", re.compile(rf"\b(?:{_EURO_COUNTRIES})\b")),
    (C.PLN, "Poland", re.compile(r"\bPoland\b|\bPolska\b")),
    (C.CZK, "Czechia", re.compile(r"\bCzech(?:ia| Republic)\b")),
    (C.HUF, "Hungary", re.compile(r"\bHungary\b|\bMagyarország\b")),
    (C.RON, "Romania", re.compile(r"\bRom[aâ]nia\b")),
    (C.BGN, "Bulgaria", re.compile(r"\bBulgaria\b")),
    (C.THB, "Thailand", re.compile(r"\bThailand\b")),
    (C.MYR, "Malaysia", re.compile(r"\bMalaysia\b")),
    (C.IDR, "Indonesia", re.compile(r"\bIndonesia\b")),
    (C.PHP, "the Philippines", re.compile(r"\bPhilippines\b")),
    (C.VND, "Vietnam", re.compile(r"\bViet ?Nam\b")),
    (C.AED, "the United Arab Emirates", re.compile(r"\b(?:United Arab Emirates|UAE|Dubai|Abu Dhabi)\b")),
    (C.SAR, "Saudi Arabia", re.compile(r"\b(?:Saudi Arabia|KSA)\b")),
    (C.QAR, "Qatar", re.compile(r"\bQatar\b")),
    (C.BHD, "Bahrain", re.compile(r"\bBahrain\b")),
    (C.KWD, "Kuwait", re.compile(r"\bKuwait\b")),
    (C.OMR, "Oman", re.compile(r"\bSultanate of Oman\b|\bOman\b")),
    (C.ILS, "Israel", re.compile(r"\bIsrael\b")),
    (C.TRY, "Türkiye", re.compile(r"\b(?:Turkey|Türkiye|Turkiye)\b")),
    (C.NGN, "Nigeria", re.compile(r"\bNigeria\b")),
    (C.KES, "Kenya", re.compile(r"\bKenya\b")),
    (C.EGP, "Egypt", re.compile(r"\bEgypt\b")),
    (C.MAD, "Morocco", re.compile(r"\bMorocco\b|\bMaroc\b")),
    (C.RUB, "Russia", re.compile(r"\bRussia(?:n Federation)?\b")),
    (C.UAH, "Ukraine", re.compile(r"\bUkraine\b")),
]
_COUNTRY_OF = {code: label for code, label, _ in _COUNTRY_RULES}

# International dialling codes that belong to one currency (+1 is shared by the
# US and Canada, so it is not evidence).
_PHONE_CODES: dict[str, CurrencyCode] = {
    "44": C.GBP, "61": C.AUD, "64": C.NZD, "65": C.SGD, "852": C.HKD, "52": C.MXN, "54": C.ARS, "56": C.CLP,
    "57": C.COP, "51": C.PEN, "55": C.BRL, "81": C.JPY, "86": C.CNY, "82": C.KRW, "886": C.TWD, "46": C.SEK,
    "47": C.NOK, "45": C.DKK, "354": C.ISK, "91": C.INR, "92": C.PKR, "94": C.LKR, "880": C.BDT, "27": C.ZAR,
    "41": C.CHF, "49": C.EUR, "33": C.EUR, "39": C.EUR, "34": C.EUR, "31": C.EUR, "32": C.EUR, "43": C.EUR,
    "353": C.EUR, "351": C.EUR, "358": C.EUR, "30": C.EUR, "352": C.EUR, "48": C.PLN, "420": C.CZK, "36": C.HUF,
    "40": C.RON, "359": C.BGN, "66": C.THB, "60": C.MYR, "62": C.IDR, "63": C.PHP, "84": C.VND, "971": C.AED,
    "966": C.SAR, "974": C.QAR, "973": C.BHD, "965": C.KWD, "968": C.OMR, "962": C.JOD, "216": C.TND,
    "972": C.ILS, "90": C.TRY, "234": C.NGN, "254": C.KES, "20": C.EGP, "212": C.MAD, "380": C.UAH,
}  # fmt: skip
_PHONE_RE = re.compile(r"(?<![\w+])\+(\d{1,3})[\s\-.(]")

# Country-code domains in an e-mail address or URL. Generic-looking ccTLDs
# (.co, .io, .ai, .me, .tv) are left out on purpose.
_DOMAINS: dict[str, CurrencyCode] = {
    "us": C.USD, "ca": C.CAD, "au": C.AUD, "nz": C.NZD, "sg": C.SGD, "hk": C.HKD, "mx": C.MXN, "ar": C.ARS,
    "cl": C.CLP, "pe": C.PEN, "br": C.BRL, "jp": C.JPY, "cn": C.CNY, "kr": C.KRW, "tw": C.TWD, "se": C.SEK,
    "no": C.NOK, "dk": C.DKK, "is": C.ISK, "in": C.INR, "pk": C.PKR, "lk": C.LKR, "bd": C.BDT, "za": C.ZAR,
    "uk": C.GBP, "ch": C.CHF, "de": C.EUR, "fr": C.EUR, "it": C.EUR, "es": C.EUR, "nl": C.EUR, "be": C.EUR,
    "at": C.EUR, "ie": C.EUR, "pt": C.EUR, "fi": C.EUR, "gr": C.EUR, "lu": C.EUR, "pl": C.PLN, "cz": C.CZK,
    "hu": C.HUF, "ro": C.RON, "bg": C.BGN, "th": C.THB, "my": C.MYR, "id": C.IDR, "ph": C.PHP, "vn": C.VND,
    "ae": C.AED, "sa": C.SAR, "qa": C.QAR, "bh": C.BHD, "kw": C.KWD, "om": C.OMR, "jo": C.JOD, "tn": C.TND,
    "il": C.ILS, "tr": C.TRY, "ng": C.NGN, "ke": C.KES, "eg": C.EGP, "ma": C.MAD, "ua": C.UAH,
}  # fmt: skip
_DOMAIN_RE = re.compile(r"(?:https?://|www\.|@)[\w-]+(?:\.[\w-]+)*\.([a-z]{2})(?![\w.-]*[\w])", re.IGNORECASE)

# Tax registration labels used by one country's tax authority.
_TAX_IDS: list[tuple[CurrencyCode, str, re.Pattern[str]]] = [
    (C.AUD, "ABN", re.compile(r"\bA\.?B\.?N\b")),
    (C.CAD, "GST/HST number", re.compile(r"\b(?:GST/HST|HST|QST)\b")),
    (C.NZD, "NZBN", re.compile(r"\bNZBN\b")),
    (C.SGD, "UEN", re.compile(r"\bUEN\b")),
    (C.INR, "GSTIN", re.compile(r"\bGSTIN\b")),
    (C.MXN, "RFC", re.compile(r"\bR\.?F\.?C\.?(?=\s*[:#])")),
    (C.ARS, "CUIT", re.compile(r"\bCUIT\b")),
    (C.BRL, "CNPJ", re.compile(r"\bCNPJ\b")),
    (C.NOK, "MVA number", re.compile(r"\bMVA\b")),
    (C.DKK, "CVR number", re.compile(r"\bCVR\b")),
    (C.USD, "EIN", re.compile(r"\bEIN\b")),
]

SignalKind = Literal["address", "phone", "domain", "tax_id"]


@dataclass(frozen=True)
class Signal:
    currency: CurrencyCode
    kind: SignalKind
    text: str


@dataclass(frozen=True)
class Decision:
    currency: CurrencyCode
    source: CurrencySource
    reason: str


@dataclass
class OrganizationPolicy:
    """What the organization contributes: settings and reviewers' past choices."""

    default_currency: CurrencyCode | None = None
    symbol_rules: dict[str, CurrencyCode] = field(default_factory=dict)
    # symbol -> {currency: number of invoices a reviewer resolved that way}
    reviewer_choices: dict[str, Counter[CurrencyCode]] = field(default_factory=dict)

    def learned(self, symbol: str) -> tuple[CurrencyCode, int] | None:
        counts = self.reviewer_choices.get(symbol)
        if not counts or len(counts) != 1:
            return None
        ((code, n),) = counts.items()
        return (code, n) if n >= LEARN_THRESHOLD else None


def candidates_for(raw: str | None) -> tuple[CurrencyCode, ...] | None:
    """Currencies the printed marker allows.

    Every currency when nothing is printed; None for a marker that names no
    known currency (that one is left to a reviewer).
    """
    token = (raw or "").strip()
    if not token:
        return tuple(CurrencyCode)
    if token in AMBIGUOUS_SYMBOLS:
        return AMBIGUOUS_SYMBOLS[token]
    code, candidates = detect_currency_token(token)
    if code is not None:
        return (code,)
    return candidates or None


def _read_as(raw: str | None, code: CurrencyCode) -> str:
    token = (raw or "").strip()
    return f"'{token}' read as {code}" if token else f"No currency printed; read as {code}"


def country_signals(address: str, candidates: Iterable[CurrencyCode]) -> list[Signal]:
    allowed = set(candidates)
    return [
        Signal(code, "address", m.group(0)) for code, _, pattern in _COUNTRY_RULES if code in allowed and (m := pattern.search(address))
    ]


def page_signals(text: str, candidates: Iterable[CurrencyCode]) -> list[Signal]:
    """Phone prefixes, country domains and tax-ID labels on the page."""
    allowed = set(candidates)
    found: list[Signal] = []
    for m in _PHONE_RE.finditer(text):
        code = _PHONE_CODES.get(m.group(1))
        if code in allowed:
            found.append(Signal(code, "phone", f"+{m.group(1)}"))
    for m in _DOMAIN_RE.finditer(text):
        code = _DOMAINS.get(m.group(1).lower())
        if code in allowed:
            found.append(Signal(code, "domain", f".{m.group(1).lower()}"))
    for code, label, pattern in _TAX_IDS:
        if code in allowed and pattern.search(text):
            found.append(Signal(code, "tax_id", label))
    return found


def supplier_country_currency(address: str, candidates: tuple[CurrencyCode, ...]) -> tuple[CurrencyCode, str, str] | None:
    """(currency, country, matched text) when the address points to exactly one candidate."""
    signals = country_signals(address, candidates)
    if len({s.currency for s in signals}) != 1:
        return None
    first = signals[0]
    return first.currency, _COUNTRY_OF[first.currency], first.text


def _describe(signals: list[Signal]) -> str:
    labels = {"phone": "phone number", "domain": "web address", "tax_id": ""}
    parts = []
    for s in signals:
        kind = labels[s.kind]
        parts.append(f"{s.text} {kind}".strip())
    return ", ".join(dict.fromkeys(parts))


def decide_from_document(
    raw: str | None, candidates: tuple[CurrencyCode, ...], supplier_address: str | None, page_text: str
) -> tuple[Decision | None, list[Signal]]:
    """Step 2. Returns the decision (if any) and every signal seen, for ranking."""
    address_signals = country_signals(supplier_address, candidates) if supplier_address else []
    codes = {s.currency for s in address_signals}
    if len(codes) == 1:
        s = address_signals[0]
        return (
            Decision(
                s.currency,
                CurrencySource.DOCUMENT_CONTEXT,
                f"{_read_as(raw, s.currency)}: the supplier's address is in {_COUNTRY_OF[s.currency]} ({s.text})",
            ),
            address_signals,
        )
    if len(codes) > 1 or not raw or not raw.strip():
        # Conflicting addresses decide nothing; with no printed marker only the
        # supplier's own address is strong enough.
        return None, address_signals
    signals = page_signals(page_text, candidates)
    codes = {s.currency for s in signals}
    if len(codes) == 1:
        code = next(iter(codes))
        return (
            Decision(
                code,
                CurrencySource.DOCUMENT_CONTEXT,
                f"{_read_as(raw, code)}: the page points to {_COUNTRY_OF[code]} ({_describe(signals)})",
            ),
            signals,
        )
    return None, signals


def decide_for_organization(
    raw: str | None, candidates: tuple[CurrencyCode, ...], supplier_history: Mapping[CurrencyCode, int], policy: OrganizationPolicy
) -> Decision | None:
    """Steps 3–6."""
    symbol = (raw or "").strip()
    allowed = set(candidates)
    history = {c: n for c, n in supplier_history.items() if c in allowed and n > 0}
    if len(history) == 1:
        ((code, n),) = history.items()
        invoices = "invoice" if n == 1 else "invoices"
        return Decision(
            code, CurrencySource.SUPPLIER_HISTORY, f"{_read_as(raw, code)}: {n} earlier {invoices} from this supplier used {code}"
        )
    if len(history) > 1:
        return None  # the supplier bills in several currencies: a person decides
    if symbol:
        rule = policy.symbol_rules.get(symbol)
        if rule is not None and rule in allowed:
            return Decision(rule, CurrencySource.ORGANIZATION_RULE, f"{_read_as(raw, rule)} by your organization's rule for '{symbol}'")
        learned = policy.learned(symbol)
        if learned is not None and learned[0] in allowed:
            code, n = learned
            return Decision(
                code, CurrencySource.LEARNED, f"{_read_as(raw, code)}: reviewers chose {code} for '{symbol}' on {n} earlier invoices"
            )
    default = policy.default_currency
    if default is not None and default in allowed:
        return Decision(default, CurrencySource.ORGANIZATION_DEFAULT, f"{_read_as(raw, default)}, your organization's default currency")
    return None


def rank_candidates(
    candidates: tuple[CurrencyCode, ...],
    signals: Iterable[Signal] = (),
    supplier_history: Mapping[CurrencyCode, int] | None = None,
    policy: OrganizationPolicy | None = None,
    symbol: str = "",
) -> list[CurrencyCode]:
    """Candidates ordered by how much evidence points to each (stable otherwise)."""
    score: Counter[CurrencyCode] = Counter()
    for s in signals:
        score[s.currency] += 3 if s.kind == "address" else 1
    for code, n in (supplier_history or {}).items():
        score[code] += 2 * n
    if policy is not None:
        for code, n in policy.reviewer_choices.get(symbol, Counter()).items():
            score[code] += n
        if policy.default_currency is not None:
            score[policy.default_currency] += 1
    order = {c: i for i, c in enumerate(candidates)}
    return sorted(candidates, key=lambda c: (-score[c], order[c]))


def apply_decision(inv: NormalizedInvoice, decision: Decision) -> None:
    """Set the currency on an extracted invoice, keeping where the symbol was printed."""
    printed = inv.evidence.get("currency")
    address = inv.evidence.get("supplier_address") if decision.source == CurrencySource.DOCUMENT_CONTEXT else None
    anchor = printed or address
    inv.currency = decision.currency
    inv.currency_source = decision.source
    inv.evidence["currency"] = Evidence(
        document_id=anchor.document_id if anchor else None,
        page_number=anchor.page_number if anchor else None,
        supporting_text=(anchor.supporting_text if anchor else None),
        bounding_box=anchor.bounding_box if anchor else None,
        extraction_method=f"currency:{decision.source.value.lower()}",
        support="DERIVED",
        reason=decision.reason,
    )
    inv.notes = [n for n in inv.notes if not (n.field == "currency" and n.code in ("CURRENCY_AMBIGUOUS", "CURRENCY_INFERRED"))]
    inv.notes.append(NormalizationNote(field="currency", code="CURRENCY_INFERRED", message=decision.reason))


def resolve_from_document(inv: NormalizedInvoice, page_text: str = "") -> list[Signal]:
    """Step 2 on an extracted invoice. Returns the signals seen (for later ranking)."""
    if inv.currency is not None:
        return []
    candidates = candidates_for(inv.currency_raw)
    if candidates is None:
        return []
    address_ev = inv.evidence.get("supplier_address")
    grounded_address = inv.supplier_address if address_ev is not None and address_ev.support == "SUPPORTED" else None
    decision, signals = decide_from_document(inv.currency_raw, candidates, grounded_address, page_text)
    if decision is not None:
        apply_decision(inv, decision)
    elif signals and inv.currency_raw:
        inv.alternatives["currency"] = list(rank_candidates(candidates, signals))
    return signals
