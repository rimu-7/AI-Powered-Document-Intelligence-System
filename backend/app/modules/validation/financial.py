"""Deterministic financial arithmetic checks (Decimal only).

Arithmetic model:
  line:      line_total = quantity × unit_price − line_discount
             (accepted alternative: … + line_tax, for "gross" line totals)
  subtotal:  subtotal = Σ line_total                (tax-exclusive lines)
             total    = Σ line_total + shipping − discount (tax-inclusive lines)
  total:     total = subtotal − discount + shipping + tax
             (accepted alternative: discount already netted in subtotal)
Tolerances are absolute (currency units), never percentages.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.shared.money import quantize_money


@dataclass(frozen=True)
class Check:
    ok: bool
    expected: Decimal
    actual: Decimal
    difference: Decimal
    model: str


def within(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    return abs(a - b) <= tolerance


def check_line(
    quantity: Decimal,
    unit_price: Decimal,
    line_total: Decimal,
    currency: str | None,
    tolerance: Decimal,
    discount: Decimal | None = None,
    line_tax: Decimal | None = None,
) -> Check:
    net = quantize_money(quantity * unit_price - (discount or Decimal(0)), currency)
    if within(net, line_total, tolerance):
        return Check(True, net, line_total, line_total - net, "qty*unit-discount")
    if line_tax is not None:
        gross = quantize_money(net + line_tax, currency)
        if within(gross, line_total, tolerance):
            return Check(True, gross, line_total, line_total - gross, "qty*unit-discount+tax")
    return Check(False, net, line_total, line_total - net, "qty*unit-discount")


def line_sum_tolerance(tolerance: Decimal, line_count: int) -> Decimal:
    # Each printed line total may carry its own rounding of up to half a unit.
    return tolerance * max(1, line_count)


def expected_total_candidates(
    subtotal: Decimal,
    tax: Decimal | None,
    discount: Decimal | None,
    shipping: Decimal | None,
) -> list[tuple[str, Decimal]]:
    t = tax or Decimal(0)
    s = shipping or Decimal(0)
    candidates = [("subtotal-discount+shipping+tax", subtotal - (discount or Decimal(0)) + s + t)]
    if discount:
        candidates.append(("subtotal(net of discount)+shipping+tax", subtotal + s + t))
    return candidates
