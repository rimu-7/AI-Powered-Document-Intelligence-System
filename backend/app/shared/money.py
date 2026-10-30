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

from app.shared.enums import CurrencyCode

# ISO 4217 minor units for every supported currency (one entry per CurrencyCode).
CURRENCY_MINOR_UNITS: dict[CurrencyCode, int] = {
    CurrencyCode.USD: 2,
    CurrencyCode.EUR: 2,
    CurrencyCode.GBP: 2,
    CurrencyCode.JPY: 0,
    CurrencyCode.CNY: 2,
    CurrencyCode.CHF: 2,
    CurrencyCode.CAD: 2,
    CurrencyCode.AUD: 2,
    CurrencyCode.NZD: 2,
    CurrencyCode.SEK: 2,
    CurrencyCode.NOK: 2,
    CurrencyCode.DKK: 2,
    CurrencyCode.PLN: 2,
    CurrencyCode.CZK: 2,
    CurrencyCode.HUF: 2,
    CurrencyCode.INR: 2,
    CurrencyCode.BDT: 2,
    CurrencyCode.PKR: 2,
    CurrencyCode.LKR: 2,
    CurrencyCode.SGD: 2,
    CurrencyCode.HKD: 2,
    CurrencyCode.KRW: 0,
    CurrencyCode.TWD: 2,
    CurrencyCode.THB: 2,
    CurrencyCode.MYR: 2,
    CurrencyCode.IDR: 2,
    CurrencyCode.PHP: 2,
    CurrencyCode.VND: 0,
    CurrencyCode.AED: 2,
    CurrencyCode.SAR: 2,
    CurrencyCode.QAR: 2,
    CurrencyCode.BHD: 3,
    CurrencyCode.KWD: 3,
    CurrencyCode.OMR: 3,
    CurrencyCode.JOD: 3,
    CurrencyCode.TND: 3,
    CurrencyCode.ILS: 2,
    CurrencyCode.TRY: 2,
    CurrencyCode.ZAR: 2,
    CurrencyCode.NGN: 2,
    CurrencyCode.KES: 2,
    CurrencyCode.EGP: 2,
    CurrencyCode.MAD: 2,
    CurrencyCode.BRL: 2,
    CurrencyCode.MXN: 2,
    CurrencyCode.ARS: 2,
    CurrencyCode.CLP: 0,
    CurrencyCode.COP: 2,
    CurrencyCode.PEN: 2,
    CurrencyCode.RUB: 2,
    CurrencyCode.UAH: 2,
    CurrencyCode.RON: 2,
    CurrencyCode.BGN: 2,
    CurrencyCode.ISK: 0,
    CurrencyCode.CLF: 4,
}

ISO_CURRENCIES: frozenset[CurrencyCode] = frozenset(CurrencyCode)

# Symbols that map to exactly one currency.
UNAMBIGUOUS_SYMBOLS: dict[str, CurrencyCode] = {
    "€": CurrencyCode.EUR,
    "£": CurrencyCode.GBP,
    "₹": CurrencyCode.INR,
    "৳": CurrencyCode.BDT,
    "₩": CurrencyCode.KRW,
    "₫": CurrencyCode.VND,
    "₪": CurrencyCode.ILS,
    "₺": CurrencyCode.TRY,
    "₦": CurrencyCode.NGN,
    "₱": CurrencyCode.PHP,
    "₴": CurrencyCode.UAH,
    "₽": CurrencyCode.RUB,
    "฿": CurrencyCode.THB,
    "US$": CurrencyCode.USD,
    "A$": CurrencyCode.AUD,
    "C$": CurrencyCode.CAD,
    "NZ$": CurrencyCode.NZD,
    "S$": CurrencyCode.SGD,
    "HK$": CurrencyCode.HKD,
    "R$": CurrencyCode.BRL,
    "CHF": CurrencyCode.CHF,
    "Tk": CurrencyCode.BDT,
}

# Symbols shared by several currencies: never resolved without more context.
AMBIGUOUS_SYMBOLS: dict[str, tuple[CurrencyCode, ...]] = {
    "$": (
        CurrencyCode.USD,
        CurrencyCode.CAD,
        CurrencyCode.AUD,
        CurrencyCode.NZD,
        CurrencyCode.SGD,
        CurrencyCode.HKD,
        CurrencyCode.MXN,
        CurrencyCode.ARS,
        CurrencyCode.CLP,
        CurrencyCode.COP,
    ),
    "¥": (CurrencyCode.JPY, CurrencyCode.CNY),
    "kr": (CurrencyCode.SEK, CurrencyCode.NOK, CurrencyCode.DKK, CurrencyCode.ISK),
    "Rs": (CurrencyCode.INR, CurrencyCode.PKR, CurrencyCode.LKR),
    "R": (CurrencyCode.ZAR, CurrencyCode.BRL),
}


def to_currency_code(value: object) -> CurrencyCode | None:
    """The CurrencyCode for an ISO code in any letter case, else None."""
    if isinstance(value, CurrencyCode):
        return value
    if not isinstance(value, str):
        return None
    try:
        return CurrencyCode(value.strip().upper())
    except ValueError:
        return None


def minor_units(currency: str | None) -> int:
    code = to_currency_code(currency)
    return CURRENCY_MINOR_UNITS[code] if code else 2


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
    currency_hint: CurrencyCode | None = None
    note: str | None = None


_CURRENCY_TOKEN_RE = re.compile(r"(US\$|A\$|C\$|NZ\$|S\$|HK\$|R\$|[€£₹৳₩₫₪₺₦₱₴₽฿¥$]|\b[A-Z]{3}\b|\bTk\b|\bRs\.?|\bkr\b)")
_ALLOWED_CHARS_RE = re.compile(r"^[0-9.,'\s  ]+$")


def detect_currency_token(text: str) -> tuple[CurrencyCode | None, tuple[CurrencyCode, ...]]:
    """Return (code, candidates). code is set only when unambiguous."""
    for match in _CURRENCY_TOKEN_RE.finditer(text):
        token = match.group(1).rstrip(".")
        if token in UNAMBIGUOUS_SYMBOLS:
            return UNAMBIGUOUS_SYMBOLS[token], (UNAMBIGUOUS_SYMBOLS[token],)
        code = to_currency_code(token) if token.isupper() else None
        if code is not None:
            return code, (code,)
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
