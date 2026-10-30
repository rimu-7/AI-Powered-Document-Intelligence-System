# Production-Grade FastAPI Backend — Complete Engineering Blueprint
**AI-Powered Document Intelligence & Financial Verification Platform · Senior AI Engineer Technical Assignment**

I recommend building this as a production-oriented, modular, event-driven document intelligence platform, rather than a basic FastAPI CRUD project with an OCR endpoint.

Your backend should demonstrate the engineering skills that distinguish a senior AI engineer: distributed processing, reliable AI extraction, document provenance, financial correctness, security, database architecture, observability, scalability, and operational recovery. The goal is to make a reviewer see not just that your application works, but that you understand how to build, deploy, scale, debug, and maintain a real document-processing system.

---

## 1. Architecture Decisions

### Recommended Architecture (Production-Oriented)
*   **React / Next.js Client:** Upload · Review · Compare · Search
*   **Ingress / Reverse Proxy:** TLS · Rate limits · Request size limits
*   **FastAPI Application:** Auth · Documents · Jobs · Invoices · Validation · Comparison · Search
*   **PostgreSQL Outbox + Redis / Celery:** Durable job dispatch · Multiple specialized queues
*   **Preprocessing:** File validation · Page splitting
*   **OCR Workers:** PDF · Image · Table extraction
*   **AI Workers:** LLM · Structured information
*   **Validation Workers:** Financial rules · Cross-verification
*   **Search Workers:** Embeddings · Indexing
*   **Maintenance:** Retries · Cleanup · Reconciliation
*   **PostgreSQL:** pgvector
*   **S3 / MinIO:** File storage
*   **Monitoring:** OTel / Metrics

### Technology Stack
| Layer | Recommended Stack |
| :--- | :--- |
| **Language** | Python 3.12+ |
| **API framework** | FastAPI |
| **Validation and settings** | Pydantic v2 |
| **ORM** | SQLAlchemy 2.x |
| **Database migrations** | Alembic |
| **Primary database** | PostgreSQL + pgvector |
| **Cache and messaging** | Redis |
| **Background execution** | Celery |
| **Object storage** | S3-compatible MinIO |
| **PDF parsing** | PyMuPDF |
| **OCR** | PaddleOCR, Tesseract fallback |
| **Image handling** | Pillow / OpenCV |
| **Spreadsheets** | openpyxl, pandas, xlrd |
| **AI extraction** | Provider-agnostic structured-output LLM adapter |
| **Vector embeddings** | Configurable embedding provider |
| **Authentication** | JWT + refresh-token rotation |
| **Containerization** | Docker + Docker Compose |
| **Orchestration** | Kubernetes + Helm |
| **Observability** | OpenTelemetry, Prometheus, Grafana |
| **Testing** | pytest, pytest-asyncio, HTTPX, Testcontainers |
| **CI/CD** | GitHub Actions |
| **Dependency management** | uv with lockfile |

**Why this architecture?** It keeps the synchronous API lightweight and moves expensive OCR, AI inference, and indexing into independently scalable workers. It also avoids unnecessary microservice complexity: one well-structured Python codebase can power multiple API and worker deployments.

---

## 2. Critical Engineering Decisions
These are the requirements I would insist the AI implements to make the project stand out:

*   **1,000-page PDFs:** Page-batch processing, checkpointing, bounded memory.
*   **Reliability:** Durable PostgreSQL job state and transactional outbox.
*   **Worker crashes:** At-least-once execution with idempotent tasks.
*   **Financial accuracy:** Decimal, never binary floats for money.
*   **AI hallucinations:** Nullable fields, source evidence, confidence, review.
*   **Scanned documents:** OCR routing and image preprocessing.
*   **PDF–Excel matching:** Normalized comparison with traceable evidence.
*   **Duplicate handling:** SHA-256 file hashes and business-key duplicate detection.
*   **Search:** PostgreSQL full-text search plus pgvector.
*   **Security:** Tenant isolation, RBAC, safe upload handling.
*   **Scale:** Separate Celery queues, resource limits, autoscaling.
*   **Corrections:** Immutable extraction revisions and human audit trail.
*   **Observability:** Structured logs, traces, metrics, correlation IDs.
*   **Deployment:** Reproducible Docker Compose and Kubernetes Helm chart.
*   **Evaluation:** Actual measured metrics, not invented performance claims.

> **Note:** Redis/Celery delivery is not guaranteed to be exactly once. Redis visibility timeouts can cause tasks to be redelivered, so your system must be safe when the same task executes more than once. Likewise, pgvector's HNSW indexing introduces recall and filtering trade-offs.

---

## 3. Backend Modules
Organize the application into these bounded modules:
1. **Identity and tenancy:** users, organizations, roles, access tokens, permissions.
2. **Document management:** uploads, file metadata, storage, hashing, versioning.
3. **Document parsing:** PDF, OCR, images, spreadsheets, text, tables, page evidence.
4. **AI extraction:** invoice field schemas, prompts, providers, confidence, validation.
5. **Financial verification:** arithmetic checks, duplicates, cross-document reconciliation.
6. **Job orchestration:** Celery tasks, queues, retries, recovery, progress.
7. **Human review:** corrections, approvals, revision history, audit logs.
8. **Search and retrieval:** keyword search, semantic search, hybrid ranking.
9. **Administration and observability:** health endpoints, metrics, operational reporting.

---

# 4. MASTER ENGINEERING PROMPT — DOCINTEL AI
*(Copy and paste everything below this line directly into your AI coding assistant running inside the project directory).*

**ROLE AND MISSION**
Act as a Principal AI Engineer, Staff Backend Engineer, Distributed Systems Architect, Database Architect, DevSecOps Engineer, and Senior QA Engineer.

You are responsible for architecting, implementing, integrating, testing, documenting, and preparing for deployment a complete production-oriented backend named:
**DocIntel AI — Enterprise Document Intelligence & Financial Verification Platform**

This is a high-stakes Senior AI Engineer technical assignment. The system must ingest large volumes of business documents, extract financial information accurately, validate results, reconcile financial records across document formats, support human review, and provide secure REST APIs.

Your output must be real, executable, maintainable software—not illustrative pseudocode, disconnected snippets, scaffolding without implementation, or placeholder functionality. You have access to this repository and may use the terminal, filesystem, code execution, package managers, and Docker where available.

Your mission is to implement the complete backend, run meaningful checks, fix defects, and leave the repository in the best working state possible.
* Do not stop after producing a plan.
* Do not ask me to approve architecture decisions that have already been specified here.
* Do not claim production readiness, successful tests, or measured performance without evidence.
* If a dependency, API key, GPU, Kubernetes cluster, or external resource is unavailable, implement a working local alternative where appropriate, preserve the production interface, and document exactly what could not be verified.

Work autonomously through the entire implementation.

### 1. BUSINESS REQUIREMENTS
The company receives thousands of financial documents daily, including:
- Digital PDF invoices, Scanned PDF invoices, Receipts
- JPG, PNG, and TIFF images (including multipage TIFF)
- XLSX workbooks, Legacy XLS workbooks, CSV datasets
- Large PDFs, potentially approximately 1,000 pages

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

The system must provide a documented REST API suitable for a React or Next.js frontend. Backend implementation is the primary deliverable. Do not build a frontend unless explicitly requested.

### 2. IMPLEMENTATION RULES
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
18. Use `Decimal` for monetary calculations.
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

### 3. REQUIRED TECHNOLOGY STACK
* **Language:** Python 3.12+
* **API:** FastAPI, Pydantic v2, pydantic-settings, Uvicorn, HTTPX
* **Database:** PostgreSQL, SQLAlchemy 2.x, asyncpg, psycopg, Alembic, pgvector
* **Queue:** Celery, Redis (broker & cache), PostgreSQL (outbox/job state)
* **File storage:** S3-compatible object storage (MinIO for local dev)
* **Processing:** PyMuPDF, Pillow, OpenCV, PaddleOCR (preferred), Tesseract (fallback), pandas, openpyxl, xlrd, csv
* **AI:** Provider-neutral interface, structured Pydantic output, vector embeddings
* **Search:** PostgreSQL full-text search, pgvector, hybrid ranking
* **Auth:** Secure JWT, refresh tokens, Argon2, RBAC
* **Testing:** pytest, pytest-asyncio, pytest-cov, HTTPX ASGI tests, Testcontainers, Hypothesis, Ruff, mypy/pyright
* **Infra:** Multi-stage Dockerfile, Docker Compose, Kubernetes, Helm, GitHub Actions
* **Observability:** JSON logging, Prometheus metrics, OpenTelemetry, Grafana

### 4. REPOSITORY ORGANIZATION
Create a maintainable project structure strictly similar to:

```text
docintel-ai/
├── app/
│   ├── main.py
│   ├── core/ (config.py, security.py, logging.py, exceptions.py, middleware.py, database.py, permissions.py, telemetry.py)
│   ├── api/
│   │   └── v1/ (router.py, auth.py, users.py, documents.py, jobs.py, invoices.py, validations.py, comparisons.py, corrections.py, search.py, reviews.py, admin.py, health.py)
│   ├── modules/
│   │   ├── identity/ (models.py, schemas.py, repository.py, service.py)
│   │   ├── documents/ (upload_service.py, storage.py, fingerprint.py, etc.)
│   │   ├── parsing/ (pdf_parser.py, ocr_service.py, spreadsheet_parser.py, provenance.py, etc.)
│   │   ├── extraction/ (service.py, prompts.py, normalization.py, providers/)
│   │   ├── validation/ (rules.py, financial.py, duplicates.py)
│   │   ├── comparison/ (matching.py, pdf_pdf.py, pdf_spreadsheet.py, reconciliation.py)
│   │   ├── reviews/
│   │   ├── search/ (indexing.py, embeddings.py, keyword.py, semantic.py, hybrid.py)
│   │   ├── jobs/ (orchestration.py, lifecycle.py, recovery.py, outbox.py)
│   │   └── auditing/
│   └── workers/ (celery_app.py, preprocess_tasks.py, ocr_tasks.py, extract_tasks.py, etc.)
│   └── shared/ (enums.py, pagination.py, money.py, identifiers.py, utilities.py)
├── alembic/
├── tests/ (unit, integration, api, workers, security, performance, fixtures)
├── evaluation/
├── scripts/
├── infra/ (docker, helm/docintel, monitoring)
├── docs/
├── .github/
├── Dockerfile
├── compose.yaml
├── compose.dev.yaml
├── .env.example
├── pyproject.toml
├── uv.lock
└── README.md
```

### 5. MULTI-TENANCY, USERS, AND AUTHORIZATION
Implement organization-scoped multi-tenancy.
* **Entities:** `organizations`, `users`, `refresh_sessions`.
* **Roles:** `ADMIN`, `ANALYST`, `REVIEWER`, `VIEWER`.
* **Security:** Derive Org IDs from authenticated identity. Never trust client-supplied Org IDs. Use explicit Org filters in all DB queries. Prevent cross-tenant lookup. Use short-lived JWTs and hashed refresh tokens.

### 6. DOCUMENT UPLOAD AND STORAGE
Implement secure document ingestion (.pdf, .jpg, .jpeg, .png, .tif, .tiff, .xlsx, .xls, .csv).
* Features: Multipart upload, streaming uploads, file size/count limits, UUID internal keys, SHA-256 checksums, content-signature validation.
* Security: No user-controlled paths, block unsafe types, restrict outbound access. Separate original storage from temp artifacts/OCR results.

### 7. DOCUMENT DATABASE MODELS
Use normalized PostgreSQL models with UUID primary keys.
Required Entities:
* `documents`, `document_pages`, `document_tables`, `document_chunks`
* `processing_runs`, `processing_tasks`, `outbox_events`
* `invoice_records`, `invoice_line_items`, `extraction_runs`
* `validation_issues`, `document_comparisons`, `comparison_findings`
* `review_actions`, `audit_events`
*(Add appropriate indexes, pgvector setup, and NUMERIC types for financial data).*

### 8. DOCUMENT PROCESSING PIPELINE
Pipeline workflow: UPLOAD → SECURITY CHECK → FILE IDENTIFICATION → METADATA EXTRACTION → PAGE OR SHEET DISCOVERY → TEXT EXTRACTION / OCR → DOCUMENT NORMALIZATION → CLASSIFICATION → AI EXTRACTION → FINANCIAL VALIDATION → SEARCH INDEXING → COMPLETION OR MANUAL REVIEW.
* **PDFs:** PyMuPDF, page classification, batch processing (checkpointing), handle multi-invoice docs.
* **OCR:** PaddleOCR (Tesseract fallback). Apply conditionally.
* **Spreadsheets:** Stream parsing, bounds checking, no macro execution, coordinate preservation.

### 9. DOCUMENT CLASSIFICATION
Deterministic-first system (`INVOICE`, `RECEIPT`, `CREDIT_NOTE`, `FINANCIAL_STATEMENT`, `SPREADSHEET_REGISTER`, `UNKNOWN`).

### 10. AI INFORMATION EXTRACTION
Extract using strict Pydantic schemas.
```json
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
```
* **Rules:** Never invent missing fields (use null). Preserve raw values. Normalize dates/currencies.
* **Evidence Grounding:** Trace fields back to doc_id, page, bounding_box, and supporting text.
* **Long Docs:** Token-aware chunking, segment boundaries. Do not send 1000 pages to one prompt.
* **Security:** Defend against prompt injection.

### 11. FINANCIAL VALIDATION ENGINE
Deterministic financial validation using `Decimal`.
* Rules: Missing fields, invalid dates/currencies, line total mismatch, subtotal mismatch, tax mismatch, duplicate file/invoice.
* Severities: INFO, WARNING, ERROR, CRITICAL.

### 12. PDF-TO-PDF COMPARISON
Compare document entities, line items, and totals. Preserve evidence. Return MATCH, MISMATCH, MISSING_LEFT, MISSING_RIGHT, AMBIGUOUS, NOT_COMPARABLE.

### 13. PDF-TO-EXCEL / CSV RECONCILIATION
Configurable mapping from spreadsheet columns to invoice fields. Produce structured reconciliation summaries (matched, mismatched, missing, duplicate counts). Prevent formula injection in CSV exports.

### 14. BACKGROUND JOB ORCHESTRATION
Celery + Redis + PostgreSQL.
* Queues: ingestion, ocr, extraction, validation, comparison, indexing, maintenance.
* PostgreSQL transactional outbox.
* Strict idempotency and retry policies (exponential backoff).

### 15. SEARCH ENGINE
Hybrid search using PostgreSQL full-text and pgvector.
* Semantic chunking with evidence tracing. HNSW indexing.
* Strict tenant isolation. Combine via Reciprocal Rank Fusion (RRF).

### 16. API DESIGN
All APIs under `/api/v1`.
* Endpoints for: Auth, Documents, Jobs, Extraction, Validation, Comparison, Reconciliation, Reviews, Search, Health/Metrics.
* Standards: OpenAPI, correlation IDs, 202 Accepted for background jobs, no stack traces.

### 17. HUMAN REVIEW AND AUDITING
Workflow for human oversight: extraction -> validation -> review -> human correction -> revalidation -> approved. Keep append-only audit history.

### 18. SECURITY REQUIREMENTS
Defense in depth: Input validation, RBAC, parameterized SQL, token rotation, file signature validation, anti-decompression bombs, bounded memory, TLS, restricted worker access, LLM prompt injection defenses.

### 19. DOCKER REQUIREMENTS
Reproducible environment: FastAPI, Postgres, Redis, MinIO, workers (OCR, extract, index, outbox, beat). Multi-stage build, non-root user, locked dependencies. Start with `docker compose up --build -d`.

### 20. KUBERNETES REQUIREMENTS
Helm chart in `infra/helm/docintel/`. Separate deployments for API and various workers. HPA, KEDA (optional), NetworkPolicies, controlled migrations (not automatic per pod).

### 21. OBSERVABILITY
* **Logs:** JSON (timestamp, level, service, request_id, job_id).
* **Metrics:** Prometheus (latency, error rates, queue backlogs).
* **Tracing:** OpenTelemetry for API to DB/External calls.

### 22. PERFORMANCE AND SCALABILITY
Target: Thousands of documents daily.
*Implement streaming ingestion and page-level chunking.*

*(Note: The original prompt input was truncated here. The AI should prioritize robust, streaming ingestion architectures to fulfill this final constraint.)*
