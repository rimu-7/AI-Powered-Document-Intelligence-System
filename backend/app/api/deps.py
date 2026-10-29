"""Request dependencies: DB session, authenticated principal, permissions, rate limits."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_sessionmaker
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.permissions import Permission, has_permission
from app.core.ratelimit import enforce_rate_limit
from app.core.security import decode_access_token
from app.modules.identity.models import Organization, User
from app.shared.enums import OrganizationStatus, Role

_bearer = HTTPBearer(auto_error=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_async_sessionmaker()() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: Role
    email: str

    def can(self, permission: Permission) -> bool:
        return has_permission(self.role, permission)


async def get_principal(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(credentials.credentials)
    # Role and status come from the database, not from the token, so role
    # changes and deactivation take effect immediately.
    row = (
        await session.execute(
            select(User, Organization.status).join(Organization, Organization.id == User.organization_id).where(User.id == claims.user_id)
        )
    ).first()
    if row is None:
        raise AuthenticationError("Unknown user", code="TOKEN_INVALID")
    user, org_status = row
    if not user.is_active or org_status != OrganizationStatus.ACTIVE:
        raise AuthenticationError("Account disabled", code="ACCOUNT_DISABLED")
    if user.organization_id != claims.organization_id:
        raise AuthenticationError("Token organization mismatch", code="TOKEN_INVALID")
    principal = Principal(user.id, user.organization_id, user.role, user.email)
    await enforce_rate_limit("user", str(user.id), get_settings().rate_limit_default_per_minute)
    return principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require(permission: Permission) -> Callable[[Principal], Awaitable[Principal]]:
    async def dependency(principal: PrincipalDep) -> Principal:
        if not principal.can(permission):
            raise PermissionDeniedError(f"Missing permission: {permission.value}")
        return principal

    return dependency


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
