"""Cross-check the LLM extraction against the deterministic rule-based extraction.

Two independent extractors read the same segment. The LLM result is the
primary; the rules result is used only where it is *verifiably* better:

* Amounts block (subtotal, discount, shipping, tax, total): if the LLM's
  amounts do not satisfy ``subtotal − discount + shipping + tax = total`` but
  the rules' amounts do, the rules' amounts are used.
* Line items: if the LLM's line items do not reconcile (each ``qty × price =
  line total`` and Σ lines = subtotal) but the rules' line items do, they are
  used.
* Header fields: a field the LLM left empty, or whose value could not be found
  in the source text, is taken from the rules when the rules' value *is*
  grounded in the source.

Every substitution is recorded as a note (``CROSS_CHECK_APPLIED``) listing
the fields; remaining disagreements are kept as alternatives
(``EXTRACTOR_DISAGREEMENT``). Nothing is invented: both candidates come from
the document and are grounded before this step.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.config import get_settings
from app.modules.extraction.schemas import NormalizationNote, NormalizedInvoice
from app.modules.validation.financial import check_line, expected_total_candidates, line_sum_tolerance, within
from app.shared.text import normalize_for_grounding, normalize_invoice_number

AMOUNT_BLOCK = ("subtotal", "discount_amount", "shipping_amount", "tax_amount", "total_amount", "amounts_tax_inclusive")
HEADER_FIELDS = (
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
)


def totals_consistent(inv: NormalizedInvoice, tolerance: Decimal) -> bool | None:
    if inv.subtotal is None or inv.total_amount is None:
        return None
    if inv.amounts_tax_inclusive and within(inv.subtotal, inv.total_amount, tolerance):
        return True
    for _, expected in expected_total_candidates(inv.subtotal, inv.tax_amount, inv.discount_amount, inv.shipping_amount):
        if within(expected, inv.total_amount, tolerance * 2):
            return True
    return False


def lines_consistent(inv: NormalizedInvoice, tolerance: Decimal) -> bool | None:
    lines = [li for li in inv.line_items if li.line_total is not None]
    if not lines:
        return None
    for li in lines:
        if li.quantity is not None and li.unit_price is not None and li.line_total is not None:
            if not check_line(li.quantity, li.unit_price, li.line_total, inv.currency, tolerance, li.discount_amount, li.tax_amount).ok:
                return False
    target = inv.total_amount if inv.amounts_tax_inclusive else inv.subtotal
    if target is None:
        return None
    total = sum((li.line_total for li in lines if li.line_total is not None), Decimal(0))
    discount = inv.discount_amount or Decimal(0)
    return within(total, target, line_sum_tolerance(tolerance, len(lines))) or within(
        total - discount, target, line_sum_tolerance(tolerance, len(lines))
    )


def _supported(inv: NormalizedInvoice, field: str) -> bool:
    ev = inv.evidence.get(field)
    return ev is not None and ev.support == "SUPPORTED"


def _same_text(a: object, b: object) -> bool:
    """Equal apart from case, punctuation and spacing ("Blvd, New York" = "Blvd New York")."""
    return a == b or normalize_for_grounding(str(a)) == normalize_for_grounding(str(b))


def cross_check(primary: NormalizedInvoice, secondary: NormalizedInvoice) -> NormalizedInvoice:
    tolerance = get_settings().validation_amount_tolerance
    merged = primary.model_copy(deep=True)
    taken: list[str] = []

    if totals_consistent(primary, tolerance) is False and totals_consistent(secondary, tolerance) is True:
        for name in AMOUNT_BLOCK:
            setattr(merged, name, getattr(secondary, name))
            if name in secondary.evidence:
                merged.evidence[name] = secondary.evidence[name]
            else:
                merged.evidence.pop(name, None)
        taken.append("amounts")

    if lines_consistent(merged, tolerance) is not True and lines_consistent(secondary, tolerance) is True and secondary.line_items:
        merged.line_items = [li.model_copy(deep=True) for li in secondary.line_items]
        taken.append("line_items")

    for name in HEADER_FIELDS:
        mine, theirs = getattr(merged, name), getattr(secondary, name)
        if theirs is None:
            continue
        if (mine is None or not _supported(merged, name)) and _supported(secondary, name):
            setattr(merged, name, theirs)
            merged.evidence[name] = secondary.evidence[name]
            if name == "currency":
                merged.currency_raw = secondary.currency_raw
                merged.currency_source = secondary.currency_source
            if name == "invoice_date":
                merged.invoice_date_raw = secondary.invoice_date_raw
            taken.append(name)
        elif mine is not None and _supported(secondary, name) and not _same_text(mine, theirs):
            merged.alternatives.setdefault(name, [str(mine), str(theirs)])
            merged.notes.append(
                NormalizationNote(
                    field=name, code="EXTRACTOR_DISAGREEMENT", message=f"LLM read {mine!r}, rules read {theirs!r}; LLM value kept"
                )
            )

    if taken:
        merged.notes.append(
            NormalizationNote(
                field="__extraction__",
                code="CROSS_CHECK_APPLIED",
                message="Taken from the rule-based extractor after verification: " + ", ".join(taken),
            )
        )
    return merged


def pair_invoices(
    primary: list[NormalizedInvoice], secondary: list[NormalizedInvoice]
) -> list[tuple[NormalizedInvoice, NormalizedInvoice | None]]:
    """Pair by normalized invoice number; a lone invoice on each side pairs directly."""
    if len(primary) == 1 and len(secondary) == 1:
        return [(primary[0], secondary[0])]
    by_number = {normalize_invoice_number(s.invoice_number): s for s in secondary if s.invoice_number}
    return [(p, by_number.get(normalize_invoice_number(p.invoice_number)) if p.invoice_number else None) for p in primary]
