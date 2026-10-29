"""Structured JSON logging with request/job context and secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
document_id_var: ContextVar[str | None] = ContextVar("document_id", default=None)
stage_var: ContextVar[str | None] = ContextVar("stage", default=None)

_SERVICE_NAME = "docintel"

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "secret",
    "jwt",
    "cookie",
    "x-api-key",
    "text",
    "extracted_text",
    "content",
}

_BEARER_RE = re.compile(r"(?i)bearer\s+[a-z0-9\-_.=]+")
_JWT_RE = re.compile(r"eyJ[a-zA-Z0-9_-]{5,}\.[a-zA-Z0-9_-]{5,}\.[a-zA-Z0-9_-]{5,}")
_KEYVAL_RE = re.compile(r"(?i)(password|secret|api[_-]?key|token)=([^\s&]+)")


def redact_text(value: str) -> str:
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    value = _JWT_RE.sub("[REDACTED_JWT]", value)
    return _KEYVAL_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)


def redact(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if str(k).lower() in SENSITIVE_KEYS else redact(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v, depth + 1) for v in value[:50]]
    if isinstance(value, str):
        return redact_text(value[:2000])
    return value


_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": _SERVICE_NAME,
            "logger": record.name,
            "event": redact_text(record.getMessage()),
        }
        for key, var in (
            ("request_id", request_id_var),
            ("job_id", job_id_var),
            ("document_id", document_id_var),
            ("stage", stage_var),
        ):
            val = var.get()
            if val:
                payload[key] = val
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED}
        if extras:
            payload.update(redact(extras))
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
            payload["exception"] = redact_text(self.formatException(record.exc_info))[-4000:]
        return json.dumps(payload, default=str)


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.msg = redact_text(str(record.msg))
        line = super().format(record)
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED}
        return f"{line} {redact(extras)}" if extras else line


def configure_logging(level: str = "INFO", json_logs: bool = True, service: str = "docintel") -> None:
    global _SERVICE_NAME
    _SERVICE_NAME = service
    # sys.__stdout__: Celery may replace sys.stdout with a logging proxy.
    handler = logging.StreamHandler(sys.__stdout__)
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(PlainFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("botocore", "boto3", "urllib3", "s3transfer", "httpx", "httpcore", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # Uvicorn access logs duplicate our structured request log.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
