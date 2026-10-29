"""Deterministic date parsing for invoice dates.

No fuzzy parsing: only explicit, documented formats are accepted. Numeric dates
where both day and month are <= 12 and differ are ambiguous; the configured
``day_first`` policy decides and the result is flagged as ambiguous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass(frozen=True)
class ParsedDate:
    value: date
    raw: str
    ambiguous: bool = False
    rule: str = ""


_ISO_RE = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_NUMERIC_RE = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b")
_DMY_TEXT_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/.]+([A-Za-z]{3,9})\.?[\s\-/.,]+(\d{4})\b")
_MDY_TEXT_RE = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _year(y: int) -> int:
    if y < 100:
        return 2000 + y if y < 70 else 1900 + y
    return y


def parse_date(raw: str | None, *, day_first: bool = True) -> ParsedDate | None:
    if not raw:
        return None
    text = str(raw).strip()
    if m := _ISO_RE.search(text):
        if d := _mk(int(m.group(1)), int(m.group(2)), int(m.group(3))):
            return ParsedDate(d, text, rule="iso")
    if m := _DMY_TEXT_RE.search(text):
        month = MONTHS.get(m.group(2).lower())
        if month and (d := _mk(int(m.group(3)), month, int(m.group(1)))):
            return ParsedDate(d, text, rule="d-month-y")
    if m := _MDY_TEXT_RE.search(text):
        month = MONTHS.get(m.group(1).lower())
        if month and (d := _mk(int(m.group(3)), month, int(m.group(2)))):
            return ParsedDate(d, text, rule="month-d-y")
    if m := _NUMERIC_RE.search(text):
        a, b, y = int(m.group(1)), int(m.group(2)), _year(int(m.group(3)))
        if a > 12 and b <= 12:
            if d := _mk(y, b, a):
                return ParsedDate(d, text, rule="dmy-unambiguous")
        elif b > 12 and a <= 12:
            if d := _mk(y, a, b):
                return ParsedDate(d, text, rule="mdy-unambiguous")
        elif a <= 12 and b <= 12:
            ambiguous = a != b
            d = _mk(y, b, a) if day_first else _mk(y, a, b)
            if d:
                return ParsedDate(d, text, ambiguous=ambiguous, rule="dmy-policy" if day_first else "mdy-policy")
    return None
