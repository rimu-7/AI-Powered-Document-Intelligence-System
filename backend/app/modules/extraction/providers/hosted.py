"""OpenAI-compatible chat-completions provider (Mistral by default).

* Strict JSON-schema structured output (or ``json_object`` mode where the
  provider lacks schema support), validated again with Pydantic.
* Bounded timeouts; retries only for transient failures (timeouts, 408/409/
  429/5xx) with exponential backoff, jitter, and ``Retry-After`` support.
* Authentication/permission/bad-request errors fail immediately.
* One repair attempt for schema-invalid output, then a permanent error.
* A Redis-backed semaphore bounds concurrent requests across all workers.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import LLM_REQUESTS, LLM_RETRIES, LLM_TOKENS
from app.modules.extraction.prompts import (
    CLASSIFY_SYSTEM_PROMPT,
    CLASSIFY_USER_TEMPLATE,
    INVOICE_SYSTEM_PROMPT,
    INVOICE_USER_TEMPLATE,
)
from app.modules.extraction.providers.base import (
    ClassificationResponse,
    ExtractionRequest,
    ProviderPermanentError,
    ProviderResult,
    ProviderSchemaError,
    ProviderTransientError,
)
from app.modules.extraction.schemas import RawClassification, RawExtraction, strict_json_schema

logger = get_logger(__name__)

_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


@contextmanager
def _concurrency_slot(limit: int, ttl: int = 300) -> Iterator[None]:
    """Distributed counting semaphore. Falls back to no limit if Redis is down."""
    from app.core.redis import get_sync_redis

    key = "llm:inflight"
    acquired = False
    deadline = time.monotonic() + ttl
    try:
        client = get_sync_redis()
        while time.monotonic() < deadline:
            count: Any = client.incr(key)
            client.expire(key, ttl)
            if int(count) <= limit:
                acquired = True
                break
            client.decr(key)
            time.sleep(0.25 + random.random() * 0.5)
        if not acquired:
            raise ProviderTransientError("LLM concurrency slot not available")
    except ProviderTransientError:
        raise
    except Exception:  # noqa: BLE001 - Redis outage must not block extraction
        logger.warning("llm_semaphore_unavailable")
        acquired = False
    try:
        yield
    finally:
        if acquired:
            try:
                get_sync_redis().decr(key)
            except Exception:  # noqa: BLE001
                pass


class HostedLLMProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        max_retries: int,
        response_format: str,
        max_concurrency: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.response_format = response_format
        self.max_concurrency = max_concurrency
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=10.0),
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    def provider_name(self) -> str:
        return "hosted-llm"

    def model_name(self) -> str:
        return self.model

    def healthcheck(self) -> bool:
        try:
            response = self._client.get(f"{self.base_url}/models", timeout=5)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def _format(self, model: type[BaseModel], name: str) -> dict[str, Any]:
        if self.response_format == "json_schema":
            return {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": strict_json_schema(model), "strict": True},
            }
        return {"type": "json_object"}

    def _post(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        attempts = 0
        while True:
            attempts += 1
            try:
                response = self._client.post(f"{self.base_url}/chat/completions", json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                reason = "timeout" if isinstance(exc, httpx.TimeoutException) else "transport"
                if attempts > self.max_retries:
                    LLM_REQUESTS.labels(self.provider_name(), "transient_error").inc()
                    raise ProviderTransientError(f"LLM request failed: {reason}") from exc
                LLM_RETRIES.labels(self.provider_name(), reason).inc()
                self._sleep(attempts, None)
                continue
            if response.status_code == 200:
                LLM_REQUESTS.labels(self.provider_name(), "ok").inc()
                return response.json(), attempts
            if response.status_code in _RETRYABLE_STATUS:
                if attempts > self.max_retries:
                    LLM_REQUESTS.labels(self.provider_name(), "transient_error").inc()
                    raise ProviderTransientError(f"LLM provider returned {response.status_code}")
                LLM_RETRIES.labels(self.provider_name(), str(response.status_code)).inc()
                self._sleep(attempts, response.headers.get("retry-after"))
                continue
            LLM_REQUESTS.labels(self.provider_name(), "permanent_error").inc()
            code = "LLM_AUTH_FAILED" if response.status_code in (401, 403) else "LLM_REQUEST_REJECTED"
            raise ProviderPermanentError(f"LLM provider returned {response.status_code}", code=code)

    def _sleep(self, attempt: int, retry_after: str | None) -> None:
        delay = min(30.0, 2 ** (attempt - 1)) + random.random()
        if retry_after:
            try:
                delay = max(delay, min(60.0, float(retry_after)))
            except ValueError:
                pass
        time.sleep(delay)

    def _complete(self, system: str, user: str, model: type[BaseModel], name: str) -> tuple[BaseModel, dict[str, Any], int, str]:
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": self._format(model, name),
        }
        total_attempts = 0
        usage: dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0}
        last_error: str | None = None
        for repair in range(2):
            with _concurrency_slot(self.max_concurrency):
                payload, attempts = self._post(body)
            total_attempts += attempts
            for key in ("prompt_tokens", "completion_tokens"):
                usage[key] += int((payload.get("usage") or {}).get(key, 0) or 0)
            content = (payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            try:
                parsed = model.model_validate(json.loads(content))
                return parsed, usage, total_attempts, content
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = type(exc).__name__
                logger.warning("llm_schema_invalid", extra={"repair_attempt": repair, "error_type": last_error})
                body["messages"] = [
                    *body["messages"][:2],
                    {"role": "assistant", "content": content[:4000]},
                    {
                        "role": "user",
                        "content": "That output did not match the JSON schema. Return only valid JSON matching the schema.",
                    },
                ]
        raise ProviderSchemaError(f"LLM output failed schema validation ({last_error})")

    def _record_usage(self, usage: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        LLM_TOKENS.labels(self.provider_name(), "prompt").inc(usage.get("prompt_tokens", 0))
        LLM_TOKENS.labels(self.provider_name(), "completion").inc(usage.get("completion_tokens", 0))
        if settings.llm_cost_per_1k_input_tokens is not None and settings.llm_cost_per_1k_output_tokens is not None:
            cost = (
                Decimal(usage.get("prompt_tokens", 0)) / 1000 * settings.llm_cost_per_1k_input_tokens
                + Decimal(usage.get("completion_tokens", 0)) / 1000 * settings.llm_cost_per_1k_output_tokens
            )
            usage["estimated_cost"] = str(cost.quantize(Decimal("0.000001")))
        return usage

    def extract_invoice(self, request: ExtractionRequest) -> ProviderResult:
        started = time.perf_counter()
        user = INVOICE_USER_TEMPLATE.format(method=request.text_method, document_text=request.document_text)
        parsed, usage, attempts, content = self._complete(INVOICE_SYSTEM_PROMPT, user, RawExtraction, "invoice_extraction")
        assert isinstance(parsed, RawExtraction)
        usage["input_chars"] = len(request.document_text)
        return ProviderResult(
            extraction=parsed,
            model=self.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            attempts=attempts,
            usage=self._record_usage(usage),
            raw_response=content,
        )

    def classify_document(self, text: str) -> ClassificationResponse:
        user = CLASSIFY_USER_TEMPLATE.format(document_text=text[:6000])
        parsed, usage, _, _ = self._complete(CLASSIFY_SYSTEM_PROMPT, user, RawClassification, "document_classification")
        assert isinstance(parsed, RawClassification)
        return ClassificationResponse(classification=parsed, model=self.model, usage=self._record_usage(usage))
