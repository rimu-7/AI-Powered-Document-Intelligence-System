from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.exceptions import PermanentProcessingError, TransientProcessingError
from app.modules.extraction.schemas import RawClassification, RawExtraction


@dataclass
class ExtractionRequest:
    document_text: str
    text_method: str  # "native PDF text extraction", "OCR", ...
    document_type_hint: str | None = None


@dataclass
class ProviderResult:
    extraction: RawExtraction
    model: str
    latency_ms: int
    attempts: int = 1
    usage: dict[str, Any] = field(default_factory=dict)
    raw_response: str | None = None


@dataclass
class ClassificationResponse:
    classification: RawClassification
    model: str
    usage: dict[str, Any] = field(default_factory=dict)


class ProviderTransientError(TransientProcessingError):
    code = "LLM_TRANSIENT"


class ProviderPermanentError(PermanentProcessingError):
    code = "LLM_PERMANENT"


class ProviderSchemaError(PermanentProcessingError):
    code = "LLM_SCHEMA_INVALID"


class ExtractionProvider(Protocol):
    def extract_invoice(self, request: ExtractionRequest) -> ProviderResult: ...

    def classify_document(self, text: str) -> ClassificationResponse: ...

    def provider_name(self) -> str: ...

    def model_name(self) -> str: ...

    def healthcheck(self) -> bool: ...
