"""Document-level extraction: segment → extract per segment → normalize → ground → merge.

Pure orchestration (no database access) so it can be tested directly. The
worker pipeline persists the result.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import PermanentProcessingError
from app.core.logging import get_logger
from app.core.metrics import EXTRACTION_DURATION
from app.modules.extraction.confidence import heuristic_confidence
from app.modules.extraction.crosscheck import cross_check as crosscheck_invoice
from app.modules.extraction.crosscheck import pair_invoices
from app.modules.extraction.currency_context import infer_currency
from app.modules.extraction.grounding import GroundingPage, ground_invoice
from app.modules.extraction.normalization import normalize_invoice
from app.modules.extraction.providers.base import ExtractionProvider, ExtractionRequest
from app.modules.extraction.schemas import INVOICE_FIELDS, NormalizationNote, NormalizedInvoice, RawInvoice
from app.modules.parsing.segmentation import PageText, Segment, segment_pages, split_for_budget
from app.shared.text import normalize_invoice_number, normalize_supplier

logger = get_logger(__name__)


@dataclass
class ExtractionPage:
    page_number: int
    text: str
    lines: list[dict[str, Any]] = field(default_factory=list)
    method: str = "native"
    ocr_confidence: float | None = None


@dataclass
class SegmentOutcome:
    segment_index: int
    page_start: int
    page_end: int
    windows: int
    invoices: int
    error_code: str | None = None
    latency_ms: int = 0
    provider: str = ""


@dataclass
class DocumentExtraction:
    invoices: list[NormalizedInvoice]
    segments: list[SegmentOutcome]
    usage: dict[str, Any]
    provider: str
    model: str
    raw_responses: list[str] = field(default_factory=list)

    @property
    def failed_segments(self) -> list[SegmentOutcome]:
        return [s for s in self.segments if s.error_code]


def _merge_raw(a: RawInvoice, b: RawInvoice) -> RawInvoice:
    """Merge two partial extractions of the same invoice (window overlap)."""
    merged = a.model_copy(deep=True)
    for name in INVOICE_FIELDS:
        if getattr(merged, name).value is None and getattr(b, name).value is not None:
            setattr(merged, name, getattr(b, name))
    seen = {(li.description, li.line_total, li.page) for li in merged.line_items}
    for li in b.line_items:
        key = (li.description, li.line_total, li.page)
        if key not in seen:
            merged.line_items.append(li)
            seen.add(key)
    merged.document_kind = merged.document_kind or b.document_kind
    if merged.amounts_tax_inclusive is None:
        merged.amounts_tax_inclusive = b.amounts_tax_inclusive
    return merged


def _key(raw: RawInvoice) -> str | None:
    return normalize_invoice_number(raw.invoice_number.value)


def _combine_windows(results: list[list[RawInvoice]]) -> list[RawInvoice]:
    combined: list[RawInvoice] = []
    by_key: dict[str, int] = {}
    for invoices in results:
        for raw in invoices:
            key = _key(raw)
            if key and key in by_key:
                combined[by_key[key]] = _merge_raw(combined[by_key[key]], raw)
            elif key is None and combined and _key(combined[-1]) is not None:
                # A window with no invoice number continues the previous invoice.
                combined[-1] = _merge_raw(combined[-1], raw)
            else:
                if key:
                    by_key[key] = len(combined)
                combined.append(raw)
    return combined


def _merge_adjacent(invoices: list[NormalizedInvoice]) -> list[NormalizedInvoice]:
    """Merge consecutive segments that turned out to be the same invoice."""
    out: list[NormalizedInvoice] = []
    for inv in invoices:
        prev = out[-1] if out else None
        same = (
            prev is not None
            and inv.invoice_number is not None
            and normalize_invoice_number(prev.invoice_number) == normalize_invoice_number(inv.invoice_number)
            and (
                prev.supplier_name is None
                or inv.supplier_name is None
                or normalize_supplier(prev.supplier_name) == normalize_supplier(inv.supplier_name)
            )
            and prev.page_end is not None
            and inv.page_start is not None
            and inv.page_start == prev.page_end + 1
        )
        if not same or prev is None:
            out.append(inv)
            continue
        for name in INVOICE_FIELDS:
            mine, theirs = getattr(prev, name), getattr(inv, name)
            if mine is None and theirs is not None:
                setattr(prev, name, theirs)
                if name in inv.evidence:
                    prev.evidence[name] = inv.evidence[name]
            elif mine is not None and theirs is not None and mine != theirs:
                prev.alternatives.setdefault(name, [str(mine)])
                prev.alternatives[name].append(str(theirs))
                prev.notes.append(
                    NormalizationNote(field=name, code="CONFLICTING_VALUES", message=f"Conflicting values across pages for {name}")
                )
        offset = len(prev.line_items)
        for li in inv.line_items:
            li.position += offset
            prev.line_items.append(li)
        prev.page_end = inv.page_end
        prev.notes.extend(inv.notes)
    for i, inv in enumerate(out):
        inv.segment_index = i
    return out


@dataclass
class _SegmentRun:
    raws: list[RawInvoice]
    error_code: str | None
    elapsed: float
    provider: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw_responses: list[str] = field(default_factory=list)
    fallback_from: str | None = None
    secondary_raws: list[RawInvoice] = field(default_factory=list)


def _run_segment(provider: ExtractionProvider, segment: Segment, text_method: str, hint: str | None) -> _SegmentRun:
    """Extract one segment (its token windows run in order). Transient errors propagate."""
    settings = get_settings()
    started = time.perf_counter()
    windows = split_for_budget(segment.text_with_markers(), settings.llm_max_input_chars)
    window_results: list[list[RawInvoice]] = []
    usage: dict[str, Any] = {
        "requests": 0,
        "attempts": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "input_chars": 0,
        "windows": len(windows),
    }
    raw_responses: list[str] = []
    for window in windows:
        try:
            result = provider.extract_invoice(ExtractionRequest(document_text=window, text_method=text_method, document_type_hint=hint))
        except PermanentProcessingError as exc:
            logger.warning(
                "segment_extraction_failed", extra={"segment": segment.index, "error_code": exc.code, "provider": provider.provider_name()}
            )
            return _SegmentRun([], exc.code, time.perf_counter() - started, provider.provider_name(), usage)
        window_results.append(result.extraction.invoices)
        usage["requests"] += 1
        usage["attempts"] += result.attempts
        for key in ("prompt_tokens", "completion_tokens", "input_chars"):
            usage[key] += int(result.usage.get(key, 0) or 0)
        if result.raw_response and settings.store_raw_llm_responses:
            raw_responses.append(result.raw_response)
    elapsed = time.perf_counter() - started
    EXTRACTION_DURATION.labels(provider.provider_name()).observe(elapsed)
    return _SegmentRun(_combine_windows(window_results), None, elapsed, provider.provider_name(), usage, raw_responses)


def extract_document(
    pages: list[ExtractionPage],
    provider: ExtractionProvider,
    *,
    document_id: str | None,
    document_type_hint: str | None = None,
    layout_loader: Callable[[int], list[dict[str, Any]]] | None = None,
    fallback: ExtractionProvider | None = None,
    cross_check: bool = False,
    max_workers: int = 1,
) -> DocumentExtraction:
    """Segment → extract (segments in parallel, up to ``max_workers``) → normalize → ground → merge.

    ``fallback`` (the deterministic rules extractor) is used two ways:
    * a segment the primary provider cannot process (permanent error) or in
      which it finds no invoice is taken from the fallback, flagged
      ``EXTRACTION_FALLBACK``;
    * with ``cross_check=True`` the fallback also runs on every segment and
      verified corrections are applied (see ``crosscheck.py``).
    """
    page_texts = [PageText(p.page_number, p.text) for p in pages if p.text and p.text.strip()]
    by_number = {p.page_number: p for p in pages}
    segments: list[Segment] = segment_pages(page_texts)

    def run(segment: Segment) -> _SegmentRun:
        methods = {by_number[p.page_number].method for p in segment.pages}
        text_method = "OCR" if "ocr" in methods else "native PDF text extraction"
        primary = _run_segment(provider, segment, text_method, document_type_hint)
        if fallback is None or not (primary.error_code or cross_check or not primary.raws):
            return primary
        secondary = _run_segment(fallback, segment, text_method, document_type_hint)
        if secondary.error_code:
            return primary
        if primary.error_code or not primary.raws:
            if not secondary.raws:
                return primary
            secondary.fallback_from = primary.error_code or "NO_INVOICE_FROM_PRIMARY"
            secondary.usage = {**primary.usage, "fallback": True}
            return secondary
        primary.secondary_raws = secondary.raws
        return primary

    if max_workers > 1 and len(segments) > 1:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(segments)), thread_name_prefix="extract") as pool:
            runs = list(pool.map(run, segments))
    else:
        runs = [run(segment) for segment in segments]

    usage: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "input_chars": 0,
        "requests": 0,
        "attempts": 0,
        "segments": len(segments),
        "fallback_segments": 0,
    }
    outcomes: list[SegmentOutcome] = []
    normalized: list[NormalizedInvoice] = []
    raw_responses: list[str] = []
    for segment, seg_run in zip(segments, runs, strict=True):
        for key in ("prompt_tokens", "completion_tokens", "input_chars", "requests", "attempts"):
            usage[key] += int(seg_run.usage.get(key, 0) or 0)
        usage["fallback_segments"] += 1 if seg_run.fallback_from else 0
        raw_responses.extend(seg_run.raw_responses)
        grounding_pages = {}
        for p in segment.pages:
            source = by_number[p.page_number]
            lines = source.lines
            if not lines and layout_loader is not None:
                lines = layout_loader(p.page_number)
            grounding_pages[p.page_number] = GroundingPage(page_number=p.page_number, text=source.text, lines=lines, method=source.method)
        confs = [c for p in segment.pages if (c := by_number[p.page_number].ocr_confidence) is not None]
        secondary_invoices = []
        for raw in seg_run.secondary_raws:
            sec = normalize_invoice(raw, segment_index=-1, page_start=segment.page_start, page_end=segment.page_end)
            ground_invoice(sec, raw, grounding_pages, document_id)
            secondary_invoices.append(sec)
        primary_invoices = []
        for raw in seg_run.raws:
            inv = normalize_invoice(raw, segment_index=0, page_start=segment.page_start, page_end=segment.page_end)
            ground_invoice(inv, raw, grounding_pages, document_id)
            primary_invoices.append(inv)
        if secondary_invoices:
            pairs = pair_invoices(primary_invoices, secondary_invoices)
            primary_invoices = [crosscheck_invoice(p, s) if s is not None else p for p, s in pairs]
            usage["cross_checked_invoices"] = usage.get("cross_checked_invoices", 0) + sum(1 for _, s in pairs if s is not None)
        for inv in primary_invoices:
            infer_currency(inv)
            inv.segment_index = len(normalized)
            inv.ocr_confidence = round(sum(confs) / len(confs), 4) if confs else None
            if seg_run.fallback_from:
                inv.notes.append(
                    NormalizationNote(
                        field="__extraction__",
                        code="EXTRACTION_FALLBACK",
                        message=f"Primary extractor failed ({seg_run.fallback_from}); extracted with deterministic rules",
                    )
                )
            normalized.append(inv)
        outcomes.append(
            SegmentOutcome(
                segment_index=segment.index,
                page_start=segment.page_start,
                page_end=segment.page_end,
                windows=int(seg_run.usage.get("windows", 1)),
                invoices=len(seg_run.raws),
                error_code=seg_run.error_code,
                latency_ms=int(seg_run.elapsed * 1000),
                provider=seg_run.provider,
            )
        )

    merged = _merge_adjacent(normalized)
    for inv in merged:
        inv.confidence = heuristic_confidence(inv)
    return DocumentExtraction(
        invoices=merged,
        segments=outcomes,
        usage=usage,
        provider=provider.provider_name(),
        model=provider.model_name(),
        raw_responses=raw_responses,
    )
