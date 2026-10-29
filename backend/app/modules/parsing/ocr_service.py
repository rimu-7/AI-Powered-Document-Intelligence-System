"""OCR behind a provider interface (Tesseract implementation).

OCR confidence is the engine's own recognition score. It is stored for
diagnostics and routing only and is never treated as a calibrated probability
that extracted financial values are correct.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Protocol

from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import PermanentProcessingError, TransientProcessingError
from app.core.logging import get_logger
from app.core.metrics import OCR_FAILURES
from app.modules.parsing.layout import Word, group_words_into_lines
from app.modules.parsing.preprocessing import preprocess_for_ocr
from app.modules.parsing.schemas import OcrResult

logger = get_logger(__name__)


class OCRProvider(Protocol):
    def recognize(self, image: Image.Image) -> OcrResult: ...

    def recognize_batch(self, images: list[Image.Image]) -> list[OcrResult]: ...

    def healthcheck(self) -> bool: ...

    def provider_name(self) -> str: ...


class OcrUnavailableError(PermanentProcessingError):
    code = "OCR_UNAVAILABLE"


class OcrTimeoutError(TransientProcessingError):
    code = "OCR_TIMEOUT"


class TesseractProvider:
    def __init__(self, languages: str, timeout: int) -> None:
        self.languages = languages
        self.timeout = timeout

    def provider_name(self) -> str:
        return "tesseract"

    def healthcheck(self) -> bool:
        import pytesseract

        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _orientation(self, image: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
        import pytesseract

        try:
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT, timeout=min(30, self.timeout))
        except Exception:  # noqa: BLE001 - OSD fails on sparse pages; not fatal
            return image, {"orientation": "unknown"}
        rotate = int(osd.get("rotate", 0) or 0)
        conf = float(osd.get("orientation_conf", 0) or 0)
        if rotate and conf >= 2.0:
            return image.rotate(-rotate, expand=True), {"orientation_rotated": rotate, "orientation_conf": conf}
        return image, {"orientation_rotated": 0, "orientation_conf": conf}

    def recognize(self, image: Image.Image) -> OcrResult:
        import pytesseract

        prep = preprocess_for_ocr(image)
        work, orientation_meta = self._orientation(prep.image)
        try:
            data = pytesseract.image_to_data(
                work,
                lang=self.languages,
                config="--oem 1 --psm 3",
                output_type=pytesseract.Output.DICT,
                timeout=self.timeout,
            )
        except RuntimeError as exc:
            OCR_FAILURES.labels("tesseract", "timeout").inc()
            raise OcrTimeoutError("Tesseract timed out") from exc
        except pytesseract.TesseractNotFoundError as exc:
            OCR_FAILURES.labels("tesseract", "missing").inc()
            raise OcrUnavailableError("Tesseract binary not installed") from exc
        except pytesseract.TesseractError as exc:
            OCR_FAILURES.labels("tesseract", "error").inc()
            raise PermanentProcessingError(f"Tesseract failed: {exc.status}", code="OCR_FAILED") from exc

        sx = image.width / max(1, work.width)
        sy = image.height / max(1, work.height)
        words: list[Word] = []
        confs: list[float] = []
        for i, word in enumerate(data["text"]):
            if not word or not word.strip():
                continue
            conf = float(data["conf"][i])
            if conf >= 0:
                confs.append(conf)
            words.append(
                Word(
                    x0=data["left"][i] * sx,
                    y0=data["top"][i] * sy,
                    x1=(data["left"][i] + data["width"][i]) * sx,
                    y1=(data["top"][i] + data["height"][i]) * sy,
                    text=word,
                    conf=round(conf / 100, 4) if conf >= 0 else None,
                )
            )
        lines = group_words_into_lines(words)
        text = "\n".join(line.text for line in lines)
        confidence = round(sum(confs) / len(confs) / 100, 4) if confs else None
        return OcrResult(
            text=text,
            lines=lines,
            confidence=confidence,
            engine="tesseract",
            metadata={"preprocessing": prep.steps, **orientation_meta, "image_px": [image.width, image.height]},
        )

    def recognize_batch(self, images: list[Image.Image]) -> list[OcrResult]:
        return [self.recognize(img) for img in images]


@lru_cache(maxsize=1)
def get_ocr_provider() -> OCRProvider:
    settings = get_settings()
    return TesseractProvider(settings.ocr_languages, settings.ocr_timeout_seconds)


_GARBAGE_RE = re.compile(r"[�-]")


def text_quality(text: str) -> float:
    """Share of characters that look like real text (0..1)."""
    stripped = re.sub(r"\s", "", text)
    if not stripped:
        return 0.0
    garbage = len(_GARBAGE_RE.findall(stripped))
    alnum = sum(1 for c in stripped if c.isalnum())
    punct_ok = sum(1 for c in stripped if c in ".,:;-/$€£%#()&'\"+*@")
    return max(0.0, min(1.0, (alnum + punct_ok - 2 * garbage) / len(stripped)))
