"""Prometheus metrics. Labels are bounded: never document/user IDs."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("docintel_http_requests_total", "HTTP requests", ["method", "route", "status_class"])
HTTP_LATENCY = Histogram(
    "docintel_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
HTTP_ERRORS = Counter("docintel_http_errors_total", "HTTP 5xx responses", ["route"])

QUEUE_BACKLOG = Gauge("docintel_queue_backlog", "Messages waiting in broker queue", ["queue"])
ACTIVE_JOBS = Gauge("docintel_active_jobs", "Non-terminal processing runs", ["job_type"])

STAGE_DURATION = Histogram(
    "docintel_stage_duration_seconds",
    "Pipeline stage task duration",
    ["task_type", "outcome"],
    buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600, 1800),
)
DOCUMENT_PROCESSING_DURATION = Histogram(
    "docintel_document_processing_duration_seconds",
    "End-to-end document processing duration",
    ["file_kind", "final_state"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600, 7200),
)
PAGES_PROCESSED = Counter("docintel_pages_processed_total", "Pages processed", ["page_type", "method"])
OCR_PAGES = Counter("docintel_ocr_pages_total", "Pages sent through OCR", ["engine"])
OCR_FAILURES = Counter("docintel_ocr_failures_total", "OCR failures", ["engine", "reason"])
EXTRACTION_DURATION = Histogram(
    "docintel_extraction_duration_seconds",
    "Invoice extraction duration per segment",
    ["provider"],
    buckets=(0.05, 0.1, 0.5, 1, 2, 5, 10, 20, 60, 120),
)
LLM_REQUESTS = Counter("docintel_llm_requests_total", "LLM requests", ["provider", "outcome"])
LLM_RETRIES = Counter("docintel_llm_retries_total", "LLM retries", ["provider", "reason"])
LLM_TOKENS = Counter("docintel_llm_tokens_total", "LLM token usage", ["provider", "kind"])
VALIDATION_ISSUES = Counter("docintel_validation_issues_total", "Validation issues raised", ["rule_code", "severity"])
JOBS_FAILED = Counter("docintel_jobs_failed_total", "Failed processing runs", ["job_type", "error_code"])
JOBS_REPROCESSED = Counter("docintel_jobs_reprocessed_total", "Retried/replayed runs", ["job_type"])
DOCUMENTS_COMPLETED = Counter("docintel_documents_completed_total", "Documents reaching a terminal state", ["final_state"])
TASK_RETRIES = Counter("docintel_task_retries_total", "Celery task retries", ["task_type", "error_code"])
OUTBOX_PUBLISHED = Counter("docintel_outbox_published_total", "Outbox events published", ["event_type"])
OUTBOX_FAILURES = Counter("docintel_outbox_publish_failures_total", "Outbox publish failures")
OUTBOX_LAG = Histogram(
    "docintel_outbox_lag_seconds",
    "Delay between outbox event creation and publication",
    buckets=(0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 300),
)
RECOVERY_ACTIONS = Counter("docintel_recovery_actions_total", "Maintenance recovery actions", ["action"])
SEARCH_DURATION = Histogram(
    "docintel_search_duration_seconds",
    "Search request duration",
    ["mode"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
DEPENDENCY_UP = Gauge("docintel_dependency_up", "Dependency health check (1=up)", ["dependency"])
