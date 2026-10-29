"""JPG/PNG/TIFF (incl. multipage TIFF) parsing via OCR with decompression-bomb guards."""

from __future__ import annotations

import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.core.exceptions import PermanentProcessingError
from app.core.metrics import OCR_PAGES, PAGES_PROCESSED
from app.modules.parsing.ocr_service import OCRProvider
from app.modules.parsing.schemas import PageResult
from app.shared.enums import PageType


class ImageMalformedError(PermanentProcessingError):
    code = "IMAGE_MALFORMED"


class ImageTooLargeError(PermanentProcessingError):
    code = "IMAGE_TOO_LARGE"


def _configure_pil() -> None:
    Image.MAX_IMAGE_PIXELS = get_settings().max_image_pixels
    # Treat Pillow's "possible decompression bomb" warning as an error.
    warnings.simplefilter("error", Image.DecompressionBombWarning)


def _open(path: str) -> Image.Image:
    _configure_pil()
    try:
        image = Image.open(path)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageTooLargeError("Image exceeds the pixel limit") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageMalformedError(f"Image could not be decoded: {type(exc).__name__}") from exc
    return image


def count_frames(path: str) -> int:
    image = _open(path)
    try:
        return int(getattr(image, "n_frames", 1))
    finally:
        image.close()


def process_image_frame(path: str, frame_number: int, ocr: OCRProvider) -> PageResult:
    """OCR one 1-based frame (page) of an image or multipage TIFF."""
    image = _open(path)
    try:
        try:
            image.seek(frame_number - 1)
            if image.width * image.height > get_settings().max_image_pixels:
                raise ImageTooLargeError("Image frame exceeds the pixel limit")
            frame = ImageOps.exif_transpose(image.copy())
            frame.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ImageTooLargeError("Image exceeds the pixel limit") from exc
        except EOFError as exc:
            raise ImageMalformedError(f"Frame {frame_number} does not exist") from exc
        except OSError as exc:
            raise ImageMalformedError(f"Frame {frame_number} is corrupted") from exc
    finally:
        image.close()
    if frame.mode not in ("L", "RGB"):
        frame = frame.convert("RGB")
    width, height = frame.width, frame.height
    try:
        ocr_result = ocr.recognize(frame)
    finally:
        frame.close()
    OCR_PAGES.labels(ocr_result.engine).inc()
    PAGES_PROCESSED.labels(PageType.IMAGE.value, "ocr").inc()
    return PageResult(
        page_number=frame_number,
        page_type=PageType.IMAGE,
        text=ocr_result.text,
        lines=ocr_result.lines,
        ocr_engine=ocr_result.engine,
        ocr_confidence=ocr_result.confidence,
        page_width=float(width),
        page_height=float(height),
        metadata={"extraction_method": "ocr", "ocr": ocr_result.metadata, "image_px": [width, height]},
    )
