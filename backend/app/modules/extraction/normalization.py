"""Deterministic normalization of provider output (strings) into typed values."""

from __future__ import annotations

from decimal import Decimal

from app.core.config import get_settings
from app.modules.extraction.schemas import (
    AMOUNT_FIELDS,
    NormalizationNote,
    NormalizedInvoice,
    NormalizedLineItem,
    RawInvoice,
)
from app.shared.dates import parse_date
from app.shared.money import AMBIGUOUS_SYMBOLS, ISO_CURRENCIES, UNAMBIGUOUS_SYMBOLS, detect_currency_token, parse_amount
from app.shared.text import normalize_whitespace, truncate

_TEXT_LIMITS = {
    "invoice_number": 120,
    "supplier_name": 300,
    "customer_name": 300,
    "supplier_tax_id": 80,
    "purchase_order_number": 120,
    "payment_reference": 120,
    "supplier_address": 1000,
    "customer_address": 1000,
}


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = normalize_whitespace(value).strip(" :;,")
    return truncate(cleaned, limit) if cleaned else None


def infer_decimal_separator(raw: RawInvoice) -> str | None:
    """Infer the document's decimal separator from amounts that use both separators."""
    votes = {".": 0, ",": 0}
    samples = [getattr(raw, f).value for f in AMOUNT_FIELDS]
    for item in raw.line_items:
        samples.extend([item.unit_price, item.line_total, item.tax_amount])
    for s in samples:
        if not s:
            continue
        last_dot, last_comma = s.rfind("."), s.rfind(",")
        if last_dot >= 0 and last_comma >= 0:
            votes["." if last_dot > last_comma else ","] += 1
        elif last_comma >= 0 and len(s) - last_comma - 1 == 2:
            votes[","] += 1
        elif last_dot >= 0 and len(s) - last_dot - 1 == 2:
            votes["."] += 1
    if votes["."] == votes[","]:
        return None
    return "." if votes["."] > votes[","] else ","


def _amount(value: str | None, field: str, hint: str | None, notes: list[NormalizationNote]) -> tuple[Decimal | None, str | None]:
    if value is None or not value.strip():
        return None, None
    parsed = parse_amount(value, decimal_hint=hint)
    if parsed is None:
        notes.append(NormalizationNote(field=field, code="AMOUNT_UNPARSEABLE", message=f"Could not parse amount {value!r}"))
        return None, None
    if parsed.ambiguous:
        notes.append(
            NormalizationNote(
                field=field,
                code="AMOUNT_AMBIGUOUS",
                message=f"Separator in {value!r} is ambiguous; {parsed.note or 'interpreted as thousands separator'}",
            )
        )
    return parsed.value, parsed.currency_hint


def _currency(raw_value: str | None, notes: list[NormalizationNote], inv: NormalizedInvoice) -> None:
    if not raw_value:
        return
    token = raw_value.strip()
    inv.currency_raw = token[:20]
    upper = token.upper()
    if upper in ISO_CURRENCIES:
        inv.currency = upper
        return
    if token in UNAMBIGUOUS_SYMBOLS:
        inv.currency = UNAMBIGUOUS_SYMBOLS[token]
        return
    if token in AMBIGUOUS_SYMBOLS:
        inv.alternatives["currency"] = list(AMBIGUOUS_SYMBOLS[token])
        notes.append(
            NormalizationNote(
                field="currency",
                code="CURRENCY_AMBIGUOUS",
                message=f"Symbol {token!r} is used by several currencies; not resolved automatically",
            )
        )
        return
    code, candidates = detect_currency_token(token)
    if code:
        inv.currency = code
    elif candidates:
        inv.alternatives["currency"] = list(candidates)
        notes.append(NormalizationNote(field="currency", code="CURRENCY_AMBIGUOUS", message=f"Currency {token!r} is ambiguous"))
    else:
        notes.append(NormalizationNote(field="currency", code="CURRENCY_UNKNOWN", message=f"Unknown currency {token!r}"))


def _rate(value: str | None) -> Decimal | None:
    if not value:
        return None
    parsed = parse_amount(value.replace("%", "").strip())
    if parsed is None:
        return None
    rate = parsed.value / 100 if "%" in value or parsed.value > 1 else parsed.value
    return rate if Decimal(0) <= rate < Decimal(10) else None


def normalize_invoice(raw: RawInvoice, *, segment_index: int, page_start: int | None, page_end: int | None) -> NormalizedInvoice:
    settings = get_settings()
    notes: list[NormalizationNote] = []
    inv = NormalizedInvoice(segment_index=segment_index, page_start=page_start, page_end=page_end)
    inv.document_kind = raw.document_kind
    inv.amounts_tax_inclusive = raw.amounts_tax_inclusive

    for name, limit in _TEXT_LIMITS.items():
        setattr(inv, name, _clean(getattr(raw, name).value, limit))
    if inv.invoice_number:
        inv.invoice_number = inv.invoice_number.strip(".-_/#")

    for name in ("invoice_date", "payment_due_date"):
        rv = getattr(raw, name).value
        if not rv:
            continue
        parsed = parse_date(rv, day_first=settings.date_day_first)
        if name == "invoice_date":
            inv.invoice_date_raw = rv[:60]
        if parsed is None:
            notes.append(NormalizationNote(field=name, code="DATE_UNPARSEABLE", message=f"Could not parse date {rv!r}"))
            continue
        setattr(inv, name, parsed.value)
        if parsed.ambiguous:
            alt = parse_date(rv, day_first=not settings.date_day_first)
            inv.alternatives[name] = [parsed.value.isoformat(), alt.value.isoformat() if alt else None]
            notes.append(
                NormalizationNote(
                    field=name,
                    code="DATE_AMBIGUOUS",
                    message=f"{rv!r} is ambiguous (day/month); interpreted with day_first={settings.date_day_first}",
                )
            )

    _currency(raw.currency.value, notes, inv)

    hint = infer_decimal_separator(raw)
    currency_hints: set[str] = set()
    for name in AMOUNT_FIELDS:
        value, cur = _amount(getattr(raw, name).value, name, hint, notes)
        setattr(inv, name, value)
        if cur:
            currency_hints.add(cur)
    if inv.currency is None and len(currency_hints) == 1:
        inv.currency = next(iter(currency_hints))
        inv.currency_raw = inv.currency_raw or inv.currency
    if len(currency_hints) > 1 or (inv.currency and currency_hints and currency_hints != {inv.currency}):
        inv.alternatives["currency_conflict"] = sorted(currency_hints | ({inv.currency} if inv.currency else set()))
        notes.append(NormalizationNote(field="currency", code="CURRENCY_CONFLICT", message="Amounts carry conflicting currency labels"))

    for pos, item in enumerate(raw.line_items, start=1):
        li = NormalizedLineItem(position=pos, description=_clean(item.description, 2000))
        li.quantity, _ = _amount(item.quantity, f"line_items[{pos - 1}].quantity", hint, notes)
        li.unit_price, _ = _amount(item.unit_price, f"line_items[{pos - 1}].unit_price", hint, notes)
        li.discount_amount, _ = _amount(item.discount_amount, f"line_items[{pos - 1}].discount_amount", hint, notes)
        li.tax_amount, _ = _amount(item.tax_amount, f"line_items[{pos - 1}].tax_amount", hint, notes)
        li.line_total, _ = _amount(item.line_total, f"line_items[{pos - 1}].line_total", hint, notes)
        li.tax_rate = _rate(item.tax_rate)
        inv.line_items.append(li)

    inv.notes = notes
    return inv
