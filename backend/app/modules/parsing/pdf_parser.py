"""PDF parsing with PyMuPDF: native text first, OCR only where needed.

Pages are processed one at a time and rendered images are released right
away, so memory use stays bounded even for 1,000-page documents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pymupdf
from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import PermanentProcessingError
from app.core.metrics import OCR_PAGES, PAGES_PROCESSED
from app.modules.parsing.layout import Word, group_words_into_lines
from app.modules.parsing.ocr_service import OCRProvider, text_quality
from app.modules.parsing.schemas import LayoutLine, PageResult, TableData
from app.shared.enums import PageType

pymupdf.TOOLS.mupdf_display_errors(False)


class PdfEncryptedError(PermanentProcessingError):
    code = "PDF_ENCRYPTED"


class PdfMalformedError(PermanentProcessingError):
    code = "PDF_MALFORMED"


@dataclass
class PdfInfo:
    page_count: int
    metadata: dict[str, Any]


def open_pdf(path: str) -> pymupdf.Document:
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise PdfMalformedError(f"PDF could not be opened: {type(exc).__name__}") from exc
    if doc.needs_pass:
        doc.close()
        raise PdfEncryptedError("PDF is password-protected")
    if doc.page_count == 0:
        doc.close()
        raise PdfMalformedError("PDF has no pages")
    return doc


def inspect_pdf(path: str) -> PdfInfo:
    doc = open_pdf(path)
    try:
        meta = {k: v for k, v in (doc.metadata or {}).items() if v and k in ("format", "producer", "creator", "title")}
        meta["is_encrypted"] = bool(doc.is_encrypted)
        # MuPDF silently repairs damaged files (e.g. truncated); content may be incomplete.
        meta["repaired"] = bool(doc.is_repaired)
        return PdfInfo(page_count=doc.page_count, metadata=meta)
    finally:
        doc.close()


_NUMERIC_TOKEN = re.compile(r"\d[\d,.]*\d|\d")


def _looks_tabular(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    numeric_lines = sum(1 for ln in lines if len(_NUMERIC_TOKEN.findall(ln)) >= 2)
    return numeric_lines >= 3


def analyse_page(page: pymupdf.Page) -> dict[str, Any]:
    rect = page.rect
    area = max(1.0, rect.width * rect.height)
    image_area = 0.0
    try:
        for info in page.get_image_info():
            bbox = pymupdf.Rect(info["bbox"]) & rect
            image_area += max(0.0, bbox.width * bbox.height)
    except Exception:  # noqa: BLE001 - damaged image refs must not kill the page
        pass
    text = page.get_text("text", sort=True)
    return {
        "native_text": text,
        "native_chars": len(text.strip()),
        "image_coverage": round(min(1.0, image_area / area), 4),
        "quality": round(text_quality(text), 4),
        "width": rect.width,
        "height": rect.height,
        "rotation": page.rotation,
    }


def classify_page(analysis: dict[str, Any]) -> PageType:
    settings = get_settings()
    chars, coverage, quality = analysis["native_chars"], analysis["image_coverage"], analysis["quality"]
    usable = chars >= settings.native_text_min_chars and quality >= settings.native_text_min_quality
    if usable and coverage < 0.5:
        return PageType.NATIVE_TEXT
    if usable and coverage >= 0.5:
        return PageType.MIXED
    if coverage > 0.05:
        return PageType.SCANNED
    if chars > 0:
        # Some text but low quality/quantity and no images: try OCR fallback.
        return PageType.MIXED
    return PageType.EMPTY


def _native_lines(page: pymupdf.Page) -> list[LayoutLine]:
    words = [Word(x0=w[0], y0=w[1], x1=w[2], y1=w[3], text=w[4]) for w in page.get_text("words", sort=True)]
    return group_words_into_lines(words)


def _tables(page: pymupdf.Page) -> list[TableData]:
    tables: list[TableData] = []
    try:
        found = page.find_tables()
    except Exception:  # noqa: BLE001 - table detection is best effort
        return tables
    for i, table in enumerate(found.tables[:10]):
        try:
            rows = table.extract()
        except Exception:  # noqa: BLE001
            continue
        if not rows or len(rows) < 2:
            continue
        header = None
        if table.header and table.header.names and not table.header.external:
            header = [str(h) if h is not None else None for h in table.header.names]
        cleaned = [[(str(c).strip() if c is not None else None) for c in row] for row in rows[:2000]]
        tables.append(TableData(index=i, rows=cleaned, header=header, bbox=tuple(round(v, 1) for v in table.bbox)))  # type: ignore[arg-type]
    return tables


def render_page(page: pymupdf.Page) -> Image.Image:
    settings = get_settings()
    rect = page.rect
    zoom = settings.ocr_dpi / 72
    pixels = rect.width * zoom * rect.height * zoom
    if pixels > settings.max_render_pixels:
        zoom *= (settings.max_render_pixels / pixels) ** 0.5
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False)
    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    del pix
    return image


def process_pdf_page(doc: pymupdf.Document, page_number: int, ocr: OCRProvider) -> PageResult:
    """Process one 1-based page number."""
    settings = get_settings()
    try:
        page = doc.load_page(page_number - 1)
    except Exception as exc:
        raise PdfMalformedError(f"Page {page_number} could not be loaded") from exc

    analysis = analyse_page(page)
    page_type = classify_page(analysis)
    meta: dict[str, Any] = {k: v for k, v in analysis.items() if k != "native_text"}
    result = PageResult(
        page_number=page_number,
        page_type=page_type,
        text=analysis["native_text"],
        page_width=analysis["width"],
        page_height=analysis["height"],
        metadata=meta,
    )

    if page_type == PageType.NATIVE_TEXT:
        result.lines = _native_lines(page)
        result.text = "\n".join(line.text for line in result.lines)
        meta["extraction_method"] = "native"
        if settings.pdf_table_extraction and _looks_tabular(result.text):
            result.tables = _tables(page)
        PAGES_PROCESSED.labels(page_type.value, "native").inc()
        return result

    if page_type == PageType.EMPTY:
        meta["extraction_method"] = "none"
        PAGES_PROCESSED.labels(page_type.value, "none").inc()
        return result

    # SCANNED or MIXED: OCR, then keep whichever text is more useful.
    image = render_page(page)
    try:
        ocr_result = ocr.recognize(image)
    finally:
        render_w, render_h = image.width, image.height
        image.close()
    OCR_PAGES.labels(ocr_result.engine).inc()
    scale_x = analysis["width"] / max(1, render_w)
    scale_y = analysis["height"] / max(1, render_h)
    ocr_lines = [
        LayoutLine(
            text=ln.text,
            bbox=(
                round(ln.bbox[0] * scale_x, 1),
                round(ln.bbox[1] * scale_y, 1),
                round(ln.bbox[2] * scale_x, 1),
                round(ln.bbox[3] * scale_y, 1),
            )
            if ln.bbox
            else None,
            confidence=ln.confidence,
        )
        for ln in ocr_result.lines
    ]
    meta["ocr"] = ocr_result.metadata
    native_useful = analysis["native_chars"] >= settings.native_text_min_chars and analysis["quality"] >= settings.native_text_min_quality
    if page_type == PageType.MIXED and native_useful and len(ocr_result.text.strip()) <= analysis["native_chars"]:
        result.lines = _native_lines(page)
        result.text = "\n".join(line.text for line in result.lines)
        meta["extraction_method"] = "native_after_ocr_check"
    else:
        result.text = ocr_result.text
        result.lines = ocr_lines
        result.ocr_engine = ocr_result.engine
        result.ocr_confidence = ocr_result.confidence
        meta["extraction_method"] = "ocr"
    PAGES_PROCESSED.labels(page_type.value, meta["extraction_method"]).inc()
    return result
