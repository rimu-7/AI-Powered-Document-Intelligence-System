"""Role-based permissions."""

from __future__ import annotations

from enum import StrEnum

from app.shared.enums import Role


class Permission(StrEnum):
    DOCUMENT_READ = "document:read"
    DOCUMENT_UPLOAD = "document:upload"
    DOCUMENT_DELETE = "document:delete"
    DOCUMENT_PROCESS = "document:process"
    SEARCH = "search"
    COMPARE = "compare"
    EXTRACTION_READ = "extraction:read"
    INVOICE_CORRECT = "invoice:correct"
    INVOICE_APPROVE = "invoice:approve"
    REVIEW_READ = "review:read"
    JOB_READ = "job:read"
    JOB_MANAGE = "job:manage"
    USER_MANAGE = "user:manage"
    ORG_ADMIN = "org:admin"
    AUDIT_READ = "audit:read"
    OPS_ADMIN = "ops:admin"


_VIEWER = {
    Permission.DOCUMENT_READ,
    Permission.EXTRACTION_READ,
    Permission.JOB_READ,
    Permission.REVIEW_READ,
    Permission.SEARCH,
}
_ANALYST = _VIEWER | {
    Permission.DOCUMENT_UPLOAD,
    Permission.DOCUMENT_PROCESS,
    Permission.COMPARE,
    Permission.JOB_MANAGE,
}
_REVIEWER = _ANALYST | {Permission.INVOICE_CORRECT, Permission.INVOICE_APPROVE}
_ADMIN = _REVIEWER | {
    Permission.DOCUMENT_DELETE,
    Permission.USER_MANAGE,
    Permission.ORG_ADMIN,
    Permission.AUDIT_READ,
    Permission.OPS_ADMIN,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(_VIEWER),
    Role.ANALYST: frozenset(_ANALYST),
    Role.REVIEWER: frozenset(_REVIEWER),
    Role.ADMIN: frozenset(_ADMIN),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
