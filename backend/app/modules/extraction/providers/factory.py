from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.core.exceptions import PermanentProcessingError
from app.modules.extraction.providers.base import ExtractionProvider
from app.modules.extraction.providers.fixture import LocalRulesProvider
from app.modules.extraction.providers.hosted import HostedLLMProvider


@lru_cache(maxsize=1)
def get_extraction_provider() -> ExtractionProvider:
    settings = get_settings()
    if settings.extraction_provider == "hosted":
        if not settings.ai_external_transmission_enabled:
            raise PermanentProcessingError("External AI transmission is disabled", code="AI_TRANSMISSION_DISABLED")
        if settings.llm_api_key is None:
            raise PermanentProcessingError("LLM_API_KEY is not configured", code="LLM_NOT_CONFIGURED")
        return HostedLLMProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            response_format=settings.llm_response_format,
            max_concurrency=settings.llm_max_concurrency,
        )
    return LocalRulesProvider()
