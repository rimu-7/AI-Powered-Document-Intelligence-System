"""Record matching and field comparison shared by PDF↔PDF and PDF↔spreadsheet.

Matching rules:
1. Candidates share a normalized invoice number.
2. Supplier must be compatible: equal normalized names, or fuzzy similarity
   above the threshold (flagged as fuzzy), or unknown on one side.
   Same invoice number from a different supplier is NOT a match.
3. Several candidates are disambiguated by exact date and total; if that does
   not leave exactly one, the result is AMBIGUOUS.
4. Optional fuzzy invoice-number matching (OCR errors) only ever yields
   AMBIGUOUS, never an authoritative match.
5. Amounts in different currencies are NOT_COMPARABLE.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz

from app.shared.enums import FindingStatus
from app.shared.money import money_str


@dataclass
class ComparableRecord:
    record_id: str
    source: str  # "invoice" | "row"
    document_id: str
    invoice_number: str | None
    normalized_number: str | None
    supplier: str | None
    normalized_supplier: str | None
    customer: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    line_items: list[dict[str, Any]] = field(default_factory=list)
    reference: dict[str, Any] = field(default_factory=dict)
    field_refs: dict[str, Any] = field(default_factory=dict)
    parse_notes: list[str] = field(default_factory=list)

    def label(self) -> str:
        return f"{self.invoice_number or '?'} / {self.supplier or '?'}"


@dataclass
class MatchOptions:
    amount_tolerance: Decimal = Decimal("0.01")
    supplier_fuzzy_threshold: int = 90
    fuzzy_invoice_numbers: bool = True
    invoice_number_fuzzy_threshold: int = 85
    default_currency: str | None = None


@dataclass
class FindingDraft:
    record_key: str
    field_name: str
    status: FindingStatus
    left: Any = None
    right: Any = None
    difference: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchResult:
    findings: list[FindingDraft]
    summary: dict[str, Any]


def _values(rec: ComparableRecord) -> tuple[object, ...]:
    return (rec.normalized_number, rec.normalized_supplier, rec.invoice_date, rec.currency, rec.subtotal, rec.tax_amount, rec.total_amount)


def _supplier_compat(a: ComparableRecord, b: ComparableRecord, threshold: int) -> tuple[bool, str]:
    if not a.normalized_supplier or not b.normalized_supplier:
        return True, "unknown"
    if a.normalized_supplier == b.normalized_supplier:
        return True, "exact"
    score = fuzz.token_sort_ratio(a.normalized_supplier, b.normalized_supplier)
    if score >= threshold:
        return True, f"fuzzy:{score:.0f}"
    return False, f"different:{score:.0f}"


def _val(v: Any) -> Any:
    if isinstance(v, Decimal):
        return money_str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def _evidence(left: ComparableRecord | None, right: ComparableRecord | None, field_name: str | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {}
    if left is not None:
        ev["left"] = {
            **left.reference,
            **({"field": left.field_refs.get(field_name)} if field_name and left.field_refs.get(field_name) else {}),
        }
    if right is not None:
        ev["right"] = {
            **right.reference,
            **({"field": right.field_refs.get(field_name)} if field_name and right.field_refs.get(field_name) else {}),
        }
    return ev


def compare_pair(
    left: ComparableRecord,
    right: ComparableRecord,
    key: str,
    opts: MatchOptions,
    match_quality: str,
    compare_customer: bool,
    compare_lines: bool,
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []

    def add(name: str, status: FindingStatus, lv: Any, rv: Any, diff: Any = None) -> None:
        findings.append(FindingDraft(key, name, status, _val(lv), _val(rv), diff, _evidence(left, right, name)))

    # Identity fields
    add(
        "invoice_number",
        FindingStatus.MATCH if left.normalized_number == right.normalized_number else FindingStatus.AMBIGUOUS,
        left.invoice_number,
        right.invoice_number,
    )
    ok, quality = _supplier_compat(left, right, opts.supplier_fuzzy_threshold)
    if quality == "unknown":
        add("supplier_name", FindingStatus.NOT_COMPARABLE, left.supplier, right.supplier)
    elif quality == "exact":
        add("supplier_name", FindingStatus.MATCH, left.supplier, right.supplier)
    else:
        add(
            "supplier_name",
            FindingStatus.AMBIGUOUS if ok else FindingStatus.MISMATCH,
            left.supplier,
            right.supplier,
            {"similarity": quality},
        )
    if compare_customer:
        if left.customer and right.customer:
            same = fuzz.token_sort_ratio(left.customer.casefold(), right.customer.casefold()) >= 95
            add("customer_name", FindingStatus.MATCH if same else FindingStatus.MISMATCH, left.customer, right.customer)
        else:
            add("customer_name", FindingStatus.NOT_COMPARABLE, left.customer, right.customer)

    if left.invoice_date and right.invoice_date:
        days = (right.invoice_date - left.invoice_date).days
        add(
            "invoice_date",
            FindingStatus.MATCH if days == 0 else FindingStatus.MISMATCH,
            left.invoice_date,
            right.invoice_date,
            {"days": days} if days else None,
        )
    else:
        add("invoice_date", FindingStatus.NOT_COMPARABLE, left.invoice_date, right.invoice_date)

    lc = left.currency or opts.default_currency
    rc = right.currency or opts.default_currency
    currency_ok = lc is not None and rc is not None and lc == rc
    if lc and rc:
        add(
            "currency",
            FindingStatus.MATCH if lc == rc else FindingStatus.MISMATCH,
            left.currency or f"{lc} (default)",
            right.currency or f"{rc} (default)",
        )
    else:
        add("currency", FindingStatus.NOT_COMPARABLE, left.currency, right.currency)

    for name in ("subtotal", "tax_amount", "total_amount"):
        lv, rv = getattr(left, name), getattr(right, name)
        if lv is None or rv is None:
            if lv is not None or rv is not None:
                add(name, FindingStatus.NOT_COMPARABLE, lv, rv, {"reason": "missing on one side"})
            continue
        if not currency_ok:
            add(name, FindingStatus.NOT_COMPARABLE, lv, rv, {"reason": "currency missing or different; no conversion policy"})
            continue
        diff = rv - lv
        status = FindingStatus.MATCH if abs(diff) <= opts.amount_tolerance else FindingStatus.MISMATCH
        add(
            name,
            status,
            lv,
            rv,
            {"difference": money_str(diff), "tolerance": money_str(opts.amount_tolerance)} if status == FindingStatus.MISMATCH else None,
        )

    if compare_lines and (left.line_items or right.line_items):
        findings.extend(_compare_lines(left, right, key, opts, currency_ok))

    statuses = [f.status for f in findings]
    if FindingStatus.MISMATCH in statuses:
        record_status = FindingStatus.MISMATCH
    elif match_quality != "exact" or FindingStatus.AMBIGUOUS in statuses:
        record_status = FindingStatus.AMBIGUOUS
    else:
        record_status = FindingStatus.MATCH
    findings.insert(
        0,
        FindingDraft(
            key,
            "__record__",
            record_status,
            left.label(),
            right.label(),
            {"match_quality": match_quality},
            _evidence(left, right),
        ),
    )
    return findings


def _compare_lines(left: ComparableRecord, right: ComparableRecord, key: str, opts: MatchOptions, currency_ok: bool) -> list[FindingDraft]:
    out: list[FindingDraft] = []
    remaining = list(right.line_items)
    for li in left.line_items:
        best_idx, best_score = None, 0.0
        for idx, ri in enumerate(remaining):
            score = fuzz.token_sort_ratio((li.get("description") or "").casefold(), (ri.get("description") or "").casefold())
            if score > best_score:
                best_idx, best_score = idx, score
        name = f"line_items[{li.get('position')}]"
        if best_idx is None or best_score < 80:
            out.append(
                FindingDraft(key, name, FindingStatus.MISSING_RIGHT, li.get("description"), None, None, {"left": li.get("evidence")})
            )
            continue
        ri = remaining.pop(best_idx)
        lt, rt = li.get("line_total"), ri.get("line_total")
        if lt is not None and rt is not None and currency_ok:
            diff = Decimal(rt) - Decimal(lt)
            status = FindingStatus.MATCH if abs(diff) <= opts.amount_tolerance else FindingStatus.MISMATCH
            out.append(
                FindingDraft(
                    key,
                    name,
                    status,
                    {"description": li.get("description"), "line_total": lt},
                    {"description": ri.get("description"), "line_total": rt},
                    {"difference": money_str(diff)} if status == FindingStatus.MISMATCH else None,
                    {"left": li.get("evidence"), "right": ri.get("evidence")},
                )
            )
        else:
            out.append(
                FindingDraft(
                    key,
                    name,
                    FindingStatus.NOT_COMPARABLE,
                    li.get("description"),
                    ri.get("description"),
                    None,
                    {"left": li.get("evidence"), "right": ri.get("evidence")},
                )
            )
    for ri in remaining:
        out.append(
            FindingDraft(
                key,
                f"line_items[r{ri.get('position')}]",
                FindingStatus.MISSING_LEFT,
                None,
                ri.get("description"),
                None,
                {"right": ri.get("evidence")},
            )
        )
    return out


def match_records(
    left: list[ComparableRecord],
    right: list[ComparableRecord],
    opts: MatchOptions,
    *,
    compare_customer: bool = False,
    compare_lines: bool = False,
    detect_right_duplicates: bool = True,
) -> MatchResult:
    findings: list[FindingDraft] = []
    counts: defaultdict[str, int] = defaultdict(int)

    by_number: dict[str, list[ComparableRecord]] = defaultdict(list)
    for rec in right:
        if rec.normalized_number:
            by_number[rec.normalized_number].append(rec)

    # Duplicates inside the right-hand set (e.g. register rows across sheets).
    duplicate_ids: set[str] = set()
    if detect_right_duplicates:
        for recs in by_number.values():
            groups: dict[str, list[ComparableRecord]] = defaultdict(list)
            for rec in recs:
                groups[rec.normalized_supplier or ""].append(rec)
            for group in groups.values():
                if len(group) > 1:
                    for extra in group[1:]:
                        duplicate_ids.add(extra.record_id)
                        counts["duplicate_count"] += 1
                        findings.append(
                            FindingDraft(
                                f"duplicate | {extra.invoice_number} | {extra.supplier or '?'}",
                                "__record__",
                                FindingStatus.DUPLICATE,
                                None,
                                extra.label(),
                                {"duplicate_of": group[0].reference},
                                {"right": extra.reference, "first_occurrence": group[0].reference},
                            )
                        )

    used: set[str] = set()
    for lrec in left:
        key = f"{lrec.invoice_number or lrec.record_id} | {lrec.supplier or '?'}"
        # Duplicate rows stay candidates: several rows for one invoice is exactly
        # the "multiple possible matches" case and must surface as AMBIGUOUS.
        candidates = [r for r in by_number.get(lrec.normalized_number or "", []) if r.record_id not in used]
        compatible = []
        for cand in candidates:
            ok, quality = _supplier_compat(lrec, cand, opts.supplier_fuzzy_threshold)
            if ok:
                compatible.append((cand, quality))
        quality_for_pair = "exact"
        chosen: ComparableRecord | None = None
        if len(compatible) == 1:
            chosen, q = compatible[0]
            quality_for_pair = "exact" if q in ("exact", "unknown") else q
        elif len(compatible) > 1:
            narrowed = [(c, q) for c, q in compatible if (c.invoice_date == lrec.invoice_date) and (c.total_amount == lrec.total_amount)]
            if len(narrowed) > 1 and len({_values(c) for c, _ in narrowed}) == 1:
                # Identical rows are duplicates, not alternatives: match the first,
                # the copies are already reported as DUPLICATE.
                narrowed = narrowed[:1]
            if len(narrowed) == 1:
                chosen, q = narrowed[0]
                quality_for_pair = "exact" if q in ("exact", "unknown") else q
            else:
                counts["ambiguous_count"] += 1
                findings.append(
                    FindingDraft(
                        key,
                        "__record__",
                        FindingStatus.AMBIGUOUS,
                        lrec.label(),
                        [c.label() for c, _ in compatible],
                        {"reason": "multiple candidate matches", "candidates": [c.reference for c, _ in compatible]},
                        {"left": lrec.reference, "right_candidates": [c.reference for c, _ in compatible]},
                    )
                )
                continue
        elif candidates:
            # Same number, incompatible supplier: explicitly not a match.
            findings.append(
                FindingDraft(
                    key,
                    "supplier_name",
                    FindingStatus.NOT_COMPARABLE,
                    lrec.supplier,
                    [c.supplier for c in candidates],
                    {"reason": "same invoice number belongs to a different supplier"},
                    {"left": lrec.reference, "right_candidates": [c.reference for c in candidates]},
                )
            )
        if chosen is None and opts.fuzzy_invoice_numbers and lrec.normalized_number:
            fuzzy = [
                r
                for r in right
                if r.record_id not in used
                and r.normalized_number
                and r.normalized_number != lrec.normalized_number
                and fuzz.ratio(r.normalized_number, lrec.normalized_number) >= opts.invoice_number_fuzzy_threshold
                and _supplier_compat(lrec, r, opts.supplier_fuzzy_threshold)[0]
                # Sequential numbers differ by one character too; require the
                # same total so only plausible OCR misreads become candidates.
                and r.total_amount is not None
                and r.total_amount == lrec.total_amount
            ]
            if fuzzy:
                counts["ambiguous_count"] += 1
                findings.append(
                    FindingDraft(
                        key,
                        "__record__",
                        FindingStatus.AMBIGUOUS,
                        lrec.label(),
                        [r.label() for r in fuzzy],
                        {"reason": "fuzzy invoice-number match requires confirmation"},
                        {"left": lrec.reference, "right_candidates": [r.reference for r in fuzzy]},
                    )
                )
                continue
        if chosen is None:
            counts["missing_right_count"] += 1
            findings.append(
                FindingDraft(key, "__record__", FindingStatus.MISSING_RIGHT, lrec.label(), None, None, {"left": lrec.reference})
            )
            continue
        used.add(chosen.record_id)
        pair = compare_pair(lrec, chosen, key, opts, quality_for_pair, compare_customer, compare_lines)
        record_status = pair[0].status
        counts[
            {FindingStatus.MATCH: "matched_count", FindingStatus.MISMATCH: "mismatched_count"}.get(record_status, "ambiguous_count")
        ] += 1
        findings.extend(pair)

    for rrec in right:
        if rrec.record_id in used or rrec.record_id in duplicate_ids:
            continue
        counts["missing_left_count"] += 1
        key = f"{rrec.invoice_number or rrec.record_id} | {rrec.supplier or '?'}"
        findings.append(FindingDraft(key, "__record__", FindingStatus.MISSING_LEFT, None, rrec.label(), None, {"right": rrec.reference}))

    summary = {
        "matched_count": counts["matched_count"],
        "mismatched_count": counts["mismatched_count"],
        "ambiguous_count": counts["ambiguous_count"],
        "duplicate_count": counts["duplicate_count"],
        "missing_left_count": counts["missing_left_count"],
        "missing_right_count": counts["missing_right_count"],
        "left_records": len(left),
        "right_records": len(right),
    }
    return MatchResult(findings=findings, summary=summary)
