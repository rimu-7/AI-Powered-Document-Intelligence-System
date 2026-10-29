from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import register_org

pytestmark = pytest.mark.integration


async def test_register_login_me(client: Any, org: dict[str, Any]) -> None:
    r = await client.get("/api/v1/auth/me", headers=org["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "ADMIN" and "user:manage" in body["permissions"]
    assert "password_hash" not in r.text


async def test_wrong_password_and_unknown_user_look_identical(client: Any, org: dict[str, Any]) -> None:
    a = await client.post("/api/v1/auth/login", json={"email": org["email"], "password": "Wrong-Password-1"})
    b = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "Wrong-Password-1"})
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["code"] == b.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_refresh_rotation_and_reuse_detection(client: Any, org: dict[str, Any]) -> None:
    first = org["tokens"]["refresh_token"]
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert r.status_code == 200
    second = r.json()["refresh_token"]
    assert second != first
    # Re-using the rotated token revokes the whole family...
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert r.status_code == 401 and r.json()["error"]["code"] == "REFRESH_REUSED"
    # ...including the legitimately rotated successor.
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": second})
    assert r.status_code == 401


async def test_logout_revokes_refresh(client: Any, org: dict[str, Any]) -> None:
    refresh = org["tokens"]["refresh_token"]
    r = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh}, headers=org["headers"])
    assert r.status_code == 204
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


async def test_missing_invalid_tokens(client: Any) -> None:
    assert (await client.get("/api/v1/documents")).status_code == 401
    r = await client.get("/api/v1/documents", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_INVALID"


async def test_roles_and_disabled_users(client: Any, org: dict[str, Any]) -> None:
    pw = "Viewer-Password-77"
    r = await client.post(
        "/api/v1/users", headers=org["headers"], json={"email": "viewer-x@example.com", "password": pw, "full_name": "V", "role": "VIEWER"}
    )
    assert r.status_code == 201, r.text
    viewer_id = r.json()["id"]
    login = (await client.post("/api/v1/auth/login", json={"email": "viewer-x@example.com", "password": pw})).json()
    vh = {"Authorization": f"Bearer {login['access_token']}"}
    assert (await client.get("/api/v1/documents", headers=vh)).status_code == 200
    r = await client.post("/api/v1/documents/upload", headers=vh, files=[("files", ("a.csv", b"a,b\n1,2\n", "text/csv"))])
    assert r.status_code == 403
    assert (await client.get("/api/v1/users", headers=vh)).status_code == 403
    # Disabling takes effect immediately, even with a still-valid access token.
    r = await client.patch(f"/api/v1/users/{viewer_id}", headers=org["headers"], json={"is_active": False})
    assert r.status_code == 200
    r = await client.get("/api/v1/documents", headers=vh)
    assert r.status_code == 401 and r.json()["error"]["code"] == "ACCOUNT_DISABLED"
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 401


async def test_weak_password_and_duplicate_email(client: Any, org: dict[str, Any]) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={"organization_name": "Xx Org", "email": "weak@example.com", "password": "alllowercaseletters", "full_name": "W"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEAK_PASSWORD"
    r = await client.post(
        "/api/v1/auth/register",
        json={"organization_name": "Yy Org", "email": org["email"].upper(), "password": "Another-Strong-Pass-1", "full_name": "D"},
    )
    assert r.status_code == 409


async def test_registration_can_be_disabled(client: Any, settings_override: Any) -> None:
    settings_override(REGISTRATION_MODE="disabled")
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        r = await c.post(
            "/api/v1/auth/register",
            json={"organization_name": "Zz Org", "email": "z@example.com", "password": "Strong-Password-99", "full_name": "Z"},
        )
        assert r.status_code == 403 and r.json()["error"]["code"] == "REGISTRATION_DISABLED"


async def test_rate_limit_login(client: Any, settings_override: Any) -> None:
    settings_override(RATE_LIMIT_ENABLED="true", RATE_LIMIT_AUTH_PER_MINUTE="3")
    other = await register_org(client)
    codes = []
    for _ in range(5):
        r = await client.post("/api/v1/auth/login", json={"email": other["email"], "password": "Wrong-Password-1"})
        codes.append(r.status_code)
    assert codes[-1] == 429 and "Retry-After" in r.headers
