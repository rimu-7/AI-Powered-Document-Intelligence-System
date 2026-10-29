"""Spreadsheet column → invoice field mapping (suggestions and validation)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.modules.parsing.spreadsheet_parser import header_field_score

MAPPABLE_FIELDS = (
    "invoice_number",
    "supplier_name",
    "customer_name",
    "invoice_date",
    "currency",
    "subtotal",
    "tax_amount",
    "total_amount",
    "purchase_order_number",
    "payment_due_date",
    "supplier_tax_id",
)
REQUIRED_MAPPING = ("invoice_number", "total_amount")


class MappingSuggestion(BaseModel):
    field: str
    header: str
    match_score: float = Field(description="String similarity of header to known synonyms (0..1), not a probability")


class MappingSuggestions(BaseModel):
    sheet_name: str | None
    headers: list[str]
    suggestions: list[MappingSuggestion]
    suggested_mapping: dict[str, str]
    missing_required: list[str]


def suggest_mapping(headers: list[str], sheet_name: str | None = None, min_score: float = 0.8) -> MappingSuggestions:
    scored: list[tuple[str, str, float]] = []
    for header in headers:
        field, score = header_field_score(header)
        if field and score >= min_score:
            scored.append((field, header, score))
    scored.sort(key=lambda t: -t[2])
    mapping: dict[str, str] = {}
    used_headers: set[str] = set()
    suggestions: list[MappingSuggestion] = []
    for field, header, score in scored:
        suggestions.append(MappingSuggestion(field=field, header=header, match_score=round(score, 3)))
        if field not in mapping and header not in used_headers:
            mapping[field] = header
            used_headers.add(header)
    return MappingSuggestions(
        sheet_name=sheet_name,
        headers=headers,
        suggestions=suggestions,
        suggested_mapping=mapping,
        missing_required=[f for f in REQUIRED_MAPPING if f not in mapping],
    )


def validate_mapping(mapping: dict[str, str], headers: set[str]) -> list[dict[str, Any]]:
    errors = []
    for field, header in mapping.items():
        if field not in MAPPABLE_FIELDS:
            errors.append({"field": field, "error": "unknown target field"})
        elif header not in headers:
            errors.append({"field": field, "header": header, "error": "header not present in spreadsheet"})
    for required in REQUIRED_MAPPING:
        if required not in mapping:
            errors.append({"field": required, "error": "required mapping missing"})
    return errors
