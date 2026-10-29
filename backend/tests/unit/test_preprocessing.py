from __future__ import annotations

from typing import Any

import pytest
from PIL import Image, ImageDraw

from app.modules.parsing.image_parser import ImageMalformedError, ImageTooLargeError, count_frames, process_image_frame
from app.modules.parsing.preprocessing import assess, preprocess_for_ocr
from app.modules.parsing.schemas import OcrResult


def _text_image(contrast: int = 255, angle: float = 0.0) -> Image.Image:
    img = Image.new("L", (1600, 1000), 255)
    draw = ImageDraw.Draw(img)
    ink = 255 - contrast
    for row in range(12):
        draw.rectangle((100, 80 + row * 70, 1400, 110 + row * 70), fill=ink)
    return img.rotate(angle, fillcolor=255, expand=False) if angle else img


def test_clean_image_is_not_modified_unnecessarily() -> None:
    result = preprocess_for_ocr(_text_image())
    assert not any(step.startswith(("clahe", "deskew", "median")) for step in result.steps)


def test_skew_is_detected_and_corrected() -> None:
    skewed = _text_image(angle=4)
    assert abs(assess(skewed).skew_degrees) > 2
    result = preprocess_for_ocr(skewed)
    assert any(step.startswith("deskew") for step in result.steps)


def test_low_contrast_triggers_clahe_and_small_images_upscale() -> None:
    assert "clahe" in preprocess_for_ocr(_text_image(contrast=40)).steps
    small = _text_image().resize((400, 250))
    assert any(s.startswith("upscale") for s in preprocess_for_ocr(small).steps)


class FakeOCR:
    def recognize(self, image: Image.Image) -> OcrResult:
        return OcrResult(text=f"frame {image.width}x{image.height}", lines=[], confidence=0.9, engine="fake")

    def recognize_batch(self, images: list[Image.Image]) -> list[OcrResult]:
        return [self.recognize(i) for i in images]

    def healthcheck(self) -> bool:
        return True

    def provider_name(self) -> str:
        return "fake"


def test_multipage_tiff_and_exif_orientation(tmp_path: Any) -> None:
    frames = [Image.new("L", (300, 200), 255), Image.new("L", (320, 220), 255), Image.new("L", (340, 240), 255)]
    path = tmp_path / "multi.tiff"
    frames[0].save(path, save_all=True, append_images=frames[1:])
    assert count_frames(str(path)) == 3
    page = process_image_frame(str(path), 2, FakeOCR())
    assert page.page_number == 2 and page.text == "frame 320x220" and page.ocr_engine == "fake"

    rotated = Image.new("RGB", (300, 100), "white")
    exif = rotated.getexif()
    exif[0x0112] = 6  # rotate 90° CW on display
    jpg = tmp_path / "exif.jpg"
    rotated.save(jpg, exif=exif)
    assert process_image_frame(str(jpg), 1, FakeOCR()).text == "frame 100x300"


def test_decompression_bomb_and_garbage(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    path = tmp_path / "big.png"
    Image.new("L", (3000, 3000), 255).save(path)
    monkeypatch.setattr(get_settings(), "max_image_pixels", 1_000_000)
    with pytest.raises(ImageTooLargeError):
        process_image_frame(str(path), 1, FakeOCR())
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\nnot really")
    with pytest.raises(ImageMalformedError):
        process_image_frame(str(bad), 1, FakeOCR())
