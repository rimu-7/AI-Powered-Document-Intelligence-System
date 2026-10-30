"""Organization-level currency resolution: settings, supplier history, learning.

The decisions themselves are made by :mod:`currency_resolution` (pure). This
module loads what they need from the database and applies them in two places:

* extraction (sync, in the worker) for every new invoice without a currency;
* :func:`apply_to_pending` (async, in the API) when an admin changes the
  policy, for invoices that are still waiting for a currency.

Only trustworthy history is used: currencies that were printed on the invoice
or set by a reviewer. Automatic decisions never feed later decisions, so a
wrong default cannot reinforce itself.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import Principal
from app.modules.documents.models import Document
from app.modules.documents.service import mark_comparisons_stale
from app.modules.extraction.currency_resolution import (
    Decision,
    OrganizationPolicy,
    apply_decision,
    candidates_for,
    decide_for_organization,
    rank_candidates,
)
from app.modules.extraction.models import InvoiceRecord
from app.modules.extraction.schemas import NormalizedInvoice
from app.modules.identity.models import Organization
from app.modules.jobs.service import build_run
from app.shared.enums import CurrencyCode, CurrencySource, DocumentStatus, JobType, ReviewStatus
from app.shared.money import AMBIGUOUS_SYMBOLS, to_currency_code
from app.shared.text import normalize_supplier

TRUSTED_SOURCES = (CurrencySource.PRINTED, CurrencySource.HUMAN)


# --- queries (shared by the sync worker and the async API) ---------------------------


def _policy_stmt(organization_id: uuid.UUID) -> Select[CurrencyCode | None, dict[str, str]]:
    return select(Organization.default_currency, Organization.currency_symbol_rules).where(Organization.id == organization_id)


def _reviewer_choices_stmt(organization_id: uuid.UUID) -> Select[str | None, CurrencyCode | None, int]:
    return (
        select(InvoiceRecord.currency_raw, InvoiceRecord.currency, func.count())
        .where(
            InvoiceRecord.organization_id == organization_id,
            InvoiceRecord.superseded_at.is_(None),
            InvoiceRecord.currency_source == CurrencySource.HUMAN,
            InvoiceRecord.currency.is_not(None),
            InvoiceRecord.currency_raw.in_(list(AMBIGUOUS_SYMBOLS)),
        )
        .group_by(InvoiceRecord.currency_raw, InvoiceRecord.currency)
    )


def _supplier_history_stmt(
    organization_id: uuid.UUID, normalized_supplier: str | None, supplier_tax_id: str | None, exclude_document_id: uuid.UUID
) -> Select[CurrencyCode | None, int] | None:
    same_supplier = []
    if normalized_supplier:
        same_supplier.append(InvoiceRecord.normalized_supplier == normalized_supplier)
    if supplier_tax_id and supplier_tax_id.strip():
        same_supplier.append(InvoiceRecord.supplier_tax_id == supplier_tax_id.strip())
    if not same_supplier:
        return None
    return (
        select(InvoiceRecord.currency, func.count())
        .where(
            InvoiceRecord.organization_id == organization_id,
            InvoiceRecord.superseded_at.is_(None),
            InvoiceRecord.document_id != exclude_document_id,
            InvoiceRecord.currency.is_not(None),
            InvoiceRecord.currency_source.in_(TRUSTED_SOURCES),
            InvoiceRecord.review_status != ReviewStatus.REJECTED,
            or_(*same_supplier),
        )
        .group_by(InvoiceRecord.currency)
    )


def _policy_from_rows(policy_row: Any, choice_rows: list[Any]) -> OrganizationPolicy:
    policy = OrganizationPolicy()
    if policy_row is not None:
        policy.default_currency = to_currency_code(policy_row[0])
        for symbol, code in (policy_row[1] or {}).items():
            if (cur := to_currency_code(code)) is not None:
                policy.symbol_rules[symbol] = cur
    for raw, code, n in choice_rows:
        cur = to_currency_code(code)
        if cur is not None:
            policy.reviewer_choices.setdefault(str(raw).strip(), Counter())[cur] += int(n)
    return policy


def _history_from_rows(rows: list[Any]) -> Counter[CurrencyCode]:
    history: Counter[CurrencyCode] = Counter()
    for code, n in rows:
        if (cur := to_currency_code(code)) is not None:
            history[cur] += int(n)
    return history


def load_policy_sync(session: Session, organization_id: uuid.UUID) -> OrganizationPolicy:
    row = session.execute(_policy_stmt(organization_id)).first()
    return _policy_from_rows(row, list(session.execute(_reviewer_choices_stmt(organization_id)).all()))


async def load_policy(session: AsyncSession, organization_id: uuid.UUID) -> OrganizationPolicy:
    row = (await session.execute(_policy_stmt(organization_id))).first()
    return _policy_from_rows(row, list((await session.execute(_reviewer_choices_stmt(organization_id))).all()))


# --- extraction (worker) ----------------------------------------------------------------


def resolve_with_organization(
    session: Session, organization_id: uuid.UUID, document_id: uuid.UUID, inv: NormalizedInvoice, policy: OrganizationPolicy
) -> None:
    """Steps 3–6 for an extracted invoice whose document did not decide the currency."""
    if inv.currency is not None:
        return
    candidates = candidates_for(inv.currency_raw)
    if candidates is None:
        return
    stmt = _supplier_history_stmt(organization_id, normalize_supplier(inv.supplier_name), inv.supplier_tax_id, document_id)
    history = _history_from_rows(list(session.execute(stmt).all())) if stmt is not None else Counter()
    decision = decide_for_organization(inv.currency_raw, candidates, history, policy)
    if decision is not None:
        apply_decision(inv, decision)
    elif inv.currency_raw:
        previous = [c for c in (to_currency_code(x) for x in inv.alternatives.get("currency", [])) if c is not None]
        base = tuple(previous) if set(previous) == set(candidates) else candidates
        inv.alternatives["currency"] = list(rank_candidates(base, (), history, policy, inv.currency_raw.strip()))


# --- stored invoices (API) --------------------------------------------------------------


def _pending_stmt(organization_id: uuid.UUID) -> Select[Any]:
    return select(InvoiceRecord).where(
        InvoiceRecord.organization_id == organization_id,
        InvoiceRecord.superseded_at.is_(None),
        InvoiceRecord.currency.is_(None),
        InvoiceRecord.review_status.not_in([ReviewStatus.APPROVED, ReviewStatus.REJECTED]),
        ~InvoiceRecord.corrected_fields_json.contains(["currency"]),
    )


async def count_pending(session: AsyncSession, organization_id: uuid.UUID) -> int:
    return int((await session.execute(select(func.count()).select_from(_pending_stmt(organization_id).subquery()))).scalar_one())


def _apply_to_record(record: InvoiceRecord, decision: Decision) -> None:
    evidence = dict(record.source_evidence_json or {})
    current = evidence.get("currency")
    printed: dict[str, Any] = current if isinstance(current, dict) else {}
    evidence["currency"] = {
        **{k: printed.get(k) for k in ("document_id", "page_number", "supporting_text", "bounding_box") if printed.get(k) is not None},
        "extraction_method": f"currency:{decision.source.value.lower()}",
        "support": "DERIVED",
        "reason": decision.reason,
        "resolved_at": datetime.now(UTC).isoformat(),
    }
    support = dict(record.field_support_json or {})
    support["currency"] = "DERIVED"
    alternatives = dict(record.alternatives_json or {})
    notes = [
        n
        for n in alternatives.get("notes", [])
        if not (n.get("field") == "currency" and n.get("code") in ("CURRENCY_AMBIGUOUS", "CURRENCY_INFERRED"))
    ]
    notes.append({"field": "currency", "code": "CURRENCY_INFERRED", "message": decision.reason})
    alternatives["notes"] = notes
    record.currency = decision.currency
    record.currency_source = decision.source
    record.source_evidence_json = evidence
    record.field_support_json = support
    record.alternatives_json = alternatives


async def apply_to_pending(session: AsyncSession, principal: Principal) -> int:
    """Resolve waiting invoices with the current policy and revalidate each one.

    Returns the number of invoices that now have a currency. The caller commits.
    """
    policy = await load_policy(session, principal.organization_id)
    records = list((await session.execute(_pending_stmt(principal.organization_id).with_for_update(skip_locked=True))).scalars())
    touched_documents: set[uuid.UUID] = set()
    resolved = 0
    for record in records:
        candidates = candidates_for(record.currency_raw)
        if candidates is None:
            continue
        stmt = _supplier_history_stmt(principal.organization_id, record.normalized_supplier, record.supplier_tax_id, record.document_id)
        history = _history_from_rows(list((await session.execute(stmt)).all())) if stmt is not None else Counter()
        decision = decide_for_organization(record.currency_raw, candidates, history, policy)
        if decision is None:
            continue
        _apply_to_record(record, decision)
        run, extras = build_run(
            principal,
            JobType.REVALIDATION,
            document_id=record.document_id,
            payload={"invoice_id": str(record.id), "reason": "currency policy"},
        )
        session.add(run)
        await session.flush()
        session.add_all(extras)
        touched_documents.add(record.document_id)
        resolved += 1
    for document_id in touched_documents:
        await mark_comparisons_stale(session, principal.organization_id, document_id, "currency resolved by policy")
        doc = await session.get(Document, document_id)
        if doc is not None:
            doc.status = DocumentStatus.PROCESSING
    return resolved
