"""Text normalization helpers used for matching, grounding, and filenames."""

from __future__ import annotations

import re
import unicodedata

_LEGAL_SUFFIXES = (
    "limited",
    "ltd",
    "llc",
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "gmbh",
    "ag",
    "sa",
    "sarl",
    "bv",
    "nv",
    "plc",
    "pvt",
    "private",
    "pty",
    "srl",
    "spa",
    "oy",
    "ab",
    "as",
    "kg",
    "llp",
    "lp",
)
_SUFFIX_RE = re.compile(r"\b(" + "|".join(_LEGAL_SUFFIXES) + r")\b\.?", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")
_WS_RE = re.compile(r"\s+")


def fold(text: str) -> str:
    """Unicode NFKD + strip accents + casefold."""
    norm = unicodedata.normalize("NFKD", text)
    return "".join(c for c in norm if not unicodedata.combining(c)).casefold()


def normalize_whitespace(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def normalize_supplier(name: str | None) -> str | None:
    """Conservative supplier identity key: case/accents/punctuation/legal suffix."""
    if not name:
        return None
    folded = fold(name).replace("&", " and ")
    folded = _SUFFIX_RE.sub(" ", folded)
    key = normalize_whitespace(_NON_ALNUM_RE.sub(" ", folded))
    # Join runs of single characters so "A.B.C." and "ABC" share a key.
    key = re.sub(r"\b(\w)\s(?=\w\b)", r"\1", key)
    return key or None


def normalize_invoice_number(number: str | None) -> str | None:
    """Uppercase and strip separators; keep leading zeros (they can be significant)."""
    if not number:
        return None
    key = re.sub(r"[\s\-_/.#:]", "", fold(number)).upper()
    key = re.sub(r"^(?:INVOICE|INV|NO|NUMBER)+(?=[0-9])", "", key)
    return key or None


def normalize_for_grounding(text: str) -> str:
    """Normalize text so evidence snippets can be located in the source."""
    return _WS_RE.sub(" ", _NON_ALNUM_RE.sub(" ", fold(text))).strip()


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\- ()]+")


def safe_display_filename(name: str | None, default: str = "upload") -> str:
    """Display-only filename: strips paths and control/special characters."""
    if not name:
        return default
    base = name.replace("\\", "/").split("/")[-1]
    base = unicodedata.normalize("NFKC", base)
    base = "".join(c for c in base if unicodedata.category(c)[0] != "C")
    base = _SAFE_FILENAME_RE.sub("_", base).strip(" .")
    return (base or default)[:200]


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"
