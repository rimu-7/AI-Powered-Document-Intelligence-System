"""UploadThing storage for original files (raw, unmodified bytes).

API behaviour this client relies on (verified against the live service):

* ``POST {api}/v7/prepareUpload`` with ``x-uploadthing-api-key`` returns
  ``{"key", "url"}``; ``url`` is a signed ingest URL valid for ``expiresIn``.
* The ingest URL accepts ``PUT`` with **multipart/form-data** (field ``file``);
  it rejects bodies larger than the declared ``fileSize`` (413).
* Files are addressable by ``customId``: ``https://{appId}.ufs.sh/f/{customId}``.
  We always set ``customId`` to our own storage key, so the database never
  depends on UploadThing's generated key.
* ``POST {api}/v6/deleteFiles`` accepts ``{"customIds": [...]}``.
* Free apps only allow ``acl=public-read`` (URL is unguessable but public);
  ``private`` needs a paid app and ``POST /v6/requestFileAccess`` for reads.
* After deletion the CDN may keep serving a cached copy for a while.
"""

from __future__ import annotations

import base64
import json
import random
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import IO, Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import PermanentProcessingError, TransientProcessingError
from app.core.logging import get_logger

logger = get_logger(__name__)

UPLOADTHING_BUCKET = "uploadthing"  # sentinel "bucket" used in storage_objects and routing
_RETRYABLE = {408, 425, 429, 500, 502, 503, 504}


class UploadThingUnavailableError(TransientProcessingError):
    code = "UPLOADTHING_UNAVAILABLE"


class UploadThingError(PermanentProcessingError):
    code = "UPLOADTHING_ERROR"


@dataclass(frozen=True)
class UploadThingCredentials:
    api_key: str
    app_id: str
    regions: tuple[str, ...]

    @classmethod
    def from_token(cls, token: str) -> UploadThingCredentials:
        try:
            data = json.loads(base64.b64decode(token))
            return cls(api_key=data["apiKey"], app_id=data["appId"], regions=tuple(data.get("regions", [])))
        except (ValueError, KeyError, TypeError) as exc:
            raise UploadThingError("UPLOADTHING_TOKEN is not a valid UploadThing token", code="UPLOADTHING_BAD_TOKEN") from exc


@dataclass(frozen=True)
class PreparedUpload:
    key: str
    url: str
    custom_id: str
    expires_at: float


class UploadThingClient:
    def __init__(
        self,
        credentials: UploadThingCredentials,
        *,
        api_url: str = "https://api.uploadthing.com",
        acl: str = "public-read",
        timeout: float = 120.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.credentials = credentials
        self.api_url = api_url.rstrip("/")
        self.acl = acl
        self.max_retries = max_retries
        self._http = httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0), transport=transport, follow_redirects=True)
        self._health_cache: tuple[float, bool] | None = None

    # -- low level ---------------------------------------------------------------

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        rewind = kwargs.pop("rewind", None)
        for attempt in range(1, self.max_retries + 2):
            if rewind is not None:
                rewind.seek(0)
            try:
                response = self._http.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt > self.max_retries:
                    raise UploadThingUnavailableError(f"UploadThing unreachable: {type(exc).__name__}") from exc
                self._sleep(attempt, None)
                continue
            if response.status_code in _RETRYABLE and attempt <= self.max_retries:
                self._sleep(attempt, response.headers.get("retry-after"))
                continue
            if response.status_code in _RETRYABLE:
                raise UploadThingUnavailableError(f"UploadThing returned {response.status_code}")
            return response
        raise UploadThingUnavailableError("UploadThing request failed")

    @staticmethod
    def _sleep(attempt: int, retry_after: str | None) -> None:
        delay = min(20.0, 2 ** (attempt - 1)) + random.random()
        if retry_after:
            try:
                delay = max(delay, min(60.0, float(retry_after)))
            except ValueError:
                pass
        time.sleep(delay)

    def _api(self, path: str, payload: dict[str, Any]) -> Any:
        response = self._request(
            "POST",
            f"{self.api_url}{path}",
            json=payload,
            headers={"x-uploadthing-api-key": self.credentials.api_key},
        )
        if response.status_code in (401, 403):
            raise UploadThingError("UploadThing rejected the API key", code="UPLOADTHING_AUTH_FAILED")
        if response.status_code >= 400:
            raise UploadThingError(f"UploadThing {path} failed with {response.status_code}: {_error_text(response)}")
        return response.json()

    # -- operations ----------------------------------------------------------------

    def file_url(self, custom_id: str) -> str:
        return f"https://{self.credentials.app_id}.ufs.sh/f/{custom_id}"

    def prepare_upload(self, custom_id: str, filename: str, size: int, content_type: str, expires_in: int = 3600) -> PreparedUpload:
        data = self._api(
            "/v7/prepareUpload",
            {
                "fileName": filename,
                "fileSize": size,
                "fileType": content_type,
                "customId": custom_id,
                "contentDisposition": "attachment",
                "acl": self.acl,
                "expiresIn": expires_in,
            },
        )
        return PreparedUpload(key=data["key"], url=data["url"], custom_id=custom_id, expires_at=time.time() + expires_in)

    def put(self, prepared: PreparedUpload, fileobj: IO[bytes], filename: str, content_type: str) -> dict[str, Any]:
        """Stream the file to the signed ingest URL (multipart, chunked from disk)."""
        response = self._request(
            "PUT",
            prepared.url,
            files={"file": (filename, fileobj, content_type)},
            rewind=fileobj,
        )
        if response.status_code == 413:
            raise UploadThingError("File is larger than the size declared for this upload", code="UPLOAD_SIZE_MISMATCH")
        if response.status_code >= 400:
            raise UploadThingError(f"UploadThing ingest failed with {response.status_code}: {_error_text(response)}")
        return dict(response.json())

    def upload(self, fileobj: IO[bytes], custom_id: str, filename: str, content_type: str) -> dict[str, Any]:
        fileobj.seek(0, 2)
        size = fileobj.tell()
        fileobj.seek(0)
        prepared = self.prepare_upload(custom_id, filename, size, content_type)
        return self.put(prepared, fileobj, filename, content_type)

    def _read_url(self, custom_id: str) -> str:
        if self.acl == "private":
            data = self._api("/v6/requestFileAccess", {"customId": custom_id, "expiresIn": 300})
            return str(data.get("ufsUrl") or data["url"])
        return self.file_url(custom_id)

    def download_to_file(self, custom_id: str, path: str) -> None:
        url = self._read_url(custom_id)
        for attempt in range(1, self.max_retries + 2):
            try:
                with self._http.stream("GET", url) as response:
                    if response.status_code == 404:
                        raise UploadThingError("File not found in UploadThing", code="STORAGE_OBJECT_MISSING")
                    if response.status_code in _RETRYABLE and attempt <= self.max_retries:
                        self._sleep(attempt, response.headers.get("retry-after"))
                        continue
                    if response.status_code >= 400:
                        raise UploadThingUnavailableError(f"UploadThing download failed with {response.status_code}")
                    with open(path, "wb") as fh:
                        for chunk in response.iter_bytes(1024 * 1024):
                            fh.write(chunk)
                    return
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt > self.max_retries:
                    raise UploadThingUnavailableError(f"UploadThing download failed: {type(exc).__name__}") from exc
                self._sleep(attempt, None)
        raise UploadThingUnavailableError("UploadThing download failed")

    def iter_object(self, custom_id: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        url = self._read_url(custom_id)
        try:
            with self._http.stream("GET", url) as response:
                if response.status_code == 404:
                    raise UploadThingError("File not found in UploadThing", code="STORAGE_OBJECT_MISSING")
                if response.status_code >= 400:
                    raise UploadThingUnavailableError(f"UploadThing download failed with {response.status_code}")
                yield from response.iter_bytes(chunk_size)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise UploadThingUnavailableError(f"UploadThing download failed: {type(exc).__name__}") from exc

    def delete(self, custom_ids: list[str]) -> int:
        if not custom_ids:
            return 0
        data = self._api("/v6/deleteFiles", {"customIds": custom_ids})
        return int(data.get("deletedCount", 0))

    def signed_read_url(self, custom_id: str, ttl: int) -> str:
        if self.acl != "private":
            raise UploadThingError(
                "Short-lived download links need UPLOADTHING_ACL=private (paid app); use mode=stream",
                code="PRESIGNED_UNAVAILABLE",
            )
        data = self._api("/v6/requestFileAccess", {"customId": custom_id, "expiresIn": ttl})
        return str(data.get("ufsUrl") or data["url"])

    def healthcheck(self) -> bool:
        now = time.monotonic()
        if self._health_cache and now - self._health_cache[0] < 30:
            return self._health_cache[1]
        try:
            self._api("/v6/listFiles", {"limit": 1})
            ok = True
        except (UploadThingError, UploadThingUnavailableError):
            ok = False
        self._health_cache = (now, ok)
        return ok


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
        return str(body.get("error") or body.get("message") or body)[:200]
    except ValueError:
        return response.text[:200]


_client: UploadThingClient | None = None


def get_uploadthing() -> UploadThingClient:
    global _client
    if _client is None:
        settings = get_settings()
        if settings.uploadthing_token is None:
            raise UploadThingError("UPLOADTHING_TOKEN is not configured", code="UPLOADTHING_NOT_CONFIGURED")
        _client = UploadThingClient(
            UploadThingCredentials.from_token(settings.uploadthing_token.get_secret_value()),
            api_url=settings.uploadthing_api_url,
            acl=settings.uploadthing_acl,
            timeout=settings.uploadthing_timeout_seconds,
            max_retries=settings.uploadthing_max_retries,
        )
    return _client


def reset_uploadthing() -> None:
    global _client
    _client = None
