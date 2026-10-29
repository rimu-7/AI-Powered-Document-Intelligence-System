"""Hosted LLM adapter: structured output, retry policy, schema repair (mocked HTTP)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.modules.extraction.providers.base import (
    ExtractionRequest,
    ProviderPermanentError,
    ProviderSchemaError,
    ProviderTransientError,
)
from app.modules.extraction.providers.hosted import HostedLLMProvider
from app.modules.extraction.schemas import RawExtraction, empty_invoice, strict_json_schema


def _valid_content() -> str:
    inv = empty_invoice()
    inv.invoice_number.value = "INV-9"
    inv.total_amount.value = "12.50"
    return RawExtraction(invoices=[inv]).model_dump_json()


def _completion(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}


def provider(handler: Any, **kw: Any) -> HostedLLMProvider:
    return HostedLLMProvider(
        base_url="https://llm.test/v1",
        api_key="sk-test",
        model="test-model",
        timeout=5,
        max_retries=kw.get("max_retries", 2),
        response_format="json_schema",
        max_concurrency=4,
        transport=httpx.MockTransport(handler),
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.modules.extraction.providers.hosted.time.sleep", lambda *_: None)
    monkeypatch.setattr("app.modules.extraction.providers.hosted._concurrency_slot", _null_slot)


from contextlib import contextmanager  # noqa: E402


@contextmanager
def _null_slot(*_: Any, **__: Any) -> Any:
    yield


def test_strict_schema_is_closed_and_fully_required() -> None:
    schema = strict_json_schema(RawExtraction)
    assert "$defs" not in json.dumps(schema)
    inv = schema["properties"]["invoices"]["items"]
    assert inv["additionalProperties"] is False
    assert set(inv["required"]) == set(inv["properties"])
    assert inv["properties"]["total_amount"]["properties"]["value"]["type"] == ["string", "null"]


def test_success_sends_schema_and_records_usage() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.update(body)
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(200, json=_completion(_valid_content()))

    result = provider(handler).extract_invoice(ExtractionRequest("Invoice INV-9 total 12.50", "native"))
    assert result.extraction.invoices[0].invoice_number.value == "INV-9"
    assert seen["response_format"]["type"] == "json_schema" and seen["temperature"] == 0
    assert "untrusted DATA" in seen["messages"][0]["content"]
    assert "<<<DOCUMENT_START>>>" in seen["messages"][1]["content"]
    assert result.usage["prompt_tokens"] == 100


def test_retries_transient_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        if calls["n"] == 2:
            return httpx.Response(503)
        return httpx.Response(200, json=_completion(_valid_content()))

    result = provider(handler).extract_invoice(ExtractionRequest("x", "native"))
    assert calls["n"] == 3 and result.attempts == 3


def test_transient_errors_exhaust_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderTransientError):
        provider(handler, max_retries=1).extract_invoice(ExtractionRequest("x", "native"))


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_permanent_errors_are_not_retried(status: int) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status, json={"error": "nope"})

    with pytest.raises(ProviderPermanentError):
        provider(handler).extract_invoice(ExtractionRequest("x", "native"))
    assert calls["n"] == 1


def test_schema_invalid_output_is_repaired_once_then_fails() -> None:
    responses = [_completion('{"invoices": [{"total": 5}]}'), _completion(_valid_content())]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    result = provider(handler).extract_invoice(ExtractionRequest("x", "native"))
    assert result.extraction.invoices[0].total_amount.value == "12.50"

    def always_bad(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion("not json at all"))

    with pytest.raises(ProviderSchemaError):
        provider(always_bad).extract_invoice(ExtractionRequest("x", "native"))
