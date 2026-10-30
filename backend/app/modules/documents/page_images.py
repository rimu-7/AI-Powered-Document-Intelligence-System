"""Page images for the review viewer, rendered once and cached.

A page is rendered from the original file (PDF via PyMuPDF; PNG/JPG/TIFF via
Pillow, with EXIF orientation applied exactly as OCR saw it, so evidence
bounding boxes line up) at one of a few fixed widths. Rendered images are
stored in the artifacts bucket; later requests are served from there and
browsers revalidate with an ETag derived from the file hash, so an unchanged
page is never downloaded or rendered twice.
"""

from __future__ import annotations

import io
import uuid

import pymupdf
from botocore.exceptions import ClientError
from PIL import Image, ImageOps

from app.modules.documents.models import Document
from app.modules.documents.storage import get_storage
from app.shared.enums import FileKind
from app.workers.files import local_copy

RENDER_VERSION = 1
WIDTHS = (240, 640, 1024, 1600)
DEFAULT_WIDTH = 1024
WEBP_QUALITY = 85


class PageOutOfRange(Exception):
    pass


def snap_width(requested: int | None) -> int:
    """Round up to a cached width so the cache stays small and hit rates high."""
    if requested is None:
        return DEFAULT_WIDTH
    return next((w for w in WIDTHS if w >= requested), WIDTHS[-1])


def page_images_prefix(organization_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f"{organization_id}/{document_id}/page-images/"


def cache_key(organization_id: uuid.UUID, document_id: uuid.UUID, page_number: int, width: int) -> str:
    return f"{page_images_prefix(organization_id, document_id)}v{RENDER_VERSION}/{page_number}-{width}.webp"


def etag(sha256: str, page_number: int, width: int) -> str:
    return f'"{sha256[:32]}-{page_number}-{width}-v{RENDER_VERSION}"'


def _encode(image: Image.Image, width: int) -> bytes:
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    if image.width > width:
        image = image.resize((width, max(1, round(image.height * width / image.width))), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=WEBP_QUALITY, method=4)
    return out.getvalue()


def _render_pdf(path: str, page_number: int, width: int) -> bytes:
    with pymupdf.open(path) as pdf:
        if page_number > pdf.page_count:
            raise PageOutOfRange
        page = pdf[page_number - 1]
        scale = width / page.rect.width if page.rect.width else 1.0
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return _encode(image, width)


def _render_image(path: str, page_number: int, width: int) -> bytes:
    with Image.open(path) as image:
        try:
            image.seek(page_number - 1)
        except EOFError as exc:
            raise PageOutOfRange from exc
        frame = ImageOps.exif_transpose(image.copy())
    return _encode(frame, width)


def render_page(file_kind: FileKind, path: str, page_number: int, width: int) -> bytes:
    if file_kind == FileKind.PDF:
        return _render_pdf(path, page_number, width)
    if file_kind in (FileKind.IMAGE, FileKind.TIFF):
        return _render_image(path, page_number, width)
    raise ValueError(f"No page images for {file_kind}")


def get_or_render(document: Document, page_number: int, width: int, artifacts_bucket: str) -> bytes:
    """Blocking (call from a worker thread). Cached render, else render from a
    local, hash-verified copy of the original that later pages reuse."""
    storage = get_storage()
    key = cache_key(document.organization_id, document.id, page_number, width)
    try:
        return storage.get_bytes(artifacts_bucket, key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
            raise
    data = render_page(FileKind(document.file_kind), local_copy(document), page_number, width)
    storage.put_bytes(artifacts_bucket, key, data, "image/webp")
    return data
