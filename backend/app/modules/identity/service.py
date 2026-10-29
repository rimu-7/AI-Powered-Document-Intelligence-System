"""Registration, login, refresh-token rotation with reuse detection, logout."""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, ConflictError, PermissionDeniedError, ValidationFailedError
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, hash_token, new_refresh_token, password_needs_rehash, verify_password
from app.modules.auditing.service import record_audit
from app.modules.identity.models import Organization, RefreshSession, User
from app.modules.identity.schemas import TokenResponse
from app.shared.enums import OrganizationStatus, Role

logger = get_logger(__name__)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
    return f"{slug}-{secrets.token_hex(3)}"


def check_password_policy(password: str) -> None:
    settings = get_settings()
    if len(password) < settings.password_min_length:
        raise ValidationFailedError(f"Password must be at least {settings.password_min_length} characters", code="WEAK_PASSWORD")
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        raise ValidationFailedError("Password must mix at least three of: lowercase, uppercase, digits, symbols", code="WEAK_PASSWORD")


async def register(session: AsyncSession, *, organization_name: str, email: str, password: str, full_name: str) -> User:
    if get_settings().registration_mode != "open":
        raise PermissionDeniedError("Self-registration is disabled", code="REGISTRATION_DISABLED")
    check_password_policy(password)
    org = Organization(id=uuid.uuid4(), name=organization_name.strip(), slug=_slugify(organization_name), status=OrganizationStatus.ACTIVE)
    user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=email.lower(),
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        role=Role.ADMIN,
        is_active=True,
    )
    session.add(org)
    await session.flush()
    session.add(user)
    record_audit(
        session,
        organization_id=org.id,
        actor_id=user.id,
        action="organization.registered",
        resource_type="organization",
        resource_id=org.id,
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("An account with this email already exists", code="EMAIL_TAKEN") from exc
    return user


async def create_user(
    session: AsyncSession, *, organization_id: uuid.UUID, actor_id: uuid.UUID, email: str, password: str, full_name: str, role: Role
) -> User:
    check_password_policy(password)
    user = User(
        id=uuid.uuid4(),
        organization_id=organization_id,
        email=email.lower(),
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        role=role,
        is_active=True,
    )
    session.add(user)
    record_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="user.created",
        resource_type="user",
        resource_id=user.id,
        metadata={"role": role.value},
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("An account with this email already exists", code="EMAIL_TAKEN") from exc
    return user


async def _issue(session: AsyncSession, user: User, family_id: uuid.UUID | None = None) -> tuple[TokenResponse, RefreshSession]:
    settings = get_settings()
    access, ttl = create_access_token(user.id, user.organization_id, user.role.value)
    refresh = new_refresh_token()
    record = RefreshSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_token(refresh),
        family_id=family_id or uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds),
    )
    session.add(record)
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=ttl), record


async def login(session: AsyncSession, *, email: str, password: str) -> TokenResponse:
    row = (
        await session.execute(
            select(User, Organization.status)
            .join(Organization, Organization.id == User.organization_id)
            .where(func.lower(User.email) == email.lower())
        )
    ).first()
    user, org_status = (row[0], row[1]) if row else (None, None)
    # verify_password runs even for unknown users (dummy hash) to keep timing uniform.
    valid = verify_password(password, user.password_hash if user else None)
    if not valid or user is None:
        raise AuthenticationError("Invalid email or password", code="INVALID_CREDENTIALS")
    if not user.is_active or org_status != OrganizationStatus.ACTIVE:
        raise AuthenticationError("Account disabled", code="ACCOUNT_DISABLED")
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    tokens, _ = await _issue(session, user)
    record_audit(
        session, organization_id=user.organization_id, actor_id=user.id, action="auth.login", resource_type="user", resource_id=user.id
    )
    await session.commit()
    return tokens


async def refresh(session: AsyncSession, *, refresh_token: str) -> TokenResponse:
    now = datetime.now(UTC)
    record = (
        await session.execute(select(RefreshSession).where(RefreshSession.token_hash == hash_token(refresh_token)).with_for_update())
    ).scalar_one_or_none()
    if record is None:
        raise AuthenticationError("Invalid refresh token", code="REFRESH_INVALID")
    user = await session.get(User, record.user_id)
    if record.revoked_at is not None:
        # Reuse of a rotated/revoked token: assume theft, revoke the whole family.
        await session.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == record.family_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason="reuse_detected")
        )
        if user is not None:
            record_audit(
                session,
                organization_id=user.organization_id,
                actor_id=user.id,
                action="auth.refresh_reuse_detected",
                resource_type="refresh_session",
                resource_id=record.family_id,
            )
        await session.commit()
        logger.warning("refresh_token_reuse_detected")
        raise AuthenticationError("Refresh token reuse detected; session revoked", code="REFRESH_REUSED")
    if record.expires_at <= now:
        raise AuthenticationError("Refresh token expired", code="REFRESH_EXPIRED")
    if user is None or not user.is_active:
        raise AuthenticationError("Account disabled", code="ACCOUNT_DISABLED")
    org = await session.get(Organization, user.organization_id)
    if org is None or org.status != OrganizationStatus.ACTIVE:
        raise AuthenticationError("Account disabled", code="ACCOUNT_DISABLED")
    tokens, new_record = await _issue(session, user, family_id=record.family_id)
    record.revoked_at = now
    record.revoked_reason = "rotated"
    record.replaced_by_id = new_record.id
    record.last_used_at = now
    await session.commit()
    return tokens


async def logout(session: AsyncSession, *, refresh_token: str, all_sessions: bool = False, user_id: uuid.UUID | None = None) -> None:
    now = datetime.now(UTC)
    record = (
        await session.execute(select(RefreshSession).where(RefreshSession.token_hash == hash_token(refresh_token)))
    ).scalar_one_or_none()
    if record is None or (user_id is not None and record.user_id != user_id):
        return  # idempotent; do not reveal token validity
    stmt = update(RefreshSession).where(RefreshSession.revoked_at.is_(None))
    stmt = (
        stmt.where(RefreshSession.user_id == record.user_id) if all_sessions else stmt.where(RefreshSession.family_id == record.family_id)
    )
    await session.execute(stmt.values(revoked_at=now, revoked_reason="logout"))
    await session.commit()


async def revoke_user_sessions(session: AsyncSession, user_id: uuid.UUID, reason: str) -> int:
    result = await session.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
