from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.shared.enums import PageType


@dataclass
class LayoutLine:
    text: str
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None

    def to_json(self) -> dict[str, Any]:
        return {"text": self.text, "bbox": list(self.bbox) if self.bbox else None, "conf": self.confidence}


@dataclass
class TableData:
    index: int
    rows: list[list[str | None]]
    header: list[str | None] | None = None
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class OcrResult:
    text: str
    lines: list[LayoutLine]
    confidence: float | None
    engine: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageResult:
    page_number: int
    page_type: PageType
    text: str
    lines: list[LayoutLine] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
    ocr_engine: str | None = None
    ocr_confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    page_width: float | None = None
    page_height: float | None = None
