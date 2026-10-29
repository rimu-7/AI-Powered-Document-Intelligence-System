"""Embedding providers.

* ``local-hash-v1``: deterministic feature-hashing embedding (word unigrams,
  bigrams, character trigrams → signed hashed buckets, L2-normalised). It needs
  no network or model download and captures lexical similarity only; it is NOT
  a semantic model. It exists for offline development and tests.
* ``hosted``: OpenAI-compatible ``/embeddings`` endpoint (e.g. ``mistral-embed``,
  1024 dimensions).

Vectors from different models are never mixed: every chunk stores its
``embedding_model`` and queries filter on it.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.exceptions import PermanentProcessingError, TransientProcessingError
from app.modules.documents.models import EMBEDDING_DIMENSIONS
from app.shared.text import fold

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingProvider(Protocol):
    model: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbeddingProvider:
    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS, model: str = "local-hash-v1") -> None:
        self.dimensions = dimensions
        self.model = model

    def _features(self, text: str) -> dict[str, float]:
        tokens = _TOKEN_RE.findall(fold(text))
        feats: dict[str, float] = {}
        for tok in tokens:
            feats[f"w:{tok}"] = feats.get(f"w:{tok}", 0.0) + 1.0
            if len(tok) >= 4:
                padded = f"^{tok}$"
                for i in range(len(padded) - 2):
                    key = f"c:{padded[i : i + 3]}"
                    feats[key] = feats.get(key, 0.0) + 0.3
        for a, b in zip(tokens, tokens[1:], strict=False):
            feats[f"b:{a}_{b}"] = feats.get(f"b:{a}_{b}", 0.0) + 0.7
        return feats

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dimensions
            for feat, weight in self._features(text).items():
                digest = hashlib.blake2b(feat.encode(), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "little") % self.dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                vec[idx] += sign * (1.0 + math.log(weight)) if weight >= 1 else sign * weight
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class HostedEmbeddingProvider:
    def __init__(self, base_url: str, api_key: str, model: str, dimensions: int, timeout: float) -> None:
        self.model = model
        self.dimensions = dimensions
        self._url = base_url.rstrip("/") + "/embeddings"
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        for attempt in range(1, 5):
            try:
                response = self._client.post(self._url, json={"model": self.model, "input": texts})
            except httpx.HTTPError as exc:
                if attempt == 4:
                    raise TransientProcessingError("Embedding request failed", code="EMBEDDING_UNAVAILABLE") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 200:
                data = sorted(response.json()["data"], key=lambda d: d["index"])
                vectors = [d["embedding"] for d in data]
                if any(len(v) != self.dimensions for v in vectors):
                    raise PermanentProcessingError("Embedding dimension mismatch", code="EMBEDDING_DIMENSION_MISMATCH")
                return vectors
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2**attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504):
                raise TransientProcessingError(f"Embedding provider returned {response.status_code}", code="EMBEDDING_UNAVAILABLE")
            raise PermanentProcessingError(f"Embedding provider returned {response.status_code}", code="EMBEDDING_REJECTED")
        raise TransientProcessingError("Embedding request failed", code="EMBEDDING_UNAVAILABLE")


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise PermanentProcessingError(
            f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions} does not match the database column ({EMBEDDING_DIMENSIONS})",
            code="EMBEDDING_DIMENSION_MISMATCH",
        )
    if settings.embedding_provider == "hosted":
        if not settings.llm_api_key:
            raise PermanentProcessingError("Embedding API key missing", code="EMBEDDING_NOT_CONFIGURED")
        return HostedEmbeddingProvider(
            base_url=settings.embedding_base_url or settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            timeout=settings.llm_timeout_seconds,
        )
    return HashingEmbeddingProvider(settings.embedding_dimensions, settings.embedding_model)
