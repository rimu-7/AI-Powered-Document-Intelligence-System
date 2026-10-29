from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select

from app.api.deps import Principal, SessionDep, require
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Permission
from app.modules.auditing.service import record_audit
from app.modules.identity import service
from app.modules.identity.models import User
from app.modules.identity.schemas import CreateUserRequest, UpdateUserRequest, UserOut
from app.shared.enums import Role
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/users", tags=["users"])
Admin = Annotated[Principal, Depends(require(Permission.USER_MANAGE))]


async def _get_user(session: SessionDep, principal: Principal, user_id: uuid.UUID) -> User:
    user = (
        await session.execute(select(User).where(User.id == user_id, User.organization_id == principal.organization_id))
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")
    return user


@router.get("", response_model=Page[UserOut])
async def list_users(principal: Admin, session: SessionDep, page: Annotated[PageParams, Depends(page_params)]) -> Page[UserOut]:
    base = select(User).where(User.organization_id == principal.organization_id)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.order_by(User.created_at, User.id).limit(page.limit).offset(page.offset))).scalars().all()
    return Page(items=[UserOut.model_validate(u) for u in rows], total=total, limit=page.limit, offset=page.offset)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: CreateUserRequest, principal: Admin, session: SessionDep) -> User:
    return await service.create_user(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        role=body.role,
    )


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: uuid.UUID, body: UpdateUserRequest, principal: Admin, session: SessionDep) -> User:
    user = await _get_user(session, principal, user_id)
    changes: dict[str, object] = {}
    if user.id == principal.user_id and (body.is_active is False or (body.role and body.role != Role.ADMIN)):
        raise ConflictError("Administrators cannot demote or disable themselves", code="SELF_LOCKOUT")
    if body.role is not None and body.role != user.role:
        changes["role"] = [user.role.value, body.role.value]
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        changes["is_active"] = [user.is_active, body.is_active]
        user.is_active = body.is_active
        if not body.is_active:
            await service.revoke_user_sessions(session, user.id, "user_disabled")
    if body.full_name is not None:
        user.full_name = body.full_name
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="user.updated",
        resource_type="user",
        resource_id=user.id,
        metadata=changes,
    )
    await session.commit()
    return user


@router.post("/{user_id}/revoke-sessions", status_code=status.HTTP_200_OK)
async def revoke_sessions(user_id: uuid.UUID, principal: Admin, session: SessionDep) -> dict[str, int]:
    user = await _get_user(session, principal, user_id)
    count = await service.revoke_user_sessions(session, user.id, "admin_revoked")
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="user.sessions_revoked",
        resource_type="user",
        resource_id=user.id,
        metadata={"count": count},
    )
    await session.commit()
    return {"revoked": count}
