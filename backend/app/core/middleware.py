"""Pure ASGI middleware: request context/metrics, body-size limit, security headers."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import error_body
from app.core.logging import get_logger, request_id_var
from app.core.metrics import HTTP_ERRORS, HTTP_LATENCY, HTTP_REQUESTS

logger = get_logger("docintel.http")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9\-_.]{8,64}$")


class RequestContextMiddleware:
    """Assigns a correlation ID, logs one structured line per request, records metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = _header(scope, b"x-request-id")
        request_id = incoming if incoming and _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            route = scope.get("route")
            route_path = getattr(route, "path", None) or "unmatched"
            status = status_holder["status"]
            method = scope.get("method", "GET")
            HTTP_REQUESTS.labels(method, route_path, f"{status // 100}xx").inc()
            HTTP_LATENCY.labels(method, route_path).observe(duration)
            if status >= 500:
                HTTP_ERRORS.labels(route_path).inc()
            if route_path not in ("/health/live", "/metrics"):
                logger.info(
                    "http_request",
                    extra={
                        "method": method,
                        "route": route_path,
                        "status": status,
                        "duration_ms": round(duration * 1000, 2),
                    },
                )
            request_id_var.reset(token)


class BodySizeLimitMiddleware:
    """Rejects requests whose body exceeds ``max_bytes`` while streaming."""

    def __init__(self, app: ASGIApp, max_bytes: int, default_max_bytes: int = 2 * 1024 * 1024) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.default_max_bytes = default_max_bytes

    def _limit_for(self, scope: Scope) -> int:
        path: str = scope.get("path", "")
        if path.endswith(("/documents/upload", "/documents/upload/raw")):
            return self.max_bytes
        return self.default_max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit_for(scope)
        declared = _header(scope, b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await _send_413(send, limit)
            return
        received = 0
        exceeded = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge()
            return message

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await _send_413(send, limit)
        except Exception:
            if exceeded and not response_started:
                await _send_413(send, limit)
                return
            raise


class _BodyTooLarge(Exception):
    pass


async def _send_413(send: Send, limit: int) -> None:
    import json

    body = json.dumps(error_body("PAYLOAD_TOO_LARGE", f"Request body exceeds the {limit} byte limit")).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[Any] = list(message.get("headers", []))
                existing = {k.lower() for k, _ in headers}
                defaults = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                    b"cache-control": b"no-store",
                }
                if self.hsts:
                    defaults[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                for key, value in defaults.items():
                    if key not in existing:
                        headers.append((key, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            try:
                return str(value.decode("latin-1"))
            except UnicodeDecodeError:
                return None
    return None
