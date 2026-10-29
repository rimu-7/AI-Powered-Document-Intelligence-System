from __future__ import annotations

import json
import logging
import uuid

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.logging import JsonFormatter, redact
from app.core.permissions import Permission, has_permission
from app.core.security import create_access_token, decode_access_token, hash_password, hash_token, verify_password
from app.modules.search.embeddings import HashingEmbeddingProvider
from app.modules.search.indexing import chunk_text
from app.shared.enums import Role


def test_password_hashing_is_argon2_and_verifies() -> None:
    h = hash_password("Sufficiently-Long-123")
    assert h.startswith("$argon2id$")
    assert verify_password("Sufficiently-Long-123", h)
    assert not verify_password("wrong", h)
    assert not verify_password("anything", None)


def test_access_token_roundtrip_and_tampering() -> None:
    uid, org = uuid.uuid4(), uuid.uuid4()
    token, ttl = create_access_token(uid, org, "ANALYST")
    claims = decode_access_token(token)
    assert claims.user_id == uid and claims.organization_id == org and ttl == get_settings().access_token_ttl_seconds
    forged = jwt.encode(
        {"sub": str(uid), "org": str(org), "type": "access", "exp": 9999999999, "iat": 0},
        "wrong-secret-wrong-secret-wrong-secret",
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(forged)
    none_alg = jwt.encode({"sub": str(uid)}, None, algorithm="none")  # type: ignore[arg-type]
    with pytest.raises(AuthenticationError):
        decode_access_token(none_alg)


def test_refresh_tokens_stored_as_hashes() -> None:
    assert len(hash_token("abc")) == 64 and hash_token("abc") != "abc"


def test_rbac_matrix() -> None:
    assert has_permission(Role.VIEWER, Permission.DOCUMENT_READ)
    assert not has_permission(Role.VIEWER, Permission.DOCUMENT_UPLOAD)
    assert has_permission(Role.ANALYST, Permission.COMPARE)
    assert not has_permission(Role.ANALYST, Permission.INVOICE_CORRECT)
    assert has_permission(Role.REVIEWER, Permission.INVOICE_APPROVE)
    assert not has_permission(Role.REVIEWER, Permission.USER_MANAGE)
    assert has_permission(Role.ADMIN, Permission.USER_MANAGE)


def test_log_redaction() -> None:
    assert redact({"password": "x", "nested": {"refresh_token": "y", "ok": 1}}) == {
        "password": "[REDACTED]",
        "nested": {"refresh_token": "[REDACTED]", "ok": 1},
    }
    token, _ = create_access_token(uuid.uuid4(), uuid.uuid4(), "ADMIN")
    record = logging.LogRecord("t", logging.INFO, "", 0, f"Authorization: Bearer {token} api_key=sk-123", (), None)
    record.extracted_text = "Confidential invoice body"
    out = json.loads(JsonFormatter().format(record))
    assert token not in out["event"] and "sk-123" not in out["event"]
    assert out["extracted_text"] == "[REDACTED]"


def test_hash_embeddings_are_deterministic_normalized_and_lexical() -> None:
    emb = HashingEmbeddingProvider(1024)
    a, b, c = emb.embed(["office chair invoice", "invoice for office chairs", "quarterly balance sheet"])
    assert a == emb.embed(["office chair invoice"])[0]
    assert abs(sum(v * v for v in a) - 1.0) < 1e-9

    def cos(x: list[float], y: list[float]) -> float:
        return sum(i * j for i, j in zip(x, y, strict=True))

    assert cos(a, b) > cos(a, c)


def test_chunking_is_bounded_with_overlap() -> None:
    text = "\n".join(f"line {i}: " + "word " * 20 for i in range(200))
    chunks = chunk_text(text, 1200, 150)
    assert all(len(c) <= 1200 for c in chunks)
    assert chunks[0].startswith("line 0") and "line 199" in chunks[-1]
