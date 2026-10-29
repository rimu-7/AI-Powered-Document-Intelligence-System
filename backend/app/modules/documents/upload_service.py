"""Secure multi-file upload.

Per file: size limit → content-signature check (extension must match bytes)
→ SHA-256 (streamed) → archive/macro checks (XLSX) → quota reservation under
an organization row lock → streamed multipart upload to object storage →
document + processing run + first task + outbox event in one transaction.
An interrupted upload leaves a PENDING storage object that maintenance removes.
"""

from __future__ import annotations

import functools
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import IO

import anyio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.api.deps import Principal
from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.modules.auditing.service import record_audit
from app.modules.documents.fingerprint import (
    _EXT_SIGNATURE as _EXT_TO_SIGNATURE,
)
from app.modules.documents.fingerprint import (
    ALLOWED_EXTENSIONS,
    CONTENT_TYPES,
    FileIdentity,
    FileRejected,
    check_office_archive,
    identify,
    sha256_stream,
)
from app.modules.documents.models import Document, StorageObject
from app.modules.documents.schemas import UploadError, UploadResult
from app.modules.documents.storage import bucket_for, get_storage, make_key
from app.modules.documents.uploadthing import UPLOADTHING_BUCKET, UploadThingError, get_uploadthing
from app.modules.identity.models import Organization
from app.modules.jobs.models import ProcessingRun
from app.modules.jobs.outbox import new_task_with_event
from app.shared.enums import (
    DocumentStatus,
    FileKind,
    JobType,
    RunState,
    ScanStatus,
    StorageCategory,
    StorageObjectStatus,
    TaskType,
)
from app.shared.text import safe_display_filename

logger = get_logger(__name__)


async def _quota_reserve(
    session: AsyncSession,
    principal: Principal,
    doc_id: uuid.UUID,
    bucket: str,
    key: str,
    size: int,
    *,
    original_filename: str | None = None,
    metadata: dict[str, object] | None = None,
) -> uuid.UUID:
    settings = get_settings()
    org = (await session.execute(select(Organization).where(Organization.id == principal.organization_id).with_for_update())).scalar_one()
    quota = org.storage_quota_bytes or settings.org_storage_quota_bytes
    used_docs = (
        await session.execute(
            select(func.coalesce(func.sum(Document.file_size_bytes), 0)).where(
                Document.organization_id == org.id, Document.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    pending = (
        await session.execute(
            select(func.coalesce(func.sum(StorageObject.size_bytes), 0)).where(
                StorageObject.organization_id == org.id,
                StorageObject.status == StorageObjectStatus.PENDING,
                StorageObject.category == StorageCategory.ORIGINAL,
            )
        )
    ).scalar_one()
    if int(used_docs or 0) + int(pending or 0) + size > quota:
        await session.rollback()
        raise FileRejected("STORAGE_QUOTA_EXCEEDED", "Organization storage quota exceeded")
    obj = StorageObject(
        id=uuid.uuid4(),
        organization_id=org.id,
        document_id=doc_id,
        category=StorageCategory.ORIGINAL,
        bucket=bucket,
        key=key,
        size_bytes=size,
        status=StorageObjectStatus.PENDING,
        original_filename=original_filename,
        metadata_json=metadata or {},
    )
    session.add(obj)
    await session.commit()
    return obj.id


def _validate_file(fileobj: IO[bytes], display_name: str, size_hint: int | None) -> tuple[FileIdentity, str, int]:
    """Signature, size, SHA-256 and archive checks. Raises FileRejected. Sync (run in a thread)."""
    settings = get_settings()
    if size_hint is not None and size_hint > settings.upload_max_file_bytes:
        raise FileRejected("FILE_TOO_LARGE", f"File exceeds the {settings.upload_max_file_bytes} byte limit")
    fileobj.seek(0)
    head = fileobj.read(8192)
    fileobj.seek(0)
    if not head:
        raise FileRejected("EMPTY_FILE", "File is empty")
    identity = identify(display_name, head)
    digest, measured = sha256_stream(fileobj)
    if measured > settings.upload_max_file_bytes:
        raise FileRejected("FILE_TOO_LARGE", f"File exceeds the {settings.upload_max_file_bytes} byte limit")
    if identity.kind == FileKind.XLSX:
        check_office_archive(fileobj, settings)
    fileobj.seek(0)
    return identity, digest, measured


async def _duplicates(session: AsyncSession, principal: Principal, digest: str) -> list[uuid.UUID]:
    rows = list(
        (
            await session.execute(
                select(Document.id)
                .where(Document.organization_id == principal.organization_id, Document.sha256 == digest, Document.deleted_at.is_(None))
                .limit(10)
            )
        ).scalars()
    )
    await session.commit()
    return rows


def _rejected(display_name: str, code: str, message: str, **kw: object) -> UploadResult:
    return UploadResult(filename=display_name, status="rejected", error=UploadError(code=code, message=message), **kw)  # type: ignore[arg-type]


async def _discard_object(session: AsyncSession, storage_obj_id: uuid.UUID, *, remote: bool) -> None:
    obj = await session.get(StorageObject, storage_obj_id)
    if obj is None:
        return
    if remote:
        try:
            await anyio.to_thread.run_sync(get_storage().delete, obj.bucket, obj.key)
        except Exception:  # noqa: BLE001 - maintenance retries PENDING objects later
            logger.warning("discard_object_failed")
            await session.commit()
            return
    obj.status = StorageObjectStatus.DELETED
    obj.deleted_at = datetime.now(UTC)
    await session.commit()


async def _register_document(
    session: AsyncSession,
    principal: Principal,
    *,
    doc_id: uuid.UUID,
    storage_obj_id: uuid.UUID,
    bucket: str,
    key: str,
    display_name: str,
    identity: FileIdentity,
    digest: str,
    measured: int,
    client_content_type: str | None,
    duplicates: list[uuid.UUID],
    via: str,
) -> UploadResult:
    """Document + processing run + first task + outbox event, in one transaction."""
    document = Document(
        id=doc_id,
        organization_id=principal.organization_id,
        uploaded_by=principal.user_id,
        original_filename=display_name,
        content_type=identity.content_type,
        file_extension=identity.extension,
        file_kind=identity.kind,
        file_size_bytes=measured,
        sha256=digest,
        storage_key=key,
        status=DocumentStatus.UPLOADED,
        scan_status=ScanStatus.PENDING,
        metadata_json={
            "client_content_type": (client_content_type or "")[:120],
            "storage_backend": "uploadthing" if bucket == UPLOADTHING_BUCKET else "s3",
            "upload_method": via,
        },
    )
    run = ProcessingRun(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        document_id=doc_id,
        job_type=JobType.DOCUMENT_PROCESSING,
        state=RunState.QUEUED,
        attempt_number=1,
        created_by=principal.user_id,
        payload_json={},
        stage_history_json=[],
    )
    task, event = new_task_with_event(run, TaskType.PREPROCESS)
    try:
        session.add(document)
        await session.flush()
        session.add(run)
        await session.flush()
        document.current_processing_run_id = run.id
        session.add_all([task, event])
        obj = await session.get(StorageObject, storage_obj_id)
        if obj is not None:
            obj.status = StorageObjectStatus.ACTIVE
            obj.size_bytes = measured
        record_audit(
            session,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            action="document.uploaded",
            resource_type="document",
            resource_id=doc_id,
            metadata={"file_kind": identity.kind.value, "size": measured, "duplicate": bool(duplicates), "via": via},
        )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("upload_db_commit_failed")
        # Best-effort immediate cleanup; maintenance also removes PENDING objects.
        await _discard_object(session, storage_obj_id, remote=True)
        return _rejected(display_name, "UPLOAD_FAILED", "Upload could not be recorded; retry later")
    return UploadResult(
        filename=display_name,
        status="accepted",
        document_id=doc_id,
        job_id=run.id,
        status_url=f"/api/v1/jobs/{run.id}",
        sha256=digest,
        duplicate_of_document_ids=duplicates,
    )


async def _process_one(session: AsyncSession, principal: Principal, upload: UploadFile, via: str) -> UploadResult:
    settings = get_settings()
    display_name = safe_display_filename(upload.filename)
    try:
        identity, digest, measured = await anyio.to_thread.run_sync(_validate_file, upload.file, display_name, upload.size)
    except FileRejected as exc:
        return _rejected(display_name, exc.code, exc.message)

    duplicates = await _duplicates(session, principal, digest)
    if duplicates and settings.upload_duplicate_policy == "reject":
        return _rejected(
            display_name, "DUPLICATE_FILE", "An identical file already exists", sha256=digest, duplicate_of_document_ids=duplicates
        )

    doc_id = uuid.uuid4()
    bucket = bucket_for(StorageCategory.ORIGINAL)
    key = make_key(StorageCategory.ORIGINAL, principal.organization_id, doc_id, identity.extension)
    try:
        storage_obj_id = await _quota_reserve(session, principal, doc_id, bucket, key, measured, original_filename=display_name)
    except FileRejected as exc:
        return _rejected(display_name, exc.code, exc.message)

    upload.file.seek(0)
    try:
        await anyio.to_thread.run_sync(
            functools.partial(get_storage().upload_fileobj, upload.file, bucket, key, identity.content_type, filename=display_name)
        )
    except Exception as exc:
        logger.exception("upload_storage_failed", extra={"backend": bucket if bucket == UPLOADTHING_BUCKET else "s3"})
        await _discard_object(session, storage_obj_id, remote=bucket == UPLOADTHING_BUCKET)
        code = getattr(exc, "code", "STORAGE_UNAVAILABLE")
        if code not in ("UPLOADTHING_AUTH_FAILED", "UPLOAD_SIZE_MISMATCH"):
            code = "STORAGE_UNAVAILABLE"
        return _rejected(display_name, code, "Object storage is unavailable or rejected the file; retry later")

    return await _register_document(
        session,
        principal,
        doc_id=doc_id,
        storage_obj_id=storage_obj_id,
        bucket=bucket,
        key=key,
        display_name=display_name,
        identity=identity,
        digest=digest,
        measured=measured,
        client_content_type=upload.content_type,
        duplicates=duplicates,
        via=via,
    )


async def upload_documents(
    session: AsyncSession, principal: Principal, files: list[UploadFile], via: str = "multipart"
) -> list[UploadResult]:
    results = []
    for upload in files:
        try:
            results.append(await _process_one(session, principal, upload, via))
        finally:
            await upload.close()
    return results


# --- Direct upload (client → UploadThing, then confirm) ----------------------------------------


@dataclass(frozen=True)
class DirectUploadTicket:
    upload_id: uuid.UUID
    document_id: uuid.UUID
    upload_url: str
    expires_at: datetime
    max_bytes: int


async def prepare_direct_upload(session: AsyncSession, principal: Principal, filename: str, size: int) -> DirectUploadTicket:
    settings = get_settings()
    if settings.originals_storage != "uploadthing":
        raise FileRejected("DIRECT_UPLOAD_UNAVAILABLE", "Direct uploads require ORIGINALS_STORAGE=uploadthing")
    display_name = safe_display_filename(filename)
    extension = "." + display_name.lower().rsplit(".", 1)[-1] if "." in display_name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise FileRejected("UNSUPPORTED_FILE_TYPE", f"File extension '{extension or '(none)'}' is not allowed")
    if size <= 0:
        raise FileRejected("EMPTY_FILE", "File is empty")
    if size > settings.upload_max_file_bytes:
        raise FileRejected("FILE_TOO_LARGE", f"File exceeds the {settings.upload_max_file_bytes} byte limit")
    doc_id = uuid.uuid4()
    key = make_key(StorageCategory.ORIGINAL, principal.organization_id, doc_id, extension)
    ttl = settings.direct_upload_ttl_seconds
    storage_obj_id = await _quota_reserve(
        session,
        principal,
        doc_id,
        UPLOADTHING_BUCKET,
        key,
        size,
        original_filename=display_name,
        metadata={"direct_upload": True, "declared_size": size, "uploaded_by": str(principal.user_id)},
    )
    content_type = CONTENT_TYPES[_EXT_TO_SIGNATURE[extension]]
    try:
        prepared = await anyio.to_thread.run_sync(get_uploadthing().prepare_upload, key, display_name, size, content_type, ttl)
    except Exception:
        logger.exception("direct_upload_prepare_failed")
        await _discard_object(session, storage_obj_id, remote=False)
        raise FileRejected("STORAGE_UNAVAILABLE", "Upload storage is unavailable; retry later") from None
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="document.direct_upload_prepared",
        resource_type="storage_object",
        resource_id=storage_obj_id,
        metadata={"size": size, "extension": extension},
    )
    await session.commit()
    return DirectUploadTicket(
        upload_id=storage_obj_id,
        document_id=doc_id,
        upload_url=prepared.url,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
        max_bytes=size,
    )


async def complete_direct_upload(session: AsyncSession, principal: Principal, upload_id: uuid.UUID) -> UploadResult:
    """Verify the file the client sent to UploadThing and register it (idempotent)."""
    settings = get_settings()
    obj = (
        await session.execute(
            select(StorageObject).where(
                StorageObject.id == upload_id,
                StorageObject.organization_id == principal.organization_id,
                StorageObject.category == StorageCategory.ORIGINAL,
                StorageObject.bucket == UPLOADTHING_BUCKET,
            )
        )
    ).scalar_one_or_none()
    if obj is None or not (obj.metadata_json or {}).get("direct_upload"):
        raise NotFoundError("Upload not found")
    display_name = obj.original_filename or "upload"
    if obj.status == StorageObjectStatus.ACTIVE and obj.document_id:
        # Repeat call after success: return the already-registered document.
        run_id = (
            await session.execute(select(Document.current_processing_run_id).where(Document.id == obj.document_id))
        ).scalar_one_or_none()
        return UploadResult(
            filename=display_name, status="accepted", document_id=obj.document_id, job_id=run_id, status_url=f"/api/v1/jobs/{run_id}"
        )
    if obj.status != StorageObjectStatus.PENDING:
        raise ConflictError("Upload was discarded; prepare a new one", code="UPLOAD_DISCARDED")
    if obj.created_at + timedelta(seconds=settings.direct_upload_ttl_seconds + 300) < datetime.now(UTC):
        await _discard_object(session, obj.id, remote=True)
        raise ConflictError("Upload expired; prepare a new one", code="UPLOAD_EXPIRED")
    declared = int((obj.metadata_json or {}).get("declared_size", 0))
    obj_id, obj_key, doc_id = obj.id, obj.key, obj.document_id
    await session.commit()

    tmp = tempfile.NamedTemporaryFile(prefix="direct-", suffix=".bin", delete=False)  # noqa: SIM115
    tmp.close()
    try:
        try:
            await anyio.to_thread.run_sync(get_storage().download_to_file, UPLOADTHING_BUCKET, obj_key, tmp.name)
        except UploadThingError as exc:
            if exc.code == "STORAGE_OBJECT_MISSING":
                raise ConflictError("The file has not been uploaded to the upload URL yet", code="UPLOAD_NOT_RECEIVED") from exc
            raise
        with open(tmp.name, "rb") as fh:  # noqa: ASYNC230 - local temp file; reads happen in a thread
            try:
                identity, digest, measured = await anyio.to_thread.run_sync(_validate_file, fh, display_name, None)
                if measured != declared:
                    raise FileRejected("UPLOAD_SIZE_MISMATCH", f"Received {measured} bytes, declared {declared}")
            except FileRejected as exc:
                await _discard_object(session, obj_id, remote=True)
                return _rejected(display_name, exc.code, exc.message)
    finally:
        os.unlink(tmp.name)

    duplicates = await _duplicates(session, principal, digest)
    if duplicates and settings.upload_duplicate_policy == "reject":
        await _discard_object(session, obj_id, remote=True)
        return _rejected(
            display_name, "DUPLICATE_FILE", "An identical file already exists", sha256=digest, duplicate_of_document_ids=duplicates
        )
    assert doc_id is not None
    return await _register_document(
        session,
        principal,
        doc_id=doc_id,
        storage_obj_id=obj_id,
        bucket=UPLOADTHING_BUCKET,
        key=obj_key,
        display_name=display_name,
        identity=identity,
        digest=digest,
        measured=measured,
        client_content_type=identity.content_type,
        duplicates=duplicates,
        via="direct",
    )
