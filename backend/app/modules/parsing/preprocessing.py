"""Conditional image preprocessing for OCR.

Each step runs only when a measurement says it is needed, so already-clean
images are not degraded. The original image is never modified.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

MIN_OCR_WIDTH = 1200
MAX_OCR_SIDE = 5000


@dataclass
class ImageAssessment:
    width: int
    height: int
    contrast: float
    noise: float
    skew_degrees: float


@dataclass
class PreprocessResult:
    image: Image.Image
    steps: list[str] = field(default_factory=list)
    assessment: ImageAssessment | None = None


def _to_gray(image: Image.Image) -> np.ndarray:
    if image.mode not in ("L", "RGB"):
        image = image.convert("RGB")
    arr = np.asarray(image)
    if arr.ndim == 3:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return arr.copy()


def estimate_skew(gray: np.ndarray) -> float:
    """Estimate text skew in degrees from the minimum-area rectangle of ink pixels."""
    small = gray
    scale = 1.0
    if max(gray.shape) > 2000:
        scale = 2000 / max(gray.shape)
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    _, binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ys, xs = np.where(binary > 0)
    if len(xs) < 500:
        return 0.0
    points = np.column_stack((xs, ys)).astype(np.float32)  # (x, y) order for OpenCV
    angle = float(cv2.minAreaRect(points)[-1])
    # The angle convention differs across OpenCV versions; normalise to (-45, 45].
    while angle > 45:
        angle -= 90
    while angle <= -45:
        angle += 90
    return angle


def assess(image: Image.Image) -> ImageAssessment:
    gray = _to_gray(image)
    contrast = float(gray.std())
    # Speckle estimate: mean absolute residual against a 3x3 median filter.
    # Sharp text edges change little under a median filter; salt-and-pepper does.
    noise = float(np.mean(cv2.absdiff(gray, cv2.medianBlur(gray, 3)))) if gray.size else 0.0
    return ImageAssessment(
        width=image.width,
        height=image.height,
        contrast=contrast,
        noise=noise,
        skew_degrees=estimate_skew(gray),
    )


def preprocess_for_ocr(image: Image.Image) -> PreprocessResult:
    assessment = assess(image)
    gray = _to_gray(image)
    steps: list[str] = []

    # Resolution normalization.
    longest = max(gray.shape)
    if gray.shape[1] < MIN_OCR_WIDTH:
        factor = min(3.0, MIN_OCR_WIDTH / max(1, gray.shape[1]))
        gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
        steps.append(f"upscale:{factor:.2f}")
    elif longest > MAX_OCR_SIDE:
        factor = MAX_OCR_SIDE / longest
        gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
        steps.append(f"downscale:{factor:.2f}")

    # Contrast improvement only for low-contrast scans.
    if assessment.contrast < 45:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        steps.append("clahe")

    # Noise reduction only for very noisy images (speckle).
    if assessment.noise > 6:
        gray = cv2.medianBlur(gray, 3)
        steps.append("median_blur")

    # Deskew small rotations; large rotations are handled by orientation detection.
    skew = assessment.skew_degrees
    if 0.5 <= abs(skew) <= 15:
        h, w = gray.shape
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), skew, 1.0)
        gray = cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        steps.append(f"deskew:{skew:.2f}")

    return PreprocessResult(image=Image.fromarray(gray), steps=steps, assessment=assessment)
