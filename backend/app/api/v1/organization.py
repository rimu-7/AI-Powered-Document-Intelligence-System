"""Organization settings: currency policy for invoices that do not print one clearly."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import Principal, SessionDep, require
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.permissions import Permission
from app.modules.auditing.service import record_audit
from app.modules.extraction import currency_policy
from app.modules.extraction.currency_resolution import LEARN_THRESHOLD
from app.modules.identity.models import Organization
from app.shared.enums import CurrencyCode
from app.shared.money import AMBIGUOUS_SYMBOLS

router = APIRouter(prefix="/organization", tags=["organization"])
Reader = Annotated[Principal, Depends(require(Permission.DOCUMENT_READ))]
Admin = Annotated[Principal, Depends(require(Permission.ORG_ADMIN))]


class AmbiguousSymbol(BaseModel):
    symbol: str
    candidates: list[CurrencyCode]
    rule: CurrencyCode | None = Field(description="The organization's rule for this symbol, if any")
    learned: CurrencyCode | None = Field(description="What reviewers consistently chose for this symbol, if learned")
    learned_from: int = Field(description="Reviewer decisions behind the learned currency")


class CurrencySettingsOut(BaseModel):
    default_currency: CurrencyCode | None
    symbol_rules: dict[str, CurrencyCode]
    symbols: list[AmbiguousSymbol]
    learn_threshold: int = Field(description="Reviewer decisions needed before a symbol is resolved automatically")
    pending_invoices: int = Field(description="Invoices still waiting for a currency")


class CurrencySettingsUpdate(BaseModel):
    default_currency: CurrencyCode | None = None
    symbol_rules: dict[str, CurrencyCode] = Field(default_factory=dict, description='For example {"$": "USD"}')
    apply_to_pending: bool = Field(default=True, description="Also resolve invoices that are waiting for a currency")


class CurrencySettingsUpdated(CurrencySettingsOut):
    resolved_invoices: int = Field(description="Waiting invoices that received a currency from this change")


async def _organization(session: SessionDep, principal: Principal) -> Organization:
    org = await session.get(Organization, principal.organization_id)
    if org is None:
        raise NotFoundError("Organization not found")
    return org


async def _settings(session: SessionDep, principal: Principal) -> CurrencySettingsOut:
    policy = await currency_policy.load_policy(session, principal.organization_id)
    symbols = []
    for symbol, candidates in AMBIGUOUS_SYMBOLS.items():
        learned = policy.learned(symbol)
        symbols.append(
            AmbiguousSymbol(
                symbol=symbol,
                candidates=list(candidates),
                rule=policy.symbol_rules.get(symbol),
                learned=learned[0] if learned else None,
                learned_from=learned[1] if learned else 0,
            )
        )
    return CurrencySettingsOut(
        default_currency=policy.default_currency,
        symbol_rules=policy.symbol_rules,
        symbols=symbols,
        learn_threshold=LEARN_THRESHOLD,
        pending_invoices=await currency_policy.count_pending(session, principal.organization_id),
    )


@router.get("/currency-settings", response_model=CurrencySettingsOut)
async def get_currency_settings(principal: Reader, session: SessionDep) -> CurrencySettingsOut:
    return await _settings(session, principal)


@router.put("/currency-settings", response_model=CurrencySettingsUpdated)
async def update_currency_settings(body: CurrencySettingsUpdate, principal: Admin, session: SessionDep) -> CurrencySettingsUpdated:
    rules: dict[str, str] = {}
    for symbol, code in body.symbol_rules.items():
        candidates = AMBIGUOUS_SYMBOLS.get(symbol.strip())
        if candidates is None:
            raise ValidationFailedError(f"'{symbol}' is not an ambiguous currency symbol", code="INVALID_CURRENCY_RULE")
        if code not in candidates:
            allowed = ", ".join(candidates)
            raise ValidationFailedError(f"'{symbol}' cannot mean {code}; choose one of {allowed}", code="INVALID_CURRENCY_RULE")
        rules[symbol.strip()] = code.value
    org = await _organization(session, principal)
    before = {"default_currency": org.default_currency, "symbol_rules": dict(org.currency_symbol_rules or {})}
    org.default_currency = body.default_currency
    org.currency_symbol_rules = rules
    await session.flush()
    resolved = await currency_policy.apply_to_pending(session, principal) if body.apply_to_pending else 0
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="organization.currency_settings_updated",
        resource_type="organization",
        resource_id=principal.organization_id,
        metadata={
            "before": before,
            "after": {"default_currency": body.default_currency, "symbol_rules": rules},
            "resolved_invoices": resolved,
        },
    )
    await session.commit()
    current = await _settings(session, principal)
    return CurrencySettingsUpdated(**current.model_dump(), resolved_invoices=resolved)
