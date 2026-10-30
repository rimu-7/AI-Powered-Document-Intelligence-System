Production-Grade FastAPI Backend — Complete Engineering Blueprint
AI-Powered Document Intelligence & Financial Verification Platform · Senior AI Engineer Technical Assignment
I recommend building this as a production-oriented, modular, event-driven document intelligence platform, rather than a basic FastAPI CRUD project with an OCR endpoint.
Your backend should demonstrate the engineering skills that distinguish a senior AI engineer: distributed processing, reliable AI extraction, document provenance, financial correctness, security, database architecture, observability, scalability, and operational recovery.
The goal is to make a reviewer see not just that your application works, but that you understand how to build, deploy, scale, debug, and maintain a real document-processing system.
1.
Architecture decisions
Recommended architecture
Production-oriented
React / Next.js Client
Upload · Review · Compare · Search
Ingress / Reverse Proxy
TLS · Rate limits · Request size limits
FastAPI Application
Auth · Documents · Jobs · Invoices · Validation · Comparison · Search
PostgreSQL Outbox + Redis / Celery
Durable job dispatch · Multiple specialized queues
Preprocessing
File validation · Page splitting
OCR Workers
PDF · Image · Table extraction
AI Workers
LLM · Structured information
Validation Workers
Financial rules · Cross-verification
Search Workers
Embeddings · Indexing
Maintenance
Retries · Cleanup · Reconciliation
PostgreSQL
pgvector
S3 / MinIO
File storage
Monitoring
OTel / Metrics
Technology stack
Layer
Recommended stack
Language
Python 3.12+
API framework
FastAPI
Validation and settings
Pydantic v2
ORM
SQLAlchemy 2.x
Database migrations
Alembic
Primary database
PostgreSQL + pgvector
Cache and messaging
Redis
Background execution
Celery
Object storage
S3-compatible MinIO
PDF parsing
PyMuPDF
OCR
PaddleOCR, Tesseract fallback
Image handling
Pillow / OpenCV
Spreadsheets
openpyxl, pandas, xlrd
AI extraction
Provider-agnostic structured-output LLM adapter
Vector embeddings
Configurable embedding provider
Authentication
JWT + refresh-token rotation
Containerization
Docker + Docker Compose
Orchestration
Kubernetes + Helm
Observability
OpenTelemetry, Prometheus, Grafana
Testing
pytest, pytest-asyncio, HTTPX, Testcontainers
CI/CD
GitHub Actions
Dependency management
uv with lockfile
Why this architecture? It keeps the synchronous API lightweight and moves expensive OCR, AI inference, and indexing into independently scalable workers. It also avoids unnecessary microservice complexity: one well-structured Python codebase can power multiple API and worker deployments.
FastAPI currently recommends building your own container image rather than using the deprecated tiangolo/uvicorn-gunicorn-fastapi image, especially when Kubernetes handles replication.
FastAPI
2. Critical engineering decisions that will make your project stand out
These are the requirements I would insist Claude Code implements.
Concern
Required design decision
1,000-page PDFs
Page-batch processing, checkpointing, bounded memory
Reliability
Durable PostgreSQL job state and transactional outbox
Worker crashes
At-least-once execution with idempotent tasks
Financial accuracy
Decimal, never binary floats for money
AI hallucinations
Nullable fields, source evidence, confidence, review
Scanned documents
OCR routing and image preprocessing
PDF–Excel matching
Normalized comparison with traceable evidence
Duplicate handling
SHA-256 file hashes and business-key duplicate detection
Search
PostgreSQL full-text search plus pgvector
Security
Tenant isolation, RBAC, safe upload handling
Scale
Separate Celery queues, resource limits, autoscaling
Corrections
Immutable extraction revisions and human audit trail
Observability
Structured logs, traces, metrics, correlation IDs
Deployment
Reproducible Docker Compose and Kubernetes Helm chart
Evaluation
Actual measured metrics, not invented performance claims
A particularly important detail: Redis/Celery delivery is not guaranteed to be exactly once. Redis visibility timeouts can cause tasks to be redelivered, so your system must be safe when the same task executes more than once.
Celery 5.6.3 documentation
Likewise, pgvector's HNSW indexing accelerates approximate vector search but introduces recall and filtering trade-offs. Your search implementation should account for these rather than treating vector search as a black box.
GitHub
3. Backend modules
I would organize the application into these bounded modules:
1. Identity and tenancy — users, organizations, roles, access tokens, permissions.
2. Document management — uploads, file metadata, storage, hashing, versioning.
3. Document parsing — PDF, OCR, images, spreadsheets, text, tables, page evidence.
4. AI extraction — invoice field schemas, prompts, providers, confidence, validation.
5. Financial verification — arithmetic checks, duplicates, cross-document reconciliation.
6. Job orchestration — Celery tasks, queues, retries, recovery, progress.
7. Human review — corrections, approvals, revision history, audit logs.
8. Search and retrieval — keyword search, semantic search, hybrid ranking.
9. Administration and observability — health endpoints, metrics, operational reporting.
Now the most useful part: a comprehensive prompt you can give directly to Claude Code.
4. Master Claude Code prompt
This prompt is designed for Claude Code running inside an actual project directory with terminal, file-editing, and Docker access.
It instructs Claude to build a complete repository, execute tests, fix failures, and produce a verification report instead of only generating boilerplate.
MASTER ENGINEERING PROMPT — DOCINTEL AI
ROLE AND MISSION
Act as a Principal AI Engineer, Staff Backend Engineer, Distributed Systems Architect, Database Architect, DevSecOps Engineer, and Senior QA Engineer.
You are responsible for architecting, implementing, integrating, testing, documenting, and preparing for deployment a complete production-oriented backend named:
DocIntel AI — Enterprise Document Intelligence & Financial Verification Platform
This is a high-stakes Senior AI Engineer technical assignment.
The system must ingest large volumes of business documents, extract financial information accurately, validate results, reconcile financial records across document formats, support human review, and provide secure REST APIs.
Your output must be real, executable, maintainable software—not illustrative pseudocode, disconnected snippets, scaffolding without implementation, or placeholder functionality.
You have access to this repository and may use the terminal, filesystem, code execution, package managers, and Docker where available.
Your mission is to implement the complete backend, run meaningful checks, fix defects, and leave the repository in the best working state possible.
Do not stop after producing a plan.
Do not ask me to approve architecture decisions that have already been specified here.
Do not claim production readiness, successful tests, or measured performance without evidence.
If a dependency, API key, GPU, Kubernetes cluster, or external resource is unavailable, implement a working local alternative where appropriate, preserve the production interface, and document exactly what could not be verified.
Work autonomously through the entire implementation.

1. BUSINESS REQUIREMENTS
The company receives thousands of financial documents daily, including:
- Digital PDF invoices
- Scanned PDF invoices
- Receipts
- JPG images
- PNG images
- TIFF images, including multipage TIFF
- XLSX workbooks
- Legacy XLS workbooks
- CSV datasets
- Large PDFs, potentially approximately 1,000 pages
Employees currently extract invoice data manually and cross-check financial information between PDFs and spreadsheets.
Implement a system that automates:
1. File ingestion and secure storage.
2. Document classification and parsing.
3. Native PDF text extraction.
4. OCR for scanned pages and images.
5. Spreadsheet and CSV parsing.
6. Structured invoice information extraction.
7. Financial calculation validation.
8. Duplicate invoice detection.
9. PDF-to-PDF comparison.
10. PDF-to-Excel comparison.
11. Document search and semantic retrieval.
12. Human correction and approval.
13. Background processing and retries.
14. Processing history and auditing.
15. Evaluation and performance reporting.
The system must provide a documented REST API suitable for a React or Next.js frontend.
Backend implementation is the primary deliverable. Do not build a frontend unless the backend is complete and explicitly requested separately.

2. IMPLEMENTATION RULES
Follow these mandatory rules throughout development.
1. Implement actual functionality. No TODO-only services or empty endpoint handlers.
2. Use strict typing wherever practical.
3. Prefer straightforward, testable code over unnecessary abstractions.
4. Follow separation of concerns and dependency inversion.
5. Use a modular monolith architecture with independently deployable API and worker processes.
6. Avoid premature microservices.
7. Every feature must have a clear API contract, data model, service implementation, and tests.
8. Use asynchronous I/O in the API where appropriate.
9. Never execute expensive OCR or LLM extraction in an HTTP request handler.
10. Make background jobs idempotent.
11. Do not store original document binaries in PostgreSQL or Redis.
12. Use migrations, never runtime table creation as a production initialization strategy.
13. Never log access tokens, secrets, confidential document contents, or raw financial data unnecessarily.
14. Never trust uploaded filenames, MIME types, external document text, LLM responses, or user-supplied identifiers.
15. Never fabricate extracted data, AI confidence, benchmark results, or test outcomes.
16. Preserve references to the source document, page, table, and row whenever available.
17. Use UTC internally; preserve original dates and timezone information where relevant.
18. Use Decimal for monetary calculations.
19. Use explicit service timeouts, resource limits, retry policies, and structured error handling.
20. Ensure the application starts with one documented Docker Compose command after initial configuration.
21. Produce Kubernetes deployment artifacts as a separate production deployment option.
22. Keep all configuration in typed environment variables.
23. Use reproducible, locked dependencies and pinned container versions or digests.
24. Never modify an unrelated project or delete existing user data.
25. Use stable libraries and verify compatibility before locking versions.
26. Execute commands and inspect errors rather than assuming they succeeded.
27. Do not silently replace required functionality with mock implementations.
28. Clearly distinguish verified functionality from unverified functionality in the final report.

3. REQUIRED TECHNOLOGY STACK
Use the following:
Language:
- Python 3.12 or a newer stable, dependency-compatible release
API:
- FastAPI
- Pydantic v2
- pydantic-settings
- Uvicorn
- HTTPX
Database:
- PostgreSQL
- SQLAlchemy 2.x with typed ORM models
- asyncpg for async API database access
- psycopg for appropriate synchronous worker access if needed
- Alembic for migrations
- pgvector extension
Queue:
- Celery
- Redis as Celery broker
- Redis for suitable cache and rate-limit data
- PostgreSQL as the authoritative source of business job state
File storage:
- S3-compatible object storage
- MinIO for local Docker Compose development
- Configurable S3 implementation for production
Document processing:
- PyMuPDF for native PDF extraction
- Pillow
- OpenCV where image preprocessing materially helps
- PaddleOCR as the preferred OCR implementation if compatible
- Tesseract as a configurable fallback
- pandas
- openpyxl
- xlrd for legacy XLS
- Python csv standard library where useful
AI:
- Provider-neutral extraction interface
- Configurable hosted LLM adapter
- Optional OpenAI-compatible provider implementation
- Deterministic local fixture adapter for testing
- Strict Pydantic structured-output validation
- Embedding provider abstraction
- Configurable local embedding implementation for development
Search:
- PostgreSQL full-text search
- pgvector
- Hybrid ranking
Authentication:
- Secure JWT access tokens
- Rotating refresh tokens
- Password hashing using Argon2
- Role-based authorization
Testing:
- pytest
- pytest-asyncio
- pytest-cov
- HTTPX ASGI tests
- Testcontainers where feasible
- Hypothesis for financial/property-based tests
- Ruff
- mypy or pyright
Infrastructure:
- Multi-stage Dockerfile
- Docker Compose
- Kubernetes
- Helm
- GitHub Actions
Observability:
- Structured JSON logging
- Prometheus metrics
- OpenTelemetry tracing
- Optional Grafana dashboards
Avoid adding tools that do not have a clear purpose.

4. REPOSITORY ORGANIZATION
Create a maintainable project structure similar to:
docintel-ai/
app/
main.py
core/
config.py
security.py
logging.py
exceptions.py
middleware.py
database.py
permissions.py
telemetry.py
api/
v1/
router.py
auth.py
users.py
documents.py
jobs.py
invoices.py
validations.py
comparisons.py
corrections.py
search.py
reviews.py
admin.py
health.py
modules/
identity/
models.py
schemas.py
repository.py
service.py
documents/
models.py
schemas.py
repository.py
service.py
upload_service.py
storage.py
fingerprint.py
parsing/
schemas.py
router.py
pdf_parser.py
image_parser.py
ocr_service.py
preprocessing.py
spreadsheet_parser.py
csv_parser.py
table_extractor.py
provenance.py
extraction/
schemas.py
service.py
prompts.py
normalization.py
confidence.py
providers/
base.py
hosted.py
fixture.py
validation/
schemas.py
rules.py
service.py
financial.py
duplicates.py
comparison/
schemas.py
service.py
matching.py
pdf_pdf.py
pdf_spreadsheet.py
reconciliation.py
reviews/
models.py
schemas.py
service.py
repository.py
search/
schemas.py
indexing.py
embeddings.py
keyword.py
semantic.py
hybrid.py
jobs/
models.py
schemas.py
orchestration.py
lifecycle.py
progress.py
recovery.py
outbox.py
auditing/
models.py
service.py
workers/
celery_app.py
preprocess_tasks.py
ocr_tasks.py
extract_tasks.py
validation_tasks.py
comparison_tasks.py
indexing_tasks.py
maintenance_tasks.py
shared/
enums.py
pagination.py
money.py
identifiers.py
utilities.py
alembic/
versions/
tests/
unit/
integration/
api/
workers/
security/
performance/
fixtures/
conftest.py
evaluation/
datasets/
scripts/
results/
scripts/
bootstrap.py
create_admin.py
generate_demo_data.py
smoke_test.py
benchmark.py
infra/
docker/
helm/
docintel/
Chart.yaml
values.yaml
templates/
monitoring/
docs/
architecture.md
database.md
api.md
processing-pipeline.md
security.md
deployment.md
operations.md
evaluation.md
ai-disclosure.md
architecture.mmd
.github/
workflows/
ci.yml
image.yml
Dockerfile
compose.yaml
compose.dev.yaml
.dockerignore
.env.example
.gitignore
pyproject.toml
uv.lock
alembic.ini
Makefile
README.md
This structure is a guideline, not an excuse to create unnecessary files.
Keep related code cohesive and avoid circular dependencies.
Use a clear domain/service/repository pattern.
Every top-level module must have meaningful tests.

5. MULTI-TENANCY, USERS, AND AUTHORIZATION
Implement organization-scoped multi-tenancy from the beginning.
Entities:
organizations:
- id
- name
- slug
- status
- created_at
- updated_at
users:
- id
- organization_id
- email
- password_hash
- full_name
- role
- is_active
- created_at
- updated_at
refresh_sessions:
- id
- user_id
- token_hash
- family_id
- expires_at
- revoked_at
- created_at
- last_used_at
Roles:
- ADMIN
- ANALYST
- REVIEWER
- VIEWER
Authorization requirements:
ADMIN:
- Organization administration
- User management
- All organization-scoped document actions
- Operational administration within authorized scope
ANALYST:
- Upload
- Process
- Search
- Compare documents
- Inspect extraction data
REVIEWER:
- All analyst permissions
- Correct extracted fields
- Approve or reject reviews
VIEWER:
- Read-only access to permitted resources
Security requirements:
- Organization IDs must be derived from authenticated identity.
- Do not trust client-supplied organization IDs as authorization evidence.
- Use explicit organization filters in every relevant database query.
- Prevent cross-tenant lookup by document ID, job ID, invoice ID, embedding ID, and comparison ID.
- Test tenant isolation, including semantic search.
- Return appropriate authorization errors without revealing other tenants' document existence.
- Use short-lived JWT access tokens.
- Implement refresh-token rotation and reuse detection.
- Store refresh-token hashes, not plaintext tokens.
- Support logout and session revocation.
- Prevent disabled users from performing authorized actions.
- Use secure password hashing and constant-time verification where appropriate.
- Do not provide default production credentials.
Bootstrap development users through an explicitly documented development-only command.

6. DOCUMENT UPLOAD AND STORAGE
Implement secure document ingestion.
Supported extensions:
- .pdf
- .jpg
- .jpeg
- .png
- .tif
- .tiff
- .xlsx
- .xls
- .csv
Upload features:
- Multipart upload for multiple files.
- Streaming uploads with bounded memory.
- Configurable per-file size limit.
- Configurable request size limit.
- Configurable batch file-count limit.
- Configurable maximum pages and spreadsheet rows.
- Safe normalized filenames for display only.
- UUID-generated internal storage keys.
- SHA-256 checksum.
- File size and detected MIME type.
- Content-signature validation.
- Safe handling of malformed content.
- Configurable antivirus scanning interface, with a working supported scanning integration or a clearly documented security limitation.
- Archive and zip-bomb defenses where applicable to Office formats.
- No user-controlled filesystem paths.
- Restrict access to original files through authorization.
- Block unsafe file types.
- Restrict outbound object access.
- Do not make uploaded files publicly accessible.
- Enforce storage quotas.
- Preserve original files without overwriting.
- Handle partial upload cleanup.
- Support repeat submissions and idempotency keys.
For large uploads, prefer a configurable streaming approach; support multipart uploads for the assignment and optionally add presigned object-storage upload initialization/completion for larger deployments.
Implement secure object download through an authenticated API endpoint or short-lived scoped presigned URL.
Separate:
- Original document storage
- Temporary processing artifacts
- OCR results
- Derived page images
- Evaluation fixtures
Track all created storage objects so cleanup can occur safely.
Use separate object key prefixes per tenant.
Do not rely on object key prefixes alone as authorization.

7. DOCUMENT DATABASE MODELS
Implement normalized PostgreSQL models with UUID primary keys and appropriate indexes.
Required entities:
documents:
- id
- organization_id
- uploaded_by
- original_filename
- content_type
- file_extension
- file_size_bytes
- sha256
- storage_key
- document_type
- page_count
- sheet_count
- status
- current_processing_run_id
- created_at
- updated_at
- deleted_at
document_pages:
- id
- document_id
- page_number
- page_type
- text_storage_key or bounded extracted_text
- character_count
- ocr_engine
- processing_status
- metadata_json
- created_at
document_tables:
- id
- document_id
- page_id nullable
- sheet_name nullable
- table_index
- normalized_data_json or object storage reference
- row_count
- column_count
- created_at
document_chunks:
- id
- organization_id
- document_id
- page_id nullable
- chunk_index
- text
- source_reference_json
- embedding
- embedding_model
- created_at
processing_runs:
- id
- organization_id
- document_id
- job_type
- state
- attempt_number
- pages_total
- pages_completed
- pages_failed
- progress_percent
- started_at
- completed_at
- error_code
- sanitized_error_message
- created_at
- updated_at
processing_tasks:
- id
- processing_run_id
- page_start nullable
- page_end nullable
- task_type
- task_state
- attempt_count
- idempotency_key
- lease_expires_at
- last_error_code
- created_at
- updated_at
outbox_events:
- id
- event_type
- aggregate_id
- payload_json
- published_at
- attempt_count
- created_at
invoice_records:
- id
- organization_id
- document_id
- extraction_run_id
- invoice_number
- invoice_date
- supplier_name
- supplier_tax_id nullable
- customer_name
- currency
- subtotal
- tax_amount
- total_amount
- extraction_confidence nullable
- extraction_status
- source_evidence_json
- created_at
- updated_at
invoice_line_items:
- id
- invoice_record_id
- position
- description
- quantity
- unit_price
- discount_amount nullable
- tax_amount nullable
- line_total
- source_evidence_json
extraction_runs:
- id
- document_id
- organization_id
- provider
- model_name
- prompt_version
- schema_version
- extraction_revision
- raw_result_storage_key nullable
- normalized_result_json
- usage_json
- status
- created_at
validation_issues:
- id
- organization_id
- document_id
- invoice_record_id nullable
- rule_code
- severity
- field_path
- expected_value_json nullable
- actual_value_json nullable
- source_evidence_json
- message
- resolution_status
- created_at
- resolved_at nullable
document_comparisons:
- id
- organization_id
- left_document_id
- right_document_id
- comparison_type
- matching_strategy
- status
- summary_json
- created_by
- created_at
comparison_findings:
- id
- comparison_id
- field_name
- left_value_json
- right_value_json
- difference_json
- status
- evidence_json
review_actions:
- id
- organization_id
- document_id
- invoice_record_id nullable
- reviewer_id
- action_type
- field_path nullable
- old_value_json nullable
- new_value_json nullable
- reason
- created_at
audit_events:
- id
- organization_id
- actor_id nullable
- action
- resource_type
- resource_id
- metadata_json
- created_at
Additional required design:
- Add appropriate unique constraints and foreign keys.
- Index organization_id with common query columns.
- Add partial indexes where justified.
- Add full-text search indexes.
- Add vector indexes using pgvector.
- Add indexes for processing status and created_at.
- Avoid oversized JSON blobs in frequently queried tables.
- Put large raw OCR text and binary artifacts into object storage when appropriate.
- Preserve the ability to find the exact source page or spreadsheet row.
- Do not store financial amounts as floats.
- Use NUMERIC with adequate precision and explicit scaling policies.
- Define retention and soft-deletion behavior.
- Ensure tenant-consistent foreign-key relationships through appropriate constraints and application checks.
- Create real Alembic migrations.
Document the entity relationships and indexing choices.

8. DOCUMENT PROCESSING PIPELINE
Implement an extensible ingestion pipeline.
Workflow:
UPLOAD
→ SECURITY CHECK
→ FILE IDENTIFICATION
→ METADATA EXTRACTION
→ PAGE OR SHEET DISCOVERY
→ TEXT EXTRACTION / OCR
→ DOCUMENT NORMALIZATION
→ CLASSIFICATION
→ AI EXTRACTION
→ FINANCIAL VALIDATION
→ SEARCH INDEXING
→ COMPLETION OR MANUAL REVIEW
All stages must be observable and recoverable.
8.1 PDF Processing
Use PyMuPDF to:
- Validate PDF structure.
- Discover page count.
- Extract native text.
- Extract useful layout metadata.
- Extract page-level tables where feasible.
- Detect image-heavy or text-poor pages.
- Render pages to images only when needed.
- Preserve page numbering.
- Support PDFs up to the configured limit, including approximately 1,000 pages.
- Handle password-protected PDFs gracefully.
- Distinguish malformed PDFs from transient processing errors.
Do not OCR every page unconditionally.
Implement page classification using native text content, density, image coverage, and extraction quality heuristics.
Route digitally readable pages through native extraction.
Route scanned or insufficient-quality pages through OCR.
Allow OCR fallback when native extraction produces unusable content.
Use page batches, with an initial configurable batch size such as 10 pages.
Benchmark and adjust batch size rather than assuming it is optimal.
Do not load every rendered page of a 1,000-page PDF into memory simultaneously.
Implement checkpointing so successfully processed pages do not need to be repeated after a worker failure.
Support documents containing multiple invoices.
Do not assume one PDF always equals one invoice.
Represent multiple extracted invoice records per document when needed.
8.2 OCR
Create an OCR interface:
OCRProvider:
- recognize(image)
- recognize_batch(images)
- healthcheck()
- provider_name()
Implement configurable providers:
- PaddleOCR
- Tesseract fallback
Support:
- CPU operation
- Optional GPU configuration
- Image orientation handling
- Deskewing
- Contrast improvement
- Noise reduction
- Resolution normalization
- Bounding boxes
- Page-level OCR metadata
- OCR confidence where the provider supports it
Never treat an OCR engine's confidence score as calibrated probability of financial correctness.
Apply preprocessing conditionally to avoid degrading already readable images.
Maintain the original image.
Add OCR timeouts and bounded resource use.
8.3 TIFF and Image Processing
Support:
- JPG
- JPEG
- PNG
- Single-page TIFF
- Multipage TIFF
Validate image dimensions.
Reject or safely handle decompression bombs.
Handle EXIF orientation.
Extract text with the configured OCR engine.
Preserve page references for multipage TIFF.
8.4 XLSX, XLS and CSV Processing
For XLSX:
- Parse all supported worksheets.
- Preserve worksheet names.
- Preserve row and column coordinates.
- Distinguish formulas from cached values.
- Do not execute spreadsheet formulas or macros.
- Report missing cached formula values.
- Handle merged cells using explicit documented logic.
- Handle empty rows.
- Detect invoice tables using header matching and configurable mapping rules.
For XLS:
- Use xlrd or another compatible parser.
- Handle unsupported or malformed files clearly.
For CSV:
- Detect common encodings with configurable fallback.
- Support UTF-8 and UTF-8 BOM.
- Support configurable delimiters.
- Handle quoted values and escaped characters.
- Handle inconsistent row lengths.
- Prevent spreadsheet formula injection in any CSV export.
- Validate expected columns.
For large spreadsheets:
- Prefer streaming/read-only parsing.
- Bound row-processing memory.
- Store row references and relevant normalized data.
- Do not convert an entire massive workbook into one LLM prompt.
Use deterministic parsing when spreadsheet headers and data structures are recognizable.
Use AI-assisted interpretation only for ambiguous layouts.

9. DOCUMENT CLASSIFICATION
Implement a deterministic-first classification system.
Document types:
- INVOICE
- RECEIPT
- CREDIT_NOTE
- FINANCIAL_STATEMENT
- SPREADSHEET_REGISTER
- UNKNOWN
Use:
1. File characteristics.
2. Header keywords.
3. Layout signals.
4. Optional LLM classification for uncertain cases.
Store:
- Classification result
- Method
- Confidence when available
- Classification version
- Review requirement
Do not pretend unsupported documents are valid invoices.
Unrecognized document types must remain searchable and reviewable.

10. AI INFORMATION EXTRACTION
Implement a production-oriented extraction service.
Required invoice fields:
- invoice_number
- invoice_date
- supplier_name
- customer_name
- subtotal
- tax_amount
- total_amount
- currency
- line_items
Additional useful optional fields:
- purchase_order_number
- payment_due_date
- supplier_address
- customer_address
- tax_identifier
- discount_amount
- payment_reference
Use strict Pydantic schemas.
Example structured output:
{
"invoice_number": "INV-2026-001",
"invoice_date": "2026-10-28",
"supplier_name": "ABC Trading Ltd",
"customer_name": "Example Corporation",
"currency": "USD",
"subtotal": "1000.00",
"tax_amount": "100.00",
"total_amount": "1100.00",
"line_items": [
{
"description": "Office Equipment",
"quantity": "2",
"unit_price": "500.00",
"line_total": "1000.00"
}
]
}
The example above is a schema illustration, not an actual extraction result.
10.1 Extraction Rules
- Never invent missing fields.
- Use null for unavailable information.
- Never substitute a mathematically inferred value for an extracted source value without explicitly marking it as derived.
- Preserve raw extracted values where useful.
- Normalize dates using deterministic rules.
- Normalize currencies using ISO 4217 codes when identifiable.
- Handle ambiguous currency symbols conservatively.
- Handle international decimal separators.
- Handle negative amounts and credit notes.
- Handle multi-line item descriptions.
- Preserve source evidence.
- Flag uncertain values.
- Support multiple invoices in one document.
- Handle conflicting values by preserving alternatives and marking uncertainty.
- Validate the AI output against Pydantic schemas.
- Do not silently discard extraction errors.
10.2 Provider Interface
Define:
ExtractionProvider:
- extract_invoice(...)
- classify_document(...)
- provider_name()
- healthcheck()
Use a provider-neutral adapter interface.
Support a configured hosted LLM provider with strict structured output.
Use bounded timeouts, retry policies, and request concurrency limits.
Do not retry every failure indiscriminately.
Retry transient errors such as provider throttling and recoverable service failures.
Do not retry invalid credentials or irrecoverable schema errors indefinitely.
Use prompt versioning.
Track:
- Provider
- Model
- Prompt version
- Schema version
- Input size
- Token usage where available
- Latency
- Attempt count
- Cost estimate when available
- Extraction status
Avoid storing sensitive raw prompts unnecessarily.
10.3 Evidence Grounding
Every extracted non-null field should include source evidence where possible.
Evidence structure:
- document_id
- page_number or sheet_name
- row_number when applicable
- supporting_text
- bounding_box when available
- extraction_method
The reviewer must be able to trace a field back to its source.
If evidence is missing, mark the field as weakly supported rather than inventing evidence.
10.4 Long Documents
Never send all 1,000 pages to one LLM request.
Implement:
- Document segmentation
- Invoice-boundary detection
- Candidate-page selection
- Token-aware chunking
- Per-invoice extraction
- Deterministic result aggregation
- Duplicate candidate merging
- Cross-page line-item handling
- Provenance preservation
Handle continuation pages without assuming every page starts a new invoice.
Keep the entire document searchable, even if only selected pages are necessary for invoice extraction.
10.5 Prompt Injection Defense
Uploaded documents are untrusted data.
Instructions embedded in documents must not override system instructions or extraction schemas.
Never allow extracted document content to:
- Execute shell commands
- Access application secrets
- Modify authorization
- Call arbitrary tools
- Override business validation rules
- Trigger unauthorized external requests
Use schema validation and controlled provider adapters.

11. FINANCIAL VALIDATION ENGINE
Implement deterministic financial validation.
Do not use an LLM as the final authority for calculations.
Use Decimal and configurable currency precision.
Rules:
REQUIRED_FIELD_MISSING:
- Check mandatory invoice fields.
INVALID_DATE:
- Reject malformed dates.
- Apply configurable policy for future dates.
INVALID_CURRENCY:
- Detect unknown or ambiguous currency codes.
LINE_TOTAL_MISMATCH:
- Compare quantity × unit_price against line_total, accounting for discounts and tax treatment.
SUBTOTAL_MISMATCH:
- Reconcile line items with subtotal.
TAX_MISMATCH:
- Validate disclosed taxes against applicable source information and configured tax rules.
- Do not invent tax percentages.
TOTAL_MISMATCH:
- Verify subtotal, discounts, charges, taxes, and total under the invoice's documented arithmetic model.
NEGATIVE_AMOUNT:
- Flag unexpected negative values while supporting legitimate credit notes.
DUPLICATE_INVOICE:
- Detect repeated supplier + invoice number within an organization.
- Normalize supplier identity cautiously.
- Use business rules to distinguish legitimate repeats and revisions.
DUPLICATE_FILE:
- Detect matching SHA-256 hashes.
CURRENCY_CONFLICT:
- Detect inconsistent currency labels.
UNSUPPORTED_CALCULATION:
- Flag calculations that cannot be verified due to missing data.
LOW_EXTRACTION_CONFIDENCE:
- Require human review when appropriate.
Severity levels:
- INFO
- WARNING
- ERROR
- CRITICAL
Validation outcome:
- PASSED
- PASSED_WITH_WARNINGS
- REQUIRES_REVIEW
- FAILED
Important accounting rules:
- Different currencies must never be compared without an explicit conversion policy.
- Use configurable absolute tolerance for rounding.
- Do not use percentage tolerance to hide substantial financial mismatches.
- Treat tax-inclusive and tax-exclusive line items differently.
- Handle multiple tax rates.
- Handle discounts and shipping charges.
- Support credit notes.
- Store the exact mathematical reason for every discrepancy.
- Never overwrite source totals with recomputed totals.
Return machine-readable validation codes and human-readable explanations.
Use property-based testing for numerical invariants.

12. PDF-TO-PDF COMPARISON
Implement document comparison independent of the frontend.
Endpoint input:
- left_document_id
- right_document_id
- comparison_type
- selected invoice records when necessary
Capabilities:
- Compare invoice numbers.
- Compare supplier and customer.
- Compare dates.
- Compare subtotal.
- Compare tax.
- Compare total.
- Compare currency.
- Compare line items.
- Compare matching document entities.
- Highlight mismatches.
- Record missing and ambiguous fields.
- Preserve evidence from both source documents.
Support comparisons involving multiple invoice records.
Do not arbitrarily compare the first invoice in one document with the first invoice in another.
Implement matching logic with:
- Invoice-number normalization
- Supplier matching
- Date constraints
- Currency compatibility
- Optional fuzzy matching
Return:
- MATCH
- MISMATCH
- MISSING_LEFT
- MISSING_RIGHT
- AMBIGUOUS
- NOT_COMPARABLE
Fuzzy matching must not silently convert uncertain matches into authoritative financial matches.
Store comparison results and evidence.

13. PDF-TO-EXCEL / CSV RECONCILIATION
This is a critical feature.
Support uploading:
- Invoice PDFs
- Accounting XLSX files
- XLS files
- CSV registers
Implement configurable mapping from spreadsheet columns to invoice fields.
Example mappings:
invoice_no → invoice_number
vendor → supplier_name
invoice_total → total_amount
tax_value → tax_amount
Provide automatic header suggestions and user-confirmed mapping configuration.
Comparison workflow:
1. Extract invoice records from PDFs.
2. Normalize spreadsheet records.
3. Identify candidate matches.
4. Match using invoice number and supplier identity.
5. Check currency compatibility.
6. Reconcile dates and financial values.
7. Detect duplicates and unmatched records.
8. Store row-level comparison outcomes.
9. Return a structured reconciliation summary.
Support these cases:
- One PDF invoice matches one spreadsheet row.
- A PDF is missing in the spreadsheet.
- A spreadsheet entry has no matching PDF.
- Invoice amounts differ.
- Invoice dates differ.
- Duplicate spreadsheet invoice numbers.
- Multiple possible matches.
- Same invoice number from different suppliers.
- Multiple sheets with overlapping records.
Produce:
- matched_count
- mismatched_count
- missing_in_pdf_count
- missing_in_spreadsheet_count
- ambiguous_count
- duplicate_count
Each reconciliation finding must include source references.
Provide JSON results suitable for frontend tables.
Optionally export sanitized reconciliation reports as CSV.
Avoid spreadsheet formula injection in exported CSV.

14. BACKGROUND JOB ORCHESTRATION
Use Celery + Redis for asynchronous work.
PostgreSQL is the authoritative record for processing status.
Queues:
- ingestion
- ocr
- extraction
- validation
- comparison
- indexing
- maintenance
Use different worker concurrency settings appropriate to CPU, memory, and API limits.
Implement processing state transitions:
QUEUED
→ PREPROCESSING
→ PARSING
→ EXTRACTING
→ VALIDATING
→ INDEXING
→ COMPLETED
Additional terminal or exceptional states:
- COMPLETED_WITH_WARNINGS
- REQUIRES_REVIEW
- FAILED
- CANCELLED
Avoid a global shared enum that permits invalid state transitions.
Track each stage separately and calculate overall progress from completed work units.
For page-based documents:
- pages_total
- pages_completed
- pages_failed
- current_stage
- last_update_at
Never report 100% until required processing stages are complete.
14.1 Transactional Outbox
Use a PostgreSQL transactional outbox to avoid losing jobs between database commits and Redis publication.
Workflow:
1. Create processing run and outbox record in the same database transaction.
2. Commit.
3. Outbox dispatcher publishes the task.
4. Mark outbox event published.
5. Workers process safely even if events are delivered more than once.
Implement a small reliable dispatcher using Celery Beat or a dedicated process.
Document operational trade-offs.
14.2 Idempotency
Every task must have a deterministic idempotency identity.
For page work, use a key based on:
- processing_run_id
- page or batch range
- stage
- version
Use database uniqueness and atomic state transitions.
Do not rely only on a Redis lock for correctness.
Avoid two workers committing conflicting results for the same page.
Make repeated task delivery safe.
14.3 Retries
Configure:
- Exponential backoff
- Jitter
- Maximum retry count
- Retryable error classification
- Hard and soft execution time limits
- Graceful termination handling
Use late acknowledgments where appropriate.
Handle Redis visibility timeout carefully.
Prefer short, checkpointed tasks instead of one extremely long Celery task.
Expose an authorized endpoint for failed-job reprocessing.
Preserve retry and failure history.
Add a dead-letter equivalent using persisted terminal failure records and administrative replay.
Do not claim Redis/Celery provides exactly-once execution.
14.4 Failure Recovery
Test:
- Worker termination during OCR.
- Redis restart.
- Database temporarily unavailable.
- Object storage unavailable.
- LLM timeout.
- Malformed PDF.
- Bad spreadsheet.
- Repeated task delivery.
- Partial document completion.
- Outbox dispatch failure.
Ensure recovery does not duplicate invoices or validation findings.
Implement a periodic reconciliation task that identifies stale processing runs and repairs or fails them according to documented rules.

15. SEARCH ENGINE
Implement hybrid document search using PostgreSQL and pgvector.
15.1 Keyword Search
Use PostgreSQL full-text search.
Searchable fields:
- Document filename
- Supplier name
- Customer name
- Invoice number
- Extracted text
- Line-item descriptions
- Document type
Filters:
- Date ranges
- Supplier
- Currency
- Total amount range
- File type
- Processing status
- Validation status
Implement pagination and stable ordering.
15.2 Semantic Search
Create bounded document chunks.
Preserve:
- document_id
- page_number
- chunk_index
- source evidence
Generate embeddings through a configurable embedding provider.
Store vector embeddings in pgvector.
Use an appropriate vector dimension matching the selected provider.
Create an HNSW index when justified.
Support metadata filtering and tenant-scoped retrieval.
Account for approximate-search filtering behavior.
Do not allow results from another organization to enter the candidate set or response.
15.3 Hybrid Ranking
Combine keyword and vector search with a documented ranking method such as Reciprocal Rank Fusion.
Return:
- document_id
- filename
- snippet
- matched_pages
- score
- match_type
- source_reference
Do not invent semantic similarity percentages.
Include tests for:
- Keyword matching
- Semantic matching
- Combined ranking
- Tenant isolation
- Empty query
- Pagination
- Unsupported filters

16. API DESIGN
All business APIs must live under:
/api/v1
Use consistent request and response schemas.
Use appropriate HTTP status codes.
Implement these endpoint groups.
Auth
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
GET /auth/me
Registration policy must be configurable:
- Open registration for local demonstration.
- Restricted or invitation-based registration for production.
Documents
POST /documents/upload
GET /documents
GET /documents/{document_id}
GET /documents/{document_id}/download
GET /documents/{document_id}/pages
GET /documents/{document_id}/text
GET /documents/{document_id}/tables
DELETE /documents/{document_id}
Jobs
GET /jobs
GET /jobs/{job_id}
GET /documents/{document_id}/jobs
POST /jobs/{job_id}/retry
POST /jobs/{job_id}/cancel
Extraction
GET /documents/{document_id}/extractions
GET /documents/{document_id}/invoices
GET /invoices/{invoice_id}
GET /invoices/{invoice_id}/line-items
Validation
GET /documents/{document_id}/validations
GET /invoices/{invoice_id}/validations
POST /invoices/{invoice_id}/revalidate
Comparison
POST /comparisons
GET /comparisons
GET /comparisons/{comparison_id}
GET /comparisons/{comparison_id}/findings
Reconciliation
POST /reconciliations
GET /reconciliations/{reconciliation_id}
GET /reconciliations/{reconciliation_id}/findings
Manual Review
GET /reviews/queue
GET /reviews/{review_id}
PATCH /invoices/{invoice_id}/corrections
POST /invoices/{invoice_id}/approve
POST /invoices/{invoice_id}/reject
Search
GET /search/keyword
POST /search/semantic
POST /search/hybrid
Operational
GET /health/live
GET /health/ready
GET /health/startup
GET /metrics
Protect operational endpoints appropriately.
Do not expose sensitive diagnostics publicly.
API Standards
- OpenAPI documentation.
- Explicit request and response models.
- Consistent pagination.
- Validation errors with machine-readable codes.
- Request correlation IDs.
- Idempotency-Key support for important creation operations.
- Configurable rate limiting.
- Bounded list-query parameters.
- Stable error response envelope.
- No internal stack traces in production responses.
- No leaking filesystem paths or storage credentials.
- Explicit API versioning.
For expensive operations, return HTTP 202 Accepted with the job identifier and status URL.
Provide sample curl commands for core workflows.

17. HUMAN REVIEW AND AUDITING
Financial extraction must support human oversight.
Implement a review workflow:
AUTOMATED_EXTRACTION
→ VALIDATION
→ REVIEW_REQUIRED
→ HUMAN_CORRECTION
→ REVALIDATION
→ APPROVED or REJECTED
Requirements:
- Authorized reviewers can correct fields.
- Corrections do not overwrite historical extraction records.
- Store original and corrected values.
- Record reviewer identity.
- Record timestamps.
- Require a correction reason when appropriate.
- Re-run dependent validation rules after correction.
- Invalidate or refresh affected comparison results.
- Invalidate or refresh affected search index entries.
- Prevent race conditions from simultaneous corrections.
- Use optimistic locking or equivalent version checks.
- Keep an append-only audit history at the application level.
- Distinguish machine-extracted values from human-approved values.
- Never interpret correction as proof that the document itself changed.
Implement:
- Review queue
- Review assignment or ownership
- Review approval
- Review rejection
- Correction history
- Audit event retrieval

18. SECURITY REQUIREMENTS
Implement defense in depth.
Application
- Strict input validation.
- Explicit authorization on every resource.
- Tenant isolation.
- Parameterized SQL through ORM or safe queries.
- Secure password storage.
- Token rotation.
- Safe exception handling.
- CORS allowlist.
- Trusted host configuration.
- Rate limiting.
- Request body limits.
- Sensitive-header redaction.
- API documentation exposure configurable by environment.
File Processing
- Validate file signatures.
- Prevent path traversal.
- Prevent decompression bombs.
- Bound memory consumption.
- Limit page rendering resolution.
- Limit spreadsheet row counts.
- Limit OCR execution time.
- Do not execute macros.
- Do not execute spreadsheet formulas.
- Protect against malformed PDF and image parser crashes.
- Run parsing workers with reduced privileges.
- Use restrictive filesystem permissions.
- Use temporary directories with cleanup.
- Avoid exposing temporary object storage paths.
Network
- Enforce TLS at ingress.
- Avoid publicly exposing Redis or PostgreSQL.
- Use private service networks.
- Restrict worker outbound access where operationally feasible.
- Use secure object storage credentials.
- Minimize service permissions.
- Separate production secrets from configuration files.
LLM Security
- Treat all document text as untrusted.
- Prevent prompt injection from controlling application actions.
- Do not put secrets inside prompts.
- Support disabling external AI transmission.
- Document which data is sent to hosted LLMs.
- Support provider timeouts.
- Sanitize logs.
- Document retention behavior and provider limitations.
Operational Security
- Non-root containers.
- Minimal Linux capabilities.
- Read-only filesystem where feasible.
- Restricted temporary writable mounts.
- Resource limits.
- Secret-based credentials.
- Dependency scanning.
- Container scanning.
- Audit logs.
- Backup and restore procedures.
Do not claim certified compliance with SOC 2, ISO 27001, GDPR, or other frameworks.
Document security controls and remaining compliance work honestly.

19. DOCKER REQUIREMENTS
Create a reproducible Docker Compose environment containing:
- FastAPI API
- PostgreSQL with pgvector
- Redis
- MinIO
- Celery ingestion worker
- Celery OCR worker
- Celery extraction worker
- Celery validation/comparison worker
- Celery indexing worker
- Outbox dispatcher
- Celery Beat or controlled scheduling component
- Optional Prometheus/Grafana profile
Use shared application image layers when appropriate.
Docker requirements:
- Multi-stage build.
- Pinned base image.
- Locked Python dependencies.
- Non-root runtime user.
- Proper health checks.
- Named persistent volumes.
- Docker networks.
- Configurable environment variables.
- No secrets in images.
- Restart policies.
- Log rotation guidance.
- Resource constraints.
- Init or graceful signal handling.
- Migration command.
- Development bootstrap command.
The documented local deployment should start using:
docker compose up --build -d
Where initialization requires an explicit preliminary step, document it precisely.
Make readiness meaningful rather than relying on container-start order alone.
Provide:
- .env.example
- compose.yaml
- compose.dev.yaml
- Dockerfile
- .dockerignore
- Makefile
Document startup, shutdown, migration, tests, logs, backups, and troubleshooting.

20. KUBERNETES REQUIREMENTS
Create a Helm chart under:
infra/helm/docintel/
Include:
- API Deployment
- API Service
- API Ingress configuration
- Celery worker Deployments by queue
- Outbox dispatcher Deployment
- Scheduled maintenance component
- Kubernetes ServiceAccounts
- ConfigMaps
- External Secret references or Kubernetes Secret configuration
- PodDisruptionBudgets where justified
- Resource requests and limits
- Readiness probes
- Liveness probes
- Startup probes
- HorizontalPodAutoscaler for API
- Worker autoscaling configuration, with KEDA as a documented option
- NetworkPolicy examples
- Migration Job or release migration strategy
Important Kubernetes design:
- Do not run database migrations automatically in every API replica.
- Run migrations as a controlled one-time deployment step.
- Prefer externally managed PostgreSQL, Redis, and S3-compatible storage in production.
- Do not pretend in-cluster single-replica PostgreSQL is automatically highly available.
- Scale API pods independently of OCR workers.
- Scale OCR workers based on queue depth and CPU/memory capacity.
- Scale AI workers based on provider concurrency constraints.
- Handle SIGTERM gracefully.
- Configure termination grace periods.
- Avoid assigning excessive concurrency to memory-heavy OCR workloads.
- Apply least-privilege security contexts.
- Provide default-deny NetworkPolicy examples and required service exceptions.
- Use namespace-scoped deployment resources wherever possible.
Provide:
- Chart.yaml
- values.yaml
- values-development.yaml
- values-production.example.yaml
- Helm templates
- Installation and upgrade instructions
- Rollback instructions
Run Helm lint and template rendering if Helm is available.
If Kubernetes is not available, distinguish chart validation from actual cluster deployment.

21. OBSERVABILITY
Implement production-grade visibility.
Logging
Use structured JSON logs containing:
- timestamp
- level
- service
- request_id
- job_id when applicable
- document_id when applicable
- stage
- event
- duration_ms when relevant
- sanitized error code
Do not record:
- JWTs
- passwords
- API keys
- full sensitive document bodies
- unnecessary personally identifiable information
Metrics
Expose Prometheus metrics for:
- HTTP request count
- HTTP latency
- HTTP error rate
- Queue backlog where observable
- Active processing jobs
- Document processing duration
- OCR pages processed
- OCR failure count
- Extraction duration
- LLM request count
- LLM retry count
- Estimated token usage
- Validation failure count
- Failed jobs
- Reprocessed jobs
- Completed documents
- Search request duration
Use bounded metric label cardinality.
Do not use document IDs or user IDs as Prometheus metric labels.
Tracing
Implement OpenTelemetry trace propagation across:
- API requests
- Queue dispatch
- Celery task processing
- Database interactions
- External LLM calls
Make tracing configurable.
Provide example dashboards and alert definitions for:
- Elevated processing failures
- Growing OCR backlog
- Excessive job latency
- Database connectivity failures
- Object storage outages
- LLM provider failure spikes

22. PERFORMANCE AND SCALABILITY
Design for thousands of documents daily.
This is a design target, not an unverified performance claim.
Implement:
- Streaming file ingestion.
- Page-level che
[Message truncated - exceeded 50,000 character limit]
Show less
