"""S3-compatible object storage (MinIO locally, S3 in production).

Keys are generated server-side and never derived from user input. Tenant
prefixes organise objects but are not used as an authorization mechanism.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from functools import lru_cache
from typing import IO, Any

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

from app.core.config import get_settings
from app.core.exceptions import TransientProcessingError
from app.core.logging import get_logger
from app.modules.documents.uploadthing import UPLOADTHING_BUCKET, UploadThingError, get_uploadthing
from app.shared.enums import StorageCategory

logger = get_logger(__name__)

_TRANSFER = TransferConfig(
    multipart_threshold=16 * 1024 * 1024,
    multipart_chunksize=16 * 1024 * 1024,
    max_concurrency=4,
    use_threads=True,
)

_PREFIX = {
    StorageCategory.ORIGINAL: "originals",
    StorageCategory.PAGE_LAYOUT: "derived/layout",
    StorageCategory.PAGE_TEXT: "derived/text",
    StorageCategory.OCR_RESULT: "derived/ocr",
    StorageCategory.EXTRACTION_RAW: "derived/extraction",
    StorageCategory.TABLE_DATA: "derived/tables",
    StorageCategory.EXPORT: "exports",
}


class StorageUnavailableError(TransientProcessingError):
    code = "STORAGE_UNAVAILABLE"


def _uploadthing_originals() -> bool:
    return get_settings().originals_storage == "uploadthing"


def bucket_for(category: StorageCategory) -> str:
    """Where *new* objects of this category go."""
    settings = get_settings()
    if category == StorageCategory.ORIGINAL:
        return UPLOADTHING_BUCKET if _uploadthing_originals() else settings.s3_bucket_originals
    return settings.s3_bucket_artifacts


def original_bucket(storage_key: str) -> str:
    """Where an *existing* original lives. UploadThing keys never contain '/',
    S3 keys always do, so documents keep working after switching backends."""
    return get_settings().s3_bucket_originals if "/" in storage_key else UPLOADTHING_BUCKET


def make_key(category: StorageCategory, organization_id: uuid.UUID, document_id: uuid.UUID | None, suffix: str = "") -> str:
    if category == StorageCategory.ORIGINAL and _uploadthing_originals():
        # Used as the UploadThing customId: tenant-scoped, unguessable, no '/'.
        doc_hex = document_id.hex if document_id else "0"
        return f"o{organization_id.hex}-d{doc_hex}-{uuid.uuid4().hex}{suffix}"
    doc = str(document_id) if document_id else "_"
    return f"{_PREFIX[category]}/{organization_id}/{doc}/{uuid.uuid4().hex}{suffix}"


def _credentials() -> dict[str, Any]:
    settings = get_settings()
    creds: dict[str, Any] = {}
    if settings.s3_access_key_id and settings.s3_secret_access_key:
        creds["aws_access_key_id"] = settings.s3_access_key_id.get_secret_value()
        creds["aws_secret_access_key"] = settings.s3_secret_access_key.get_secret_value()
    return creds


@lru_cache(maxsize=2)
def _client(public: bool = False) -> Any:
    settings = get_settings()
    endpoint = settings.s3_public_endpoint_url if public and settings.s3_public_endpoint_url else settings.s3_endpoint_url
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=settings.s3_region,
        config=Config(
            connect_timeout=settings.s3_connect_timeout_seconds,
            read_timeout=settings.s3_read_timeout_seconds,
            retries={"max_attempts": 3, "mode": "standard"},
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
        **_credentials(),
    )


def _extra_args() -> dict[str, str]:
    sse = get_settings().s3_server_side_encryption
    return {"ServerSideEncryption": sse} if sse else {}


def _wrap(exc: Exception) -> Exception:
    if isinstance(exc, EndpointConnectionError | BotoCoreError):
        return StorageUnavailableError(f"Object storage unavailable: {type(exc).__name__}")
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("SlowDown", "ServiceUnavailable", "InternalError", "RequestTimeout", "503", "500"):
            return StorageUnavailableError(f"Object storage error: {code}")
    return exc


class ObjectStorage:
    def upload_fileobj(self, fileobj: IO[bytes], bucket: str, key: str, content_type: str, filename: str | None = None) -> None:
        try:
            _client().upload_fileobj(
                fileobj,
                bucket,
                key,
                ExtraArgs={"ContentType": content_type, **_extra_args()},
                Config=_TRANSFER,
            )
        except Exception as exc:
            raise _wrap(exc) from exc

    def put_bytes(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        try:
            _client().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type, **_extra_args())
        except Exception as exc:
            raise _wrap(exc) from exc

    def put_json(self, bucket: str, key: str, payload: Any) -> None:
        self.put_bytes(bucket, key, json.dumps(payload, default=str).encode(), "application/json")

    def get_bytes(self, bucket: str, key: str) -> bytes:
        try:
            body = _client().get_object(Bucket=bucket, Key=key)["Body"]
            return bytes(body.read())
        except Exception as exc:
            raise _wrap(exc) from exc

    def get_json(self, bucket: str, key: str) -> Any:
        return json.loads(self.get_bytes(bucket, key))

    def download_to_file(self, bucket: str, key: str, path: str) -> None:
        try:
            _client().download_file(bucket, key, path, Config=_TRANSFER)
        except Exception as exc:
            raise _wrap(exc) from exc

    def iter_object(self, bucket: str, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        try:
            body = _client().get_object(Bucket=bucket, Key=key)["Body"]
        except Exception as exc:
            raise _wrap(exc) from exc
        try:
            yield from body.iter_chunks(chunk_size)
        finally:
            body.close()

    def delete(self, bucket: str, key: str) -> None:
        try:
            _client().delete_object(Bucket=bucket, Key=key)
        except Exception as exc:
            raise _wrap(exc) from exc

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        """Delete every object under ``prefix`` (S3 buckets only). Returns the count."""
        deleted = 0
        try:
            paginator = _client().get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if keys:
                    _client().delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})
                    deleted += len(keys)
        except Exception as exc:
            raise _wrap(exc) from exc
        return deleted

    def presigned_get(self, bucket: str, key: str, filename: str, ttl: int) -> str:
        return str(
            _client(public=True).generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket,
                    "Key": key,
                    "ResponseContentDisposition": f'attachment; filename="{filename}"',
                },
                ExpiresIn=ttl,
            )
        )

    def healthcheck(self) -> bool:
        settings = get_settings()
        _client().head_bucket(Bucket=settings.s3_bucket_artifacts)
        if _uploadthing_originals():
            return get_uploadthing().healthcheck()
        _client().head_bucket(Bucket=settings.s3_bucket_originals)
        return True

    def ensure_buckets(self) -> None:
        settings = get_settings()
        client = _client()
        for bucket in {settings.s3_bucket_originals, settings.s3_bucket_artifacts}:
            try:
                client.head_bucket(Bucket=bucket)
            except ClientError:
                client.create_bucket(Bucket=bucket)
                logger.info("bucket_created", extra={"bucket": bucket})
            # Block any public access policy: objects are only reachable
            # through authenticated API calls or short-lived presigned URLs.
            try:
                client.delete_bucket_policy(Bucket=bucket)
            except ClientError:
                pass


class RoutingStorage(ObjectStorage):
    """S3/MinIO for everything, except objects in the UploadThing pseudo-bucket."""

    def upload_fileobj(self, fileobj: IO[bytes], bucket: str, key: str, content_type: str, filename: str | None = None) -> None:
        if bucket == UPLOADTHING_BUCKET:
            get_uploadthing().upload(fileobj, key, filename or key, content_type)
            return
        super().upload_fileobj(fileobj, bucket, key, content_type)

    def download_to_file(self, bucket: str, key: str, path: str) -> None:
        if bucket == UPLOADTHING_BUCKET:
            get_uploadthing().download_to_file(key, path)
            return
        super().download_to_file(bucket, key, path)

    def iter_object(self, bucket: str, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        if bucket == UPLOADTHING_BUCKET:
            return get_uploadthing().iter_object(key, chunk_size)
        return super().iter_object(bucket, key, chunk_size)

    def delete(self, bucket: str, key: str) -> None:
        if bucket == UPLOADTHING_BUCKET:
            get_uploadthing().delete([key])
            return
        super().delete(bucket, key)

    def presigned_get(self, bucket: str, key: str, filename: str, ttl: int) -> str:
        if bucket == UPLOADTHING_BUCKET:
            return get_uploadthing().signed_read_url(key, ttl)
        return super().presigned_get(bucket, key, filename, ttl)

    def get_bytes(self, bucket: str, key: str) -> bytes:
        if bucket == UPLOADTHING_BUCKET:
            return b"".join(get_uploadthing().iter_object(key))
        return super().get_bytes(bucket, key)

    def put_bytes(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        if bucket == UPLOADTHING_BUCKET:
            raise UploadThingError("Only original files are stored in UploadThing")
        super().put_bytes(bucket, key, data, content_type)


@lru_cache(maxsize=1)
def get_storage() -> ObjectStorage:
    return RoutingStorage()
