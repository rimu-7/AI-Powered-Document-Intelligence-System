"""Development bootstrap (refuses to run when APP_ENV=production).

  python -m scripts.bootstrap --buckets-only   wait for object storage and create buckets
  python -m scripts.bootstrap                  + dev organization/admin user + demo documents

Prints the generated admin password once; it is not stored anywhere else.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
import time

from app.core.config import get_settings


def wait_for_storage(timeout: int = 120) -> None:
    from app.modules.documents.storage import get_storage

    deadline = time.monotonic() + timeout
    while True:
        try:
            get_storage().ensure_buckets()
            print("object storage ready; buckets ensured")
            return
        except Exception as exc:
            if time.monotonic() > deadline:
                raise SystemExit(f"object storage not reachable: {type(exc).__name__}") from exc
            time.sleep(2)


async def create_dev_admin(email: str, password: str) -> bool:
    from sqlalchemy import func, select

    from app.core.database import get_async_sessionmaker
    from app.modules.identity.models import User
    from scripts.create_admin import run

    async with get_async_sessionmaker()() as session:
        exists = (await session.execute(select(User).where(func.lower(User.email) == email.lower()))).scalar_one_or_none()
    if exists:
        print(f"admin {email} already exists")
        return False
    await run("Demo Organization", email, password)
    return True


def upload_demo(api: str, email: str, password: str) -> None:
    import random

    import httpx

    from evaluation.synthetic import (
        image_bytes,
        invoice_pdf_bytes,
        random_invoice,
        register_rows,
        register_xlsx_bytes,
        scanned_pdf_bytes,
    )

    rng = random.Random(2026)
    specs = [random_invoice(rng, i + 1) for i in range(4)]
    files = [
        ("demo-invoice-1.pdf", invoice_pdf_bytes([specs[0]]), "application/pdf"),
        ("demo-multi-invoice.pdf", invoice_pdf_bytes(specs[1:3]), "application/pdf"),
        ("demo-scanned.pdf", scanned_pdf_bytes(invoice_pdf_bytes([specs[3]])), "application/pdf"),
        ("demo-receipt.png", image_bytes(invoice_pdf_bytes([specs[0]])), "image/png"),
        (
            "demo-ap-register.xlsx",
            register_xlsx_bytes(register_rows(specs)),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ]
    with httpx.Client(base_url=api, timeout=60) as client:
        token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).raise_for_status().json()["access_token"]
        r = client.post("/api/v1/documents/upload", headers={"Authorization": f"Bearer {token}"}, files=[("files", f) for f in files])
        r.raise_for_status()
        for res in r.json()["results"]:
            print(f"  {res['filename']}: {res['status']} job={res.get('job_id')}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--buckets-only", action="store_true")
    parser.add_argument("--email", default=os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "admin@docintel.local"))
    parser.add_argument("--api", default=os.environ.get("BOOTSTRAP_API_URL", "http://api:8000"))
    parser.add_argument("--no-demo", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if settings.is_production:
        sys.exit("bootstrap is a development-only command (APP_ENV=production)")
    wait_for_storage()
    if args.buckets_only:
        return
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD") or (secrets.token_urlsafe(12) + "-Aa1")
    created = asyncio.run(create_dev_admin(args.email, password))
    if created:
        print(f"admin password (shown once): {password}")
        if not args.no_demo:
            upload_demo(args.api, args.email, password)
    elif not args.no_demo:
        print("demo upload skipped (admin already existed; password unknown)")


if __name__ == "__main__":
    main()
