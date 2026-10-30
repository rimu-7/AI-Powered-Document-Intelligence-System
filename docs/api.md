# API

Base path `/api/v1`. OpenAPI: `/openapi.json`, Swagger UI `/docs` (disabled by
default in production: `API_DOCS_ENABLED`). Every response carries
`X-Request-ID` (an incoming value is accepted if it is 8–64 safe characters).

## Conventions

* **Auth**: `Authorization: Bearer <access token>` (JWT HS256, 15 min).
  Refresh tokens are opaque, rotated on every use, stored hashed; reuse of a
  rotated token revokes the whole session family.
* **Errors**: `{"error": {"code": "MACHINE_CODE", "message": "...", "request_id": "...", "details": ...}}`.
  Request validation → `422 REQUEST_VALIDATION_FAILED` with field locations.
  No stack traces or internal paths in responses.
* **Tenant isolation**: the organization always comes from the token. Other
  tenants' resources return `404` (not `403`), so their existence is not revealed.
* **Pagination**: `limit` (1–200, default 50) and `offset`; responses are
  `{items, total, limit, offset}` with stable ordering (`created_at DESC, id`).
* **Async work**: expensive operations return `202 Accepted` with `job_id`
  and `status_url` (`/api/v1/jobs/{id}`).
* **Idempotency**: `Idempotency-Key` header on `POST /documents/upload`,
  `POST /comparisons`, `POST /reconciliations`. A repeat with the same body
  replays the stored response (`Idempotent-Replay: true`); the same key with a
  different body → `422 IDEMPOTENCY_KEY_REUSED`; a concurrent repeat →
  `409 IDEMPOTENCY_IN_PROGRESS`. Keys expire after `IDEMPOTENCY_TTL_HOURS`.
* **Rate limits**: per user (`RATE_LIMIT_DEFAULT_PER_MINUTE`) and on
  login/register/refresh per IP and email; `429` + `Retry-After`.
* **Money**: decimal strings (never floats). Dates: ISO 8601. Timestamps: UTC.

## Roles

| Permission | VIEWER | ANALYST | REVIEWER | ADMIN |
|---|:-:|:-:|:-:|:-:|
| read documents, extractions, jobs, reviews; search | ✓ | ✓ | ✓ | ✓ |
| upload, reprocess, retry/cancel jobs, compare/reconcile, revalidate | | ✓ | ✓ | ✓ |
| correct, approve, reject invoices; claim reviews | | | ✓ | ✓ |
| delete documents, manage users, audit log, ops endpoints | | | | ✓ |

## Endpoints

| Group | Method & path |
|---|---|
| Auth | `POST /auth/register` (only when `REGISTRATION_MODE=open`; creates org + ADMIN) · `POST /auth/login` · `POST /auth/refresh` · `POST /auth/logout[?all_sessions=true]` · `GET /auth/me` |
| Users | `GET /users` · `POST /users` · `PATCH /users/{id}` (role / active) · `POST /users/{id}/revoke-sessions` |
| Documents | `POST /documents/upload` (multipart) · `POST /documents/upload/raw?filename=` (raw body) · `POST /documents/direct-uploads` → `PUT upload_url` (UploadThing) → `POST /documents/direct-uploads/{id}/complete` · `GET /documents` (filters: status, document_type, file_kind, filename, created range) · `GET /documents/{id}` · `GET /documents/{id}/download[?mode=presigned]` · `GET /documents/{id}/pages` (incl. `page_width`/`page_height`) · `GET /documents/{id}/pages/{n}/image[?width=]` (WebP, widths rounded up to 240/640/1024/1600, cached, ETag) · `GET /documents/{id}/text?page_from&page_to` · `GET /documents/{id}/tables` · `GET /documents/{id}/tables/{table_id}/rows` · `GET /documents/{id}/spreadsheet/mapping-suggestions` · `DELETE /documents/{id}` · `POST /documents/{id}/reprocess` |
| Jobs | `GET /jobs` · `GET /jobs/{id}` (stage history, tasks by state, failed tasks with error history) · `GET /documents/{id}/jobs` · `POST /jobs/{id}/retry` · `POST /jobs/{id}/cancel` |
| Extraction | `GET /documents/{id}/extractions` · `GET /extractions/{id}` · `GET /documents/{id}/invoices[?include_superseded=true]` · `GET /invoices/{id}` (incl. `machine_values`, evidence, alternatives) · `GET /invoices/{id}/line-items` · `GET /invoices/{id}/history` |
| Validation | `GET /documents/{id}/validations` · `GET /invoices/{id}/validations` · `POST /invoices/{id}/revalidate` |
| Review | `GET /reviews/queue` (status, assigned_to_me, unassigned) · `GET /reviews/{id}` · `POST /reviews/{id}/claim[?force=true]` · `PATCH /invoices/{id}/corrections` · `POST /invoices/{id}/approve` · `POST /invoices/{id}/reject` |
| Comparison | `POST /comparisons` · `GET /comparisons` · `GET /comparisons/{id}` · `GET /comparisons/{id}/findings` |
| Reconciliation | `POST /reconciliations` · `GET /reconciliations/{id}` · `GET /reconciliations/{id}/findings[?records_only=true&finding_status=…]` · `GET /reconciliations/{id}/export.csv` |
| Search | `GET /search/keyword` · `POST /search/semantic` · `POST /search/hybrid` |
| Admin | `GET /admin/stats` · `GET /admin/dead-letter` · `GET /admin/audit-events` |
| Config | `GET /config/public` (no auth: upload limits, allowed extensions, registration mode, direct upload availability, `currencies` as `{code, minor_units}`) |
| Ops (no prefix) | `GET /health/live` · `GET /health/ready` · `GET /health/startup` · `GET /metrics` (bearer `METRICS_TOKEN` when set) |

## Corrections

```json
PATCH /api/v1/invoices/{id}/corrections
{ "expected_version": 3,
  "reason": "Total misprinted; confirmed with supplier",
  "changes": [
    {"field_path": "total_amount", "value": "1100.00"},
    {"field_path": "line_items[0].quantity", "value": "2"},
    {"field_path": "line_items[]", "value": {"description": "Freight", "line_total": "25.00"}},
    {"field_path": "line_items[3]", "value": null}
  ] }
```

A stale `expected_version` → `409 VERSION_CONFLICT` (with `current_version`).
The response contains the updated invoice, a `revalidation_job_id`, and the
number of comparisons marked STALE. Approval with open ERROR/CRITICAL issues
→ `409 BLOCKING_ISSUES`, unless `acknowledge_issues: true` and a `reason` are
given (the issues are then marked ACCEPTED, with the approver recorded).
Approval while revalidation is still running → `409 REVALIDATION_PENDING`.

## Comparison and reconciliation

```json
POST /api/v1/comparisons
{"left_document_id": "…", "right_document_id": "…",
 "left_invoice_ids": null, "right_invoice_ids": null,
 "options": {"amount_tolerance": "0.01", "supplier_fuzzy_threshold": 90,
             "fuzzy_invoice_numbers": true, "default_currency": null}}

POST /api/v1/reconciliations
{"pdf_document_ids": ["…", "…"], "spreadsheet_document_id": "…",
 "column_mapping": {"invoice_number": "Invoice No", "supplier_name": "Vendor",
                    "invoice_date": "Invoice Date", "currency": "Currency",
                    "tax_amount": "VAT", "total_amount": "Invoice Total"},
 "sheet_names": null}
```

Without `column_mapping`, suggested mappings are used. If required fields
(`invoice_number`, `total_amount`) cannot be mapped → `422
INVALID_COLUMN_MAPPING`, with suggestions in `details`. Reconciliation summary:
`matched_count`, `mismatched_count`, `missing_in_pdf_count`,
`missing_in_spreadsheet_count`, `ambiguous_count`, `duplicate_count`. Findings
are `__record__` rows (one per record) plus per-field rows, each with evidence
from both sides.

## Search

* Keyword: PostgreSQL `websearch_to_tsquery` (english ∪ simple) over page
  chunks, spreadsheet rows, and a per-document metadata chunk; score
  `ts_rank_cd`; snippets via `ts_headline`.
* Semantic: cosine distance on pgvector HNSW; score = raw cosine similarity
  (not a percentage); pagination covers the top `SEARCH_CANDIDATE_LIMIT` chunks.
* Hybrid: Reciprocal Rank Fusion, `score = Σ 1/(k + rank)`, `k = SEARCH_RRF_K`
  (60); `match_type` is `keyword`, `semantic` or `hybrid`.
* Filters (unknown filters → 422): `date_from`, `date_to`, `supplier`,
  `currency`, `amount_min`, `amount_max`, `file_kinds`, `document_types`,
  `processing_statuses`, `validation_outcomes`. Empty query → `422 EMPTY_QUERY`.
  `currency` must be a `CurrencyCode` (e.g. `USD`); anything else → 422.
* Invoice `currency` is `CurrencyCode | null`; `currency_raw` is the text as
  printed (`"$"`). `null` means "not confirmed", never a default currency.

## curl walkthrough

```bash
API=http://localhost:8000/api/v1
curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"organization_name":"Acme","email":"me@acme.test","password":"Very-Strong-Pass-1","full_name":"Me"}'
TOKEN=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"me@acme.test","password":"Very-Strong-Pass-1"}' | jq -r .access_token)
H="Authorization: Bearer $TOKEN"

# Upload (202) and poll
curl -s -X POST $API/documents/upload -H "$H" -H "Idempotency-Key: upload-$(date +%s)" \
  -F files=@invoice.pdf -F files=@register.xlsx | tee upload.json
JOB=$(jq -r '.results[0].job_id' upload.json); DOC=$(jq -r '.results[0].document_id' upload.json)
curl -s $API/jobs/$JOB -H "$H" | jq '{state, progress_percent, pages_completed, pages_total}'

# Results
curl -s $API/documents/$DOC/invoices -H "$H" | jq
curl -s "$API/documents/$DOC/validations?severity=ERROR" -H "$H" | jq '.items[] | {rule_code, message}'

# Search
curl -s "$API/search/keyword?q=office%20equipment&currency=USD" -H "$H" | jq '.items[] | {filename, score, matched_pages}'
curl -s -X POST $API/search/hybrid -H "$H" -H 'Content-Type: application/json' -d '{"query":"ergonomic chairs"}' | jq

# Reconcile PDFs against the register
SHEET=$(jq -r '.results[1].document_id' upload.json)
curl -s -X POST $API/reconciliations -H "$H" -H 'Content-Type: application/json' \
  -d "{\"pdf_document_ids\":[\"$DOC\"],\"spreadsheet_document_id\":\"$SHEET\"}" | jq
```
