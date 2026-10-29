from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import PrincipalDep, SessionDep, client_ip
from app.core.config import get_settings
from app.core.permissions import ROLE_PERMISSIONS
from app.core.ratelimit import enforce_rate_limit
from app.modules.identity import service
from app.modules.identity.models import Organization, User
from app.modules.identity.schemas import (
    LoginRequest,
    MeResponse,
    OrganizationOut,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, session: SessionDep) -> User:
    """Create an organization and its first ADMIN user (only when REGISTRATION_MODE=open)."""
    await enforce_rate_limit("register", client_ip(request), get_settings().rate_limit_auth_per_minute)
    return await service.register(
        session, organization_name=body.organization_name, email=body.email, password=body.password, full_name=body.full_name
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, session: SessionDep) -> TokenResponse:
    limit = get_settings().rate_limit_auth_per_minute
    await enforce_rate_limit("login-ip", client_ip(request), limit * 5)
    await enforce_rate_limit("login-email", body.email.lower(), limit)
    return await service.login(session, email=body.email, password=body.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request, session: SessionDep) -> TokenResponse:
    await enforce_rate_limit("refresh", client_ip(request), get_settings().rate_limit_auth_per_minute * 6)
    return await service.refresh(session, refresh_token=body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, principal: PrincipalDep, session: SessionDep, all_sessions: bool = False) -> None:
    await service.logout(session, refresh_token=body.refresh_token, all_sessions=all_sessions, user_id=principal.user_id)


@router.get("/me", response_model=MeResponse)
async def me(principal: PrincipalDep, session: SessionDep) -> MeResponse:
    user = await session.get(User, principal.user_id)
    org = await session.get(Organization, principal.organization_id)
    assert user is not None and org is not None
    return MeResponse(
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(org),
        permissions=sorted(p.value for p in ROLE_PERMISSIONS[principal.role]),
    )
