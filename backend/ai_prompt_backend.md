# DocIntel AI — Document Intelligence Backend

Backend for an AI-powered document intelligence system. It ingests invoices,
receipts, scanned PDFs (around 1,000 pages), images and spreadsheets;
extracts structured invoice data with an LLM without inventing values;
validates the numbers deterministically; cross-verifies PDF↔PDF and
PDF↔Excel/CSV; flags records for manual review; and makes everything
searchable (keyword and semantic) through a REST API.

**Stack:** FastAPI · Celery + Redis · PostgreSQL 17 + pgvector · PyMuPDF ·
Tesseract + OpenCV · openpyxl / xlrd · Mistral (LLM + embeddings) ·
UploadThing or S3/MinIO for original files · Docker Compose.
FastAPI is used instead of Node.js/NestJS because the whole document stack
(OCR, PDF, spreadsheets) is Python, so API and workers share one codebase.
Rationale for each choice: [docs/architecture.md](docs/architecture.md#technology-choices).

## Assignment coverage

| Task | Where |
|---|---|
| 1. Document processing (PDF, JPG, PNG, TIFF, XLSX, XLS, CSV; multi-page, multi-sheet, poor quality, corrupted) | `app/modules/parsing/`, pipeline in `app/workers/pipeline.py` |
| 2. AI extraction (invoice no., date, supplier, customer, subtotal, tax, total, currency, line items → JSON, nulls instead of guesses) | `app/modules/extraction/` |
| 3. Validation (missing fields, wrong numbers, duplicates, subtotal/tax/lines/total consistency, review flags) | `app/modules/validation/` |
| 4. REST API (upload, status, results, search, corrections, failed-job reprocessing; background jobs) | `app/api/v1/`, [docs/api.md](docs/api.md) |
| 5. Database + search (metadata, text, results, errors, history; keyword + semantic) | [docs/database.md](docs/database.md), `app/modules/search/` |
| 6. Frontend | not part of this repository (planned separately; the API is ready for it, see [docs/api.md](docs/api.md)) |
| 7. Tests + evaluation (measured accuracy, time, success/failure rates) | `tests/`, [docs/testing.md](docs/testing.md), [docs/evaluation.md](docs/evaluation.md) |
| Cross-verification PDF↔PDF and PDF↔Excel | `app/modules/comparison/` |

Deliverables: architecture diagram → [docs/architecture.md](docs/architecture.md) ·
database schema → [docs/database.md](docs/database.md) · test results →
[docs/testing.md](docs/testing.md) · evaluation report →
[docs/evaluation.md](docs/evaluation.md) · AI prompts and disclosure →
[docs/ai-disclosure.md](docs/ai-disclosure.md).

## Setup

Requirements: Docker 24+ with Compose v2, Python 3 (for `make init`), and
optionally [uv](https://docs.astral.sh/uv/) for running tests on the host.

```bash
cp .env.example .env            # or: make init  (generates local secrets, never overwrites existing keys)
# Put your keys in .env:
#   MISTRAL_API_KEY=...         → LLM extraction + semantic search (without it: local rules + lexical vectors)
#   UPLOADTHING_TOKEN=...       → with ORIGINALS_STORAGE=uploadthing, original files go to UploadThing
make init                       # fills in any missing secrets
docker compose up --build -d    # API at http://localhost:8000, interactive docs at /docs
make smoke                      # end-to-end check (upload → OCR → extraction → search → reconciliation)
```

Services: `api`, `dispatcher`, `beat`, five worker pools (`worker-ingestion`,
`worker-ocr`, `worker-extraction`, `worker-validation`, `worker-indexing`),
`postgres`, `redis`, `minio`, plus the one-off `migrate` and `storage-init`.
Scale a stage with `docker compose up -d --scale worker-ocr=4`.

## Using the API

```bash
API=http://localhost:8000/api/v1
curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"organization_name":"Acme","email":"me@acme.test","password":"Very-Strong-Pass-1","full_name":"Me"}'
TOKEN=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"me@acme.test","password":"Very-Strong-Pass-1"}' | jq -r .access_token)
H="Authorization: Bearer $TOKEN"

# Upload: multipart (many files), raw body, or direct-to-UploadThing (see docs/api.md)
curl -s -X POST $API/documents/upload -H "$H" -F files=@invoice.pdf -F files=@register.xlsx
curl -s -X POST "$API/documents/upload/raw?filename=scan.png" -H "$H" --data-binary @scan.png

curl -s $API/jobs/<job_id> -H "$H"                      # status + progress_percent
curl -s $API/documents/<document_id>/invoices -H "$H"   # extracted invoices (JSON)
curl -s $API/documents/<document_id>/validations -H "$H"
curl -s "$API/search/keyword?q=office%20chairs" -H "$H"
curl -s -X POST $API/search/semantic -H "$H" -H 'Content-Type: application/json' -d '{"query":"ergonomic seating"}'
curl -s -X PATCH $API/invoices/<invoice_id>/corrections -H "$H" -H 'Content-Type: application/json' \
  -d '{"expected_version":1,"reason":"misread total","changes":[{"field_path":"total_amount","value":"1100.00"}]}'
curl -s -X POST $API/jobs/<failed_job_id>/retry -H "$H"
```

Full endpoint list and examples: [docs/api.md](docs/api.md).

## Configuration

All settings are environment variables (`app/core/config.py`, documented in
`.env.example`). The most important ones:

| Variable | Default | Meaning |
|---|---|---|
| `EXTRACTION_PROVIDER` | `hosted` with a key, else `local` | `hosted` = Mistral LLM; `local` = deterministic rules |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | `hosted` / `mistral-embed` | semantic search vectors (1024-dim) |
| `LLM_MODEL`, `LLM_MAX_CONCURRENCY` | `open-mistral-nemo`, `8` | model; max concurrent LLM calls (global, all workers) |
| `EXTRACTION_CROSS_CHECK` | `true` | verify LLM output against the rule-based extractor (see architecture) |
| `ORIGINALS_STORAGE` | `s3` | `uploadthing` stores raw originals in UploadThing |
| `PAGE_BATCH_SIZE` | `10` | pages per OCR task |
| `UPLOAD_MAX_FILE_BYTES`, `MAX_PDF_PAGES` | 200 MB, 1,500 | limits |
| `VALIDATION_AMOUNT_TOLERANCE` | `0.01` | absolute rounding tolerance |
| `REGISTRATION_MODE` | `open` locally | set `disabled` in production; create admins with `python -m scripts.create_admin` |

## Tests and evaluation

```bash
make test-unit       # fast, no Docker
make test            # unit + integration (starts PostgreSQL/Redis/MinIO with Testcontainers)
make test-docker     # whole suite inside the image (includes OCR tests)
make lint            # ruff + mypy
make evaluate        # labeled dataset → running stack → accuracy / time / success & failure rates
make benchmark       # 1,000-page PDF throughput
```

Latest results: [docs/testing.md](docs/testing.md) and [docs/evaluation.md](docs/evaluation.md).

## Operations

`make logs` · `make migrate` · `make backup-db` / `make restore-db FILE=…` ·
`docker compose exec api python -m scripts.reindex` (re-embed after changing
the embedding model) · `GET /health/ready` (database, Redis, storage) ·
`GET /metrics` (Prometheus, bearer `METRICS_TOKEN`) · `GET /api/v1/admin/dead-letter`
(failed jobs).

## Project structure

```
app/            API, domain modules, workers           alembic/      migrations
tests/          unit, api, workers, security, integration
evaluation/     labeled dataset, generator, evaluation runner, results
scripts/        init_env, create_admin, bootstrap, smoke_test, benchmark, reindex
docs/           architecture, database, api, testing, evaluation, ai-disclosure
compose.yaml    local / single-host deployment     Dockerfile   one image for all processes
```

PyMuPDF and MinIO are AGPL-licensed; review licensing before distribution.
