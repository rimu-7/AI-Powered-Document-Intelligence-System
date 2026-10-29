"""Create an organization and its first ADMIN user (works in any environment).

  python -m scripts.create_admin --org "Acme Ltd" --email admin@acme.example
The password is read from ADMIN_PASSWORD or prompted; it is never logged.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import secrets
import uuid

from app.core.database import get_async_sessionmaker
from app.core.security import hash_password
from app.modules.auditing.service import record_audit
from app.modules.identity.models import Organization, User
from app.modules.identity.service import check_password_policy
from app.shared.enums import OrganizationStatus, Role


async def run(org_name: str, email: str, password: str) -> None:
    check_password_policy(password)
    async with get_async_sessionmaker()() as session:
        org = Organization(
            id=uuid.uuid4(),
            name=org_name,
            slug=f"{org_name.lower().replace(' ', '-')[:60]}-{secrets.token_hex(3)}",
            status=OrganizationStatus.ACTIVE,
        )
        session.add(org)
        await session.flush()
        user = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            email=email.lower(),
            password_hash=hash_password(password),
            full_name="Administrator",
            role=Role.ADMIN,
            is_active=True,
        )
        session.add(user)
        record_audit(
            session,
            organization_id=org.id,
            actor_id=None,
            action="organization.created_by_cli",
            resource_type="organization",
            resource_id=org.id,
        )
        await session.commit()
        print(f"organization {org.id} / admin {user.id} created")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    asyncio.run(run(args.org, args.email, password))


if __name__ == "__main__":
    main()
