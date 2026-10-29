from __future__ import annotations

import tempfile
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

import anyio
from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from starlette.datastructures import UploadFile

from app.api import idempotency
from app.api.deps import Principal, SessionDep, require
from app.core.config import get_settings
from app.core.exceptions import AppError, ConflictError, NotFoundError, PayloadTooLargeError, ValidationFailedError
from app.core.permissions import Permission
from app.modules.auditing.service import record_audit
from app.modules.comparison.mapping import MappingSuggestions, suggest_mapping
from app.modules.documents import service
from app.modules.documents.fingerprint import FileRejected
from app.modules.documents.models import Document, DocumentPage, DocumentTable, SpreadsheetRow
from app.modules.documents.schemas import (
    DirectUploadRequest,
    DirectUploadTicketOut,
    DocumentOut,
    PageOut,
    PageText,
    PresignedDownload,
    RowOut,
    TableOut,
    UploadResponse,
)
from app.modules.documents.storage import bucket_for, get_storage, original_bucket
from app.modules.documents.upload_service import complete_direct_upload, prepare_direct_upload, upload_documents
from app.modules.documents.uploadthing import UploadThingError
from app.shared.enums import DocumentStatus, DocumentType, FileKind, ScanStatus, StorageCategory
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/documents", tags=["documents"])
Reader = Annotated[Principal, Depends(require(Permission.DOCUMENT_READ))]
Uploader = Annotated[Principal, Depends(require(Permission.DOCUMENT_UPLOAD))]
Deleter = Annotated[Principal, Depends(require(Permission.DOCUMENT_DELETE))]


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={422: {"description": "All files rejected"}, 413: {"description": "Request too large"}},
)
async def upload(
    request: Request,
    principal: Uploader,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    """Upload one or more files (multipart field name ``files``). Processing is asynchronous;
    poll ``status_url`` for each accepted file."""
    settings = get_settings()
    key = idempotency.validate_key(idempotency_key)
    form = await request.form(max_files=settings.upload_max_files, max_fields=20, max_part_size=1024 * 64)
    files = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
    if not files:
        raise ValidationFailedError("No files provided (multipart field 'files')", code="NO_FILES")
    if len(files) > settings.upload_max_files:
        raise ValidationFailedError(f"At most {settings.upload_max_files} files per request", code="TOO_MANY_FILES")

    record = None
    if key:
        fp = idempotency.fingerprint([(f.filename, f.size) for f in files])
        record, replay = await idempotency.begin(session, principal, "documents.upload", key, fp)
        if replay is not None:
            return JSONResponse(
                status_code=replay.response_status or 200, content=replay.response_body_json, headers={"Idempotent-Replay": "true"}
            )
    try:
        results = await upload_documents(session, principal, files)
    except Exception:
        if record is not None:
            await idempotency.abandon(session, record)
        raise
    accepted = sum(1 for r in results if r.status == "accepted")
    body = UploadResponse(results=results, accepted=accepted, rejected=len(results) - accepted).model_dump(mode="json")
    code = status.HTTP_202_ACCEPTED if accepted else status.HTTP_422_UNPROCESSABLE_CONTENT
    if record is not None:
        await idempotency.complete(session, record, code, body)
    return JSONResponse(status_code=code, content=body)


@router.post(
    "/upload/raw",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={422: {"description": "File rejected"}, 413: {"description": "Request too large"}},
    openapi_extra={
        "requestBody": {"required": True, "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
async def upload_raw(
    request: Request,
    principal: Uploader,
    session: SessionDep,
    filename: Annotated[str, Query(min_length=1, max_length=255, description="Original file name, e.g. invoice.pdf")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    """Upload one file as the raw request body (no multipart), e.g.
    ``curl --data-binary @invoice.pdf "$API/documents/upload/raw?filename=invoice.pdf"``.
    The bytes are stored unmodified; the file type is detected from its content."""
    settings = get_settings()
    key = idempotency.validate_key(idempotency_key)
    spooled = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)  # noqa: SIM115 - closed by UploadFile.close()
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > settings.upload_max_file_bytes:
            spooled.close()
            raise PayloadTooLargeError(f"File exceeds the {settings.upload_max_file_bytes} byte limit", code="FILE_TOO_LARGE")
        await anyio.to_thread.run_sync(spooled.write, chunk)
    spooled.seek(0)
    upload_file = UploadFile(file=spooled, filename=filename, size=size, headers=request.headers)  # type: ignore[arg-type]
    record = None
    if key:
        digest_input = [(filename, size)]
        record, replay = await idempotency.begin(session, principal, "documents.upload.raw", key, idempotency.fingerprint(digest_input))
        if replay is not None:
            await upload_file.close()
            return JSONResponse(
                status_code=replay.response_status or 200, content=replay.response_body_json, headers={"Idempotent-Replay": "true"}
            )
    try:
        results = await upload_documents(session, principal, [upload_file], via="raw")
    except Exception:
        if record is not None:
            await idempotency.abandon(session, record)
        raise
    accepted = sum(1 for r in results if r.status == "accepted")
    body = UploadResponse(results=results, accepted=accepted, rejected=len(results) - accepted).model_dump(mode="json")
    code = status.HTTP_202_ACCEPTED if accepted else status.HTTP_422_UNPROCESSABLE_CONTENT
    if record is not None:
        await idempotency.complete(session, record, code, body)
    return JSONResponse(status_code=code, content=body)


@router.post("/direct-uploads", response_model=DirectUploadTicketOut, status_code=status.HTTP_201_CREATED)
async def create_direct_upload(body: DirectUploadRequest, principal: Uploader, session: SessionDep) -> DirectUploadTicketOut:
    """Step 1 of a direct upload: get a signed UploadThing URL. The client sends the
    file straight to UploadThing (``PUT upload_url``, multipart field ``file``), then
    calls ``complete_url``. Requires ``ORIGINALS_STORAGE=uploadthing``."""
    try:
        ticket = await prepare_direct_upload(session, principal, body.filename, body.size)
    except FileRejected as exc:
        status_code = 409 if exc.code == "DIRECT_UPLOAD_UNAVAILABLE" else 503 if exc.code == "STORAGE_UNAVAILABLE" else 422
        raise AppError(exc.message, code=exc.code, status_code=status_code) from exc
    return DirectUploadTicketOut(
        upload_id=ticket.upload_id,
        document_id=ticket.document_id,
        upload_url=ticket.upload_url,
        max_bytes=ticket.max_bytes,
        expires_at=ticket.expires_at,
        complete_url=f"/api/v1/documents/direct-uploads/{ticket.upload_id}/complete",
    )


@router.post("/direct-uploads/{upload_id}/complete", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def finish_direct_upload(upload_id: uuid.UUID, principal: Uploader, session: SessionDep) -> JSONResponse:
    """Step 2: the server downloads the file from UploadThing, verifies its content
    signature, size and hash, and starts processing. Safe to call more than once."""
    result = await complete_direct_upload(session, principal, upload_id)
    accepted = 1 if result.status == "accepted" else 0
    body = UploadResponse(results=[result], accepted=accepted, rejected=1 - accepted).model_dump(mode="json")
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED if accepted else status.HTTP_422_UNPROCESSABLE_CONTENT, content=body)


@router.get("", response_model=Page[DocumentOut])
async def list_documents(
    principal: Reader,
    session: SessionDep,
    page: Annotated[PageParams, Depends(page_params)],
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    document_type: DocumentType | None = None,
    file_kind: FileKind | None = None,
    filename: Annotated[str | None, Query(max_length=200)] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> Page[DocumentOut]:
    stmt = select(Document).where(Document.organization_id == principal.organization_id, Document.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)
    if document_type:
        stmt = stmt.where(Document.document_type == document_type)
    if file_kind:
        stmt = stmt.where(Document.file_kind == file_kind)
    if filename:
        stmt = stmt.where(Document.original_filename.ilike("%" + filename.replace("%", r"\%").replace("_", r"\_") + "%"))
    if created_from:
        stmt = stmt.where(Document.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Document.created_at <= created_to)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        (await session.execute(stmt.order_by(Document.created_at.desc(), Document.id.desc()).limit(page.limit).offset(page.offset)))
        .scalars()
        .all()
    )
    return Page(items=[DocumentOut.model_validate(d) for d in rows], total=total, limit=page.limit, offset=page.offset)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, principal: Reader, session: SessionDep) -> Document:
    return await service.get_document(session, principal, document_id)


@router.get("/{document_id}/download", response_model=None, responses={200: {"content": {"application/octet-stream": {}}}})
async def download(
    document_id: uuid.UUID,
    principal: Reader,
    session: SessionDep,
    mode: Literal["stream", "presigned"] = "stream",
) -> StreamingResponse | PresignedDownload:
    settings = get_settings()
    doc = await service.get_document(session, principal, document_id)
    if doc.scan_status == ScanStatus.INFECTED:
        raise ConflictError("File is quarantined", code="FILE_QUARANTINED")
    record_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="document.downloaded",
        resource_type="document",
        resource_id=doc.id,
        metadata={"mode": mode},
    )
    await session.commit()
    bucket = original_bucket(doc.storage_key)
    storage = get_storage()
    if mode == "presigned":
        try:
            url = await anyio.to_thread.run_sync(
                storage.presigned_get, bucket, doc.storage_key, doc.original_filename, settings.s3_presigned_url_ttl_seconds
            )
        except UploadThingError as exc:
            raise ConflictError(exc.message, code=exc.code) from exc
        return PresignedDownload(url=url, expires_in=settings.s3_presigned_url_ttl_seconds)
    iterator = storage.iter_object(bucket, doc.storage_key)

    async def body() -> Any:
        while True:
            chunk = await anyio.to_thread.run_sync(next, iterator, None)
            if chunk is None:
                break
            yield chunk

    safe = doc.original_filename.replace('"', "")
    return StreamingResponse(
        body(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe}"',
            "Content-Length": str(doc.file_size_bytes),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{document_id}/pages", response_model=Page[PageOut])
async def list_pages(
    document_id: uuid.UUID, principal: Reader, session: SessionDep, page: Annotated[PageParams, Depends(page_params)]
) -> Page[PageOut]:
    doc = await service.get_document(session, principal, document_id)
    base = select(DocumentPage).where(DocumentPage.document_id == doc.id, DocumentPage.organization_id == principal.organization_id)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.order_by(DocumentPage.page_number).limit(page.limit).offset(page.offset))).scalars().all()
    return Page(items=[PageOut.model_validate(p) for p in rows], total=total, limit=page.limit, offset=page.offset)


@router.get("/{document_id}/pages/{page_number}/image")
async def get_page_image(
    document_id: uuid.UUID,
    page_number: Annotated[int, Path(ge=1)],
    principal: Reader,
    session: SessionDep,
    request: Request,
    width: Annotated[int | None, Query(ge=1, le=4000)] = None,
) -> Response:
    """Render a single document page as PNG with caching and ETag."""
    import hashlib
    import io
    import pymupdf
    from PIL import Image

    doc = await service.get_document(session, principal, document_id)
    page_row = (
        await session.execute(
            select(DocumentPage).where(
                DocumentPage.document_id == doc.id,
                DocumentPage.page_number == page_number,
                DocumentPage.organization_id == principal.organization_id,
            )
        )
    ).scalar_one_or_none()
    if not page_row:
        raise NotFoundError(f"Page {page_number} not found for document", code="PAGE_NOT_FOUND")

    bucket = original_bucket(doc.storage_key)
    storage = get_storage()
    try:
        raw_bytes = await anyio.to_thread.run_sync(storage.get_bytes, bucket, doc.storage_key)
    except Exception as e:
        raise NotFoundError("Original file could not be retrieved from storage", code="FILE_NOT_FOUND") from e

    def _render() -> bytes:
        is_pdf = doc.file_kind == FileKind.PDF or str(doc.file_kind).upper() == "PDF"
        is_img = (
            doc.file_kind in (FileKind.IMAGE, FileKind.TIFF)
            or str(doc.file_kind).upper() in ("IMAGE", "TIFF")
        )
        if is_pdf:
            pdf_doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
            if page_number > len(pdf_doc):
                raise NotFoundError(f"Page {page_number} out of range", code="PAGE_NOT_FOUND")
            page = pdf_doc[page_number - 1]
            rect = page.rect
            if width and rect.width > 0:
                scale = width / rect.width
                mat = pymupdf.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=mat)
            else:
                pix = page.get_pixmap(dpi=150)
            return pix.tobytes("png")
        elif is_img:
            if doc.file_extension in (".tiff", ".tif"):
                try:
                    tif_doc = pymupdf.open(stream=raw_bytes, filetype="tiff")
                    if page_number > len(tif_doc):
                        raise NotFoundError(f"Page {page_number} out of range", code="PAGE_NOT_FOUND")
                    page = tif_doc[page_number - 1]
                    rect = page.rect
                    if width and rect.width > 0:
                        scale = width / rect.width
                        mat = pymupdf.Matrix(scale, scale)
                        pix = page.get_pixmap(matrix=mat)
                    else:
                        pix = page.get_pixmap(dpi=150)
                    return pix.tobytes("png")
                except Exception:
                    pass
            img = Image.open(io.BytesIO(raw_bytes))
            if page_number > 1:
                try:
                    img.seek(page_number - 1)
                except EOFError:
                    raise NotFoundError(f"Page {page_number} out of range", code="PAGE_NOT_FOUND")
            if width and img.width > 0:
                h = max(1, int(img.height * (width / img.width)))
                img = img.resize((width, h), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="PNG")
            return out.getvalue()
        else:
            raise ValidationFailedError("Document type does not support page image rendering", code="PAGE_IMAGE_NOT_SUPPORTED")

    try:
        png_bytes = await anyio.to_thread.run_sync(_render)
    except AppError:
        raise
    except Exception as e:
        raise NotFoundError(f"Rendering page image failed: {e}", code="PAGE_RENDER_FAILED") from e

    etag = f'"{hashlib.sha256(png_bytes).hexdigest()[:32]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": etag,
            "Content-Type": "image/png",
        },
    )


@router.get("/{document_id}/text", response_model=list[PageText])
async def get_text(
    document_id: uuid.UUID,
    principal: Reader,
    session: SessionDep,
    page_from: Annotated[int, Query(ge=1)] = 1,
    page_to: Annotated[int | None, Query(ge=1)] = None,
) -> list[PageText]:
    doc = await service.get_document(session, principal, document_id)
    page_to = page_to or page_from + 19
    if page_to - page_from >= 50 or page_to < page_from:
        raise ValidationFailedError("Request at most 50 pages per call", code="PAGE_RANGE_TOO_LARGE")
    rows = (
        await session.execute(
            select(DocumentPage.page_number, DocumentPage.extracted_text, DocumentPage.text_storage_key)
            .where(
                DocumentPage.document_id == doc.id,
                DocumentPage.organization_id == principal.organization_id,
                DocumentPage.page_number.between(page_from, page_to),
            )
            .order_by(DocumentPage.page_number)
        )
    ).all()
    out = []
    for number, text, key in rows:
        if key:
            data = await anyio.to_thread.run_sync(get_storage().get_json, bucket_for(StorageCategory.PAGE_TEXT), key)
            out.append(PageText(page_number=number, text=data.get("text", "")))
        else:
            out.append(PageText(page_number=number, text=text or ""))
    return out


@router.get("/{document_id}/tables", response_model=Page[TableOut])
async def list_tables(
    document_id: uuid.UUID, principal: Reader, session: SessionDep, page: Annotated[PageParams, Depends(page_params)]
) -> Page[TableOut]:
    doc = await service.get_document(session, principal, document_id)
    base = select(DocumentTable).where(DocumentTable.document_id == doc.id, DocumentTable.organization_id == principal.organization_id)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(DocumentTable.page_number.nulls_first(), DocumentTable.source_key, DocumentTable.table_index)
                .limit(page.limit)
                .offset(page.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page(items=[TableOut.model_validate(t) for t in rows], total=total, limit=page.limit, offset=page.offset)


@router.get("/{document_id}/tables/{table_id}/rows", response_model=Page[RowOut])
async def list_rows(
    document_id: uuid.UUID, table_id: uuid.UUID, principal: Reader, session: SessionDep, page: Annotated[PageParams, Depends(page_params)]
) -> Page[RowOut]:
    doc = await service.get_document(session, principal, document_id)
    base = select(SpreadsheetRow).where(
        SpreadsheetRow.document_id == doc.id,
        SpreadsheetRow.table_id == table_id,
        SpreadsheetRow.organization_id == principal.organization_id,
    )
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.order_by(SpreadsheetRow.row_number).limit(page.limit).offset(page.offset))).scalars().all()
    return Page(items=[RowOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


@router.get("/{document_id}/spreadsheet/mapping-suggestions", response_model=list[MappingSuggestions])
async def mapping_suggestions(document_id: uuid.UUID, principal: Reader, session: SessionDep) -> list[MappingSuggestions]:
    """Suggested column → invoice-field mappings per sheet, for user confirmation."""
    doc = await service.get_document(session, principal, document_id)
    if not doc.file_kind.is_spreadsheet:
        raise ValidationFailedError("Document is not a spreadsheet", code="NOT_A_SPREADSHEET")
    tables = (
        (
            await session.execute(
                select(DocumentTable)
                .where(DocumentTable.document_id == doc.id, DocumentTable.page_id.is_(None))
                .order_by(DocumentTable.source_key)
            )
        )
        .scalars()
        .all()
    )
    if not tables:
        raise NotFoundError("Spreadsheet has not been parsed yet")
    return [suggest_mapping([str(h) for h in (t.header_json or [])], t.sheet_name) for t in tables]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, principal: Deleter, session: SessionDep) -> None:
    await service.soft_delete(session, principal, document_id)
