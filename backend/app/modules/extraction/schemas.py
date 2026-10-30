"""Extraction schemas.

``RawExtraction`` is the strict structured-output contract for providers. All
monetary and date values are *strings exactly as printed*; normalization to
Decimal/date happens deterministically in ``normalization.py``.
"""

from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import CurrencyCode, CurrencySource

INVOICE_FIELDS = (
    "invoice_number",
    "invoice_date",
    "payment_due_date",
    "supplier_name",
    "supplier_tax_id",
    "supplier_address",
    "customer_name",
    "customer_address",
    "purchase_order_number",
    "payment_reference",
    "currency",
    "subtotal",
    "discount_amount",
    "shipping_amount",
    "tax_amount",
    "total_amount",
)
AMOUNT_FIELDS = ("subtotal", "discount_amount", "shipping_amount", "tax_amount", "total_amount")
DATE_FIELDS = ("invoice_date", "payment_due_date")
REQUIRED_FIELDS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "currency",
    "subtotal",
    "tax_amount",
    "total_amount",
)


class RawField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None = Field(description="Value exactly as printed, or null if absent")
    page: int | None = Field(description="Page number from the <<<PAGE n>>> marker, or null")
    evidence: str | None = Field(description="Short verbatim snippet containing the value, or null")


class RawLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None
    quantity: str | None
    unit_price: str | None
    discount_amount: str | None
    tax_rate: str | None
    tax_amount: str | None
    line_total: str | None
    page: int | None
    evidence: str | None


class RawInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_kind: Literal["INVOICE", "CREDIT_NOTE", "RECEIPT", "OTHER"] | None
    invoice_number: RawField
    invoice_date: RawField
    payment_due_date: RawField
    supplier_name: RawField
    supplier_tax_id: RawField
    supplier_address: RawField
    customer_name: RawField
    customer_address: RawField
    purchase_order_number: RawField
    payment_reference: RawField
    currency: RawField
    subtotal: RawField
    discount_amount: RawField
    shipping_amount: RawField
    tax_amount: RawField
    total_amount: RawField
    amounts_tax_inclusive: bool | None
    line_items: list[RawLineItem]


class RawExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoices: list[RawInvoice]


class RawClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["INVOICE", "RECEIPT", "CREDIT_NOTE", "FINANCIAL_STATEMENT", "UNKNOWN"]


def empty_field() -> RawField:
    return RawField(value=None, page=None, evidence=None)


def empty_invoice() -> RawInvoice:
    return RawInvoice(
        document_kind=None,
        amounts_tax_inclusive=None,
        line_items=[],
        **{name: empty_field() for name in INVOICE_FIELDS},
    )


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Inline $refs and express nullables as type unions (strict-mode friendly)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return resolve(copy.deepcopy(defs[name]))
            if "anyOf" in node:
                options = [resolve(o) for o in node["anyOf"]]
                types = [o.get("type") for o in options]
                if len(options) == 2 and "null" in types:
                    other = next(o for o in options if o.get("type") != "null")
                    merged = dict(other)
                    t = other.get("type")
                    if isinstance(t, str):
                        merged["type"] = [t, "null"]
                    if "enum" in merged:
                        merged["enum"] = [*merged["enum"], None]
                    for key in ("description", "title"):
                        if key in node:
                            merged[key] = node[key]
                    merged.pop("title", None)
                    return merged
                return {"anyOf": options}
            out = {k: resolve(v) for k, v in node.items() if k not in ("title", "default")}
            if out.get("type") == "object" and "properties" in out:
                out["required"] = list(out["properties"].keys())
                out["additionalProperties"] = False
            return out
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)  # type: ignore[no-any-return]


# --- Normalized (internal) ------------------------------------------------------


class Evidence(BaseModel):
    document_id: str | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    row_number: int | None = None
    supporting_text: str | None = None
    bounding_box: list[float] | None = None
    extraction_method: str
    support: Literal["SUPPORTED", "WEAK", "UNSUPPORTED", "DERIVED"] = "WEAK"
    reason: str | None = None  # why a DERIVED value was chosen


class NormalizedLineItem(BaseModel):
    position: int
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    discount_amount: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    line_total: Decimal | None = None
    evidence: Evidence | None = None


class NormalizationNote(BaseModel):
    field: str
    code: str
    message: str


class NormalizedInvoice(BaseModel):
    segment_index: int
    page_start: int | None = None
    page_end: int | None = None
    document_kind: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    invoice_date_raw: str | None = None
    payment_due_date: date | None = None
    supplier_name: str | None = None
    supplier_tax_id: str | None = None
    supplier_address: str | None = None
    customer_name: str | None = None
    customer_address: str | None = None
    purchase_order_number: str | None = None
    payment_reference: str | None = None
    currency: CurrencyCode | None = None
    currency_raw: str | None = None
    currency_source: CurrencySource | None = None
    subtotal: Decimal | None = None
    discount_amount: Decimal | None = None
    shipping_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    amounts_tax_inclusive: bool | None = None
    line_items: list[NormalizedLineItem] = Field(default_factory=list)
    evidence: dict[str, Evidence] = Field(default_factory=dict)
    alternatives: dict[str, list[Any]] = Field(default_factory=dict)
    notes: list[NormalizationNote] = Field(default_factory=list)
    confidence: Decimal | None = None
    ocr_confidence: float | None = None

    def field_support(self) -> dict[str, str]:
        support: dict[str, str] = {}
        for name in INVOICE_FIELDS:
            if getattr(self, name) is None:
                support[name] = "MISSING"
            else:
                ev = self.evidence.get(name)
                support[name] = ev.support if ev else "WEAK"
        return support
