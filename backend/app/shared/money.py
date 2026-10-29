"""Money parsing and arithmetic. Decimal only; floats are rejected.

Amount parsing handles international formats:
  1,234.56   1.234,56   1 234,56   1'234.56   (1,234.56)   -1234.56   1234.56-
Ambiguous inputs such as ``1,234`` (thousands or decimal?) are resolved by a
documented rule and reported as ambiguous so callers can flag them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

# ISO 4217 minor units for currencies we expect to see. Unknown codes default
# to 2 decimals but are flagged by INVALID_CURRENCY validation.
CURRENCY_MINOR_UNITS: dict[str, int] = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "JPY": 0,
    "CNY": 2,
    "CHF": 2,
    "CAD": 2,
    "AUD": 2,
    "NZD": 2,
    "SEK": 2,
    "NOK": 2,
    "DKK": 2,
    "PLN": 2,
    "CZK": 2,
    "HUF": 2,
    "INR": 2,
    "BDT": 2,
    "PKR": 2,
    "LKR": 2,
    "SGD": 2,
    "HKD": 2,
    "KRW": 0,
    "TWD": 2,
    "THB": 2,
    "MYR": 2,
    "IDR": 2,
    "PHP": 2,
    "VND": 0,
    "AED": 2,
    "SAR": 2,
    "QAR": 2,
    "BHD": 3,
    "KWD": 3,
    "OMR": 3,
    "JOD": 3,
    "TND": 3,
    "ILS": 2,
    "TRY": 2,
    "ZAR": 2,
    "NGN": 2,
    "KES": 2,
    "EGP": 2,
    "MAD": 2,
    "BRL": 2,
    "MXN": 2,
    "ARS": 2,
    "CLP": 0,
    "COP": 2,
    "PEN": 2,
    "RUB": 2,
    "UAH": 2,
    "RON": 2,
    "BGN": 2,
    "ISK": 0,
    "CLF": 4,
}

ISO_CURRENCIES = frozenset(CURRENCY_MINOR_UNITS)

# Symbols that map to exactly one currency.
UNAMBIGUOUS_SYMBOLS: dict[str, str] = {
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "৳": "BDT",
    "₩": "KRW",
    "₫": "VND",
    "₪": "ILS",
    "₺": "TRY",
    "₦": "NGN",
    "₱": "PHP",
    "₴": "UAH",
    "₽": "RUB",
    "฿": "THB",
    "US$": "USD",
    "A$": "AUD",
    "C$": "CAD",
    "NZ$": "NZD",
    "S$": "SGD",
    "HK$": "HKD",
    "R$": "BRL",
    "CHF": "CHF",
    "Tk": "BDT",
}

# Symbols shared by several currencies: never resolved without more context.
AMBIGUOUS_SYMBOLS: dict[str, tuple[str, ...]] = {
    "$": ("USD", "CAD", "AUD", "NZD", "SGD", "HKD", "MXN", "ARS", "CLP", "COP"),
    "¥": ("JPY", "CNY"),
    "kr": ("SEK", "NOK", "DKK", "ISK"),
    "Rs": ("INR", "PKR", "LKR"),
    "R": ("ZAR", "BRL"),
}


def minor_units(currency: str | None) -> int:
    if currency is None:
        return 2
    return CURRENCY_MINOR_UNITS.get(currency.upper(), 2)


def quantum(currency: str | None) -> Decimal:
    return Decimal(1).scaleb(-minor_units(currency))


def quantize_money(value: Decimal, currency: str | None) -> Decimal:
    return value.quantize(quantum(currency), rounding=ROUND_HALF_EVEN)


def to_decimal(value: object) -> Decimal | None:
    """Convert a trusted machine value (str/int/Decimal) to Decimal. Rejects floats."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, bool):
        raise TypeError("bool is not a monetary value")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        raise TypeError("floats are not accepted for monetary values")
    if isinstance(value, str):
        parsed = parse_amount(value)
        return parsed.value if parsed else None
    raise TypeError(f"unsupported monetary type: {type(value).__name__}")


@dataclass(frozen=True)
class ParsedAmount:
    value: Decimal
    raw: str
    ambiguous: bool = False
    currency_hint: str | None = None
    note: str | None = None


_CURRENCY_TOKEN_RE = re.compile(r"(US\$|A\$|C\$|NZ\$|S\$|HK\$|R\$|[€£₹৳₩₫₪₺₦₱₴₽฿¥$]|\b[A-Z]{3}\b|\bTk\b|\bRs\.?|\bkr\b)")
_ALLOWED_CHARS_RE = re.compile(r"^[0-9.,'\s  ]+$")


def detect_currency_token(text: str) -> tuple[str | None, tuple[str, ...]]:
    """Return (iso_code, candidates). iso_code is set only when unambiguous."""
    for match in _CURRENCY_TOKEN_RE.finditer(text):
        token = match.group(1).rstrip(".")
        if token in UNAMBIGUOUS_SYMBOLS:
            return UNAMBIGUOUS_SYMBOLS[token], (UNAMBIGUOUS_SYMBOLS[token],)
        if token.upper() in ISO_CURRENCIES and token.isupper():
            return token.upper(), (token.upper(),)
        if token in AMBIGUOUS_SYMBOLS:
            return None, AMBIGUOUS_SYMBOLS[token]
    return None, ()


def parse_amount(raw: str, *, decimal_hint: str | None = None) -> ParsedAmount | None:
    """Parse a human-formatted amount. Returns None when no amount is present.

    ``decimal_hint`` (``"."`` or ``","``) resolves ``1,234``-style ambiguity
    when the document's convention is known.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    currency_hint, _ = detect_currency_token(text)
    negative = False
    s = text
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    s = _CURRENCY_TOKEN_RE.sub("", s).strip()
    if s.startswith(("-", "−")):
        negative, s = True, s[1:].strip()
    elif s.endswith("-"):
        negative, s = True, s[:-1].strip()
    elif s.startswith("+"):
        s = s[1:].strip()
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    if not s or not _ALLOWED_CHARS_RE.match(s) or not any(c.isdigit() for c in s):
        return None
    s = re.sub(r"[\s  ']", "", s)

    ambiguous = False
    note = None
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        decimal_sep = "." if last_dot > last_comma else ","
        thousands = "," if decimal_sep == "." else "."
        integer_part, _, frac = s.rpartition(decimal_sep)
        if not _valid_grouping(integer_part, thousands):
            return None
        s = integer_part.replace(thousands, "") + "." + frac
    elif last_comma >= 0 or last_dot >= 0:
        sep = "," if last_comma >= 0 else "."
        parts = s.split(sep)
        if len(parts) > 2:
            # Multiple identical separators: must be thousands grouping.
            if not _valid_grouping(s, sep):
                return None
            s = s.replace(sep, "")
        else:
            integer_part, frac = parts
            if len(frac) == 3 and integer_part and len(integer_part) <= 3 and integer_part != "0":
                # "1,234" / "1.234": thousands or decimal? Resolve via hint.
                ambiguous = decimal_hint is None
                if decimal_hint == sep:
                    s = integer_part + "." + frac
                else:
                    s = integer_part + frac
                    note = f"'{sep}' interpreted as thousands separator"
            else:
                s = integer_part + "." + frac
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    if negative:
        value = -value
    return ParsedAmount(value=value, raw=text, ambiguous=ambiguous, currency_hint=currency_hint, note=note)


def _valid_grouping(integer_part: str, sep: str) -> bool:
    if sep not in integer_part:
        return integer_part.isdigit() or integer_part == ""
    groups = integer_part.split(sep)
    if not groups[0].isdigit() or len(groups[0]) > 3:
        return False
    # Allow Indian grouping (12,34,567.00): middle groups of 2, last of 3.
    tail = groups[1:]
    if all(len(g) == 3 and g.isdigit() for g in tail):
        return True
    return len(tail) >= 1 and len(tail[-1]) == 3 and all(len(g) == 2 and g.isdigit() for g in tail[:-1]) and tail[-1].isdigit()


def money_str(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")
