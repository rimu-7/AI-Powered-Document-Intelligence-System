"""Rebuild visual text lines from positioned words.

Both native PDF words and OCR words are grouped into rows by vertical
position. Large horizontal gaps are kept as two or more spaces, so table
columns stay separable (e.g. ``Office Chair    2    500.00    1,000.00``).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from app.modules.parsing.schemas import LayoutLine


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    conf: float | None = None


def group_words_into_lines(words: list[Word]) -> list[LayoutLine]:
    words = [w for w in words if w.text and w.text.strip()]
    if not words:
        return []
    heights = [max(0.1, w.y1 - w.y0) for w in words]
    tolerance = max(1.0, median(heights) * 0.55)
    ordered = sorted(words, key=lambda w: ((w.y0 + w.y1) / 2, w.x0))
    rows: list[list[Word]] = []
    centers: list[float] = []
    for word in ordered:
        center = (word.y0 + word.y1) / 2
        if rows and abs(center - centers[-1]) <= tolerance:
            rows[-1].append(word)
            n = len(rows[-1])
            centers[-1] = centers[-1] + (center - centers[-1]) / n
        else:
            rows.append([word])
            centers.append(center)

    lines: list[LayoutLine] = []
    for row in rows:
        row.sort(key=lambda w: w.x0)
        char_w = median([(w.x1 - w.x0) / max(1, len(w.text)) for w in row]) or 1.0
        parts: list[str] = [row[0].text]
        for prev, cur in zip(row, row[1:], strict=False):
            gap = cur.x0 - prev.x1
            if gap > char_w * 2.5:
                parts.append(" " * max(2, min(8, int(gap / char_w / 2))))
            else:
                parts.append(" ")
            parts.append(cur.text)
        confs = [w.conf for w in row if w.conf is not None]
        lines.append(
            LayoutLine(
                text="".join(parts),
                bbox=(
                    round(min(w.x0 for w in row), 1),
                    round(min(w.y0 for w in row), 1),
                    round(max(w.x1 for w in row), 1),
                    round(max(w.y1 for w in row), 1),
                ),
                confidence=round(sum(confs) / len(confs), 4) if confs else None,
            )
        )
    return lines
