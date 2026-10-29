# Tests and test results

Run on 2026-10-29. Raw reports: [`test-results/junit-docker.xml`](test-results/junit-docker.xml),
[`test-results/junit-host.xml`](test-results/junit-host.xml),
[`test-results/host-run.txt`](test-results/host-run.txt) (includes the coverage table).

| Run | Command | Result |
|---|---|---|
| Inside the Docker image (Tesseract installed) | `make test-docker` | **177 passed, 0 failed, 0 skipped** (20.9 s) |
| Host (PostgreSQL, Redis and MinIO via Testcontainers) | `make test` | **176 passed, 1 skipped** (the OCR test needs the Tesseract binary), line coverage **87%** |
| Lint and types | `make lint` | ruff clean, `mypy app` clean (112 files) |
| End-to-end smoke test against the running stack | `make smoke` | 17/17 checks passed |

Integration tests run against real PostgreSQL 17 + pgvector, Redis and
S3/MinIO (no mocks of the database or queue). Background stages are executed
in-process by draining the real transactional outbox, so retries, leases and
idempotency are exercised exactly as in the workers. External services that
cost money or need credentials (Mistral, UploadThing) are replaced by HTTP
doubles that mirror the behaviour verified against the live APIs; the live
behaviour itself is covered by the evaluation run ([evaluation.md](evaluation.md)).

## Coverage of the required areas

| Area (assignment, Task 7) | Tests | What is checked |
|---|---:|---|
| Document processing | `unit/test_extraction.py` (PDF part), `unit/test_preprocessing.py`, `unit/test_fingerprint.py`, `api/test_document_workflows.py` | native PDF text and layout, multi-page and multi-invoice PDFs, continuation pages, encrypted/malformed PDFs, content-signature checks, zip bombs, macros, size limits |
| OCR | `api/test_operations.py::test_scanned_pdf_png_and_tiff_go_through_ocr`, `unit/test_preprocessing.py` | scanned PDF, PNG, multi-page TIFF through Tesseract; deskew, contrast and denoise only when needed; EXIF rotation; decompression bombs; corrupt images |
| Spreadsheet parsing | `unit/test_spreadsheets_and_matching.py` | XLSX header detection below title rows, cell coordinates, formulas never evaluated (missing cached value reported), legacy XLS, CSV encodings/delimiters/BOM, ragged rows, row limits |
| AI extraction | `unit/test_extraction.py`, `unit/test_hosted_provider.py` | ground-truth accuracy, multi-invoice segmentation, grounding flags values not in the source, prompt injection, ambiguous currency not guessed, OCR noise in labels; LLM adapter: strict schema, retries on 429/5xx, no retry on 4xx, schema repair, parallel extraction order, rules fallback, cross-check corrections |
| Validation | `unit/test_validation_rules.py` (incl. Hypothesis property tests) | every rule with exact expected/actual values; tolerance; credit notes; tax only from printed rates; duplicates; property tests: consistent invoices never flagged, any total error above tolerance always flagged |
| API endpoints | `api/test_auth.py`, `api/test_document_workflows.py`, `api/test_operations.py`, `api/test_uploadthing_storage.py` | auth and token rotation, roles, upload (multipart, raw body, direct-to-UploadThing), status, results, search (keyword, semantic, hybrid, filters, empty query), corrections with optimistic locking, approval rules, comparison, reconciliation, CSV export, idempotency keys, rate limits, health, metrics |
| Failure scenarios | `workers/test_reliability.py` | duplicate delivery, worker crash mid-batch, lost queue messages, broker outage, transient error retry, retries exhausted → dead letter → replay, malformed/encrypted PDF, one corrupt page in a long PDF, cancellation, SQL-error classification, many review tasks in one document (prepared-statement regression), storage outage |
| Security | `security/test_tenant_isolation.py`, `unit/test_security_and_misc.py` | every resource returns 404 across tenants, including all search modes; DB-level composite FK; JWT tampering and `alg=none`; Argon2; log redaction |
| Database | `integration/test_migrations.py` | migrations match models, upgrade/downgrade round trip, HNSW/GIN/partial indexes, `NUMERIC` money, append-only audit log |

Tests per module (Docker run): unit 130 (money/dates/text 33, extraction 23,
validation 16, spreadsheets+matching 10, hosted LLM adapter 9, state machine 9,
fingerprinting 7, security 7, UploadThing client 6, preprocessing 5, process
entry points 5) · API 29 · workers/reliability 13 · security 3 · migrations 2.

## Lowest-covered modules (host run)

`parsing/ocr_service.py` 45% and `parsing/pdf_parser.py` 58% are lower on the
host only because the OCR branches need Tesseract; they run in the Docker
suite. `workers/dispatcher.py` 61% (the long-running loop and signal handling
are not unit-tested; publishing is). `extraction/providers/hosted.py` 69%
(Redis semaphore paths; the HTTP behaviour is covered by mocked tests and the
live evaluation).
