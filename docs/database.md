# Database schema

PostgreSQL 17 + pgvector 0.8. The schema is created only by Alembic migrations
(`backend/alembic/versions/`); a test asserts that models and migrated schema match.

## Entity-relationship diagram

```mermaid
erDiagram
    organizations ||--o{ users : has
    users ||--o{ refresh_sessions : "logs in with"
    organizations ||--o{ documents : owns
    documents ||--o{ document_pages : "split into"
    documents ||--o{ document_tables : contains
    document_tables ||--o{ spreadsheet_rows : "has rows"
    documents ||--o{ document_chunks : "indexed as"
    documents ||--o{ processing_runs : "processed by"
    processing_runs ||--o{ processing_tasks : "made of"
    processing_runs ||--o{ outbox_events : emits
    documents ||--o{ extraction_runs : "extracted by"
    extraction_runs ||--o{ invoice_records : produces
    invoice_records ||--o{ invoice_line_items : has
    invoice_records ||--o{ validation_issues : "flagged with"
    invoice_records ||--o{ review_tasks : "reviewed in"
    review_tasks ||--o{ review_actions : records
    documents ||--o{ document_comparisons : "compared in"
    document_comparisons ||--o{ comparison_findings : yields
    organizations ||--o{ audit_events : logs
    documents ||--o{ storage_objects : "stored as"

    documents {
        uuid id PK
        uuid organization_id FK
        string original_filename
        string file_kind "PDF IMAGE TIFF XLSX XLS CSV"
        bigint file_size_bytes
        string sha256
        string storage_key "UploadThing customId or S3 key"
        string document_type "INVOICE RECEIPT CREDIT_NOTE ..."
        string status
        string validation_outcome
        int page_count
        timestamptz deleted_at
    }
    document_pages {
        uuid id PK
        uuid document_id FK
        int page_number "unique per document"
        string page_type "NATIVE_TEXT SCANNED MIXED IMAGE EMPTY"
        text extracted_text
        string ocr_engine
        numeric ocr_confidence
        string processing_status
        string layout_storage_key "line bounding boxes"
    }
    spreadsheet_rows {
        uuid id PK
        uuid table_id FK
        string sheet_name
        int row_number
        jsonb cells_json "header -> value, type, cell, formula"
    }
    document_chunks {
        uuid id PK
        uuid document_id FK
        int page_number
        text text
        tsvector text_tsv "generated, GIN index"
        vector embedding "1024, HNSW index"
        string embedding_model
    }
    processing_runs {
        uuid id PK
        uuid document_id FK
        string job_type "DOCUMENT_PROCESSING REVALIDATION REINDEX COMPARISON RECONCILIATION"
        string state
        int pages_total
        int pages_completed
        int pages_failed
        numeric progress_percent
        string error_code
        jsonb stage_history_json
    }
    processing_tasks {
        uuid id PK
        uuid processing_run_id FK
        string task_type
        string task_state
        int page_start
        int page_end
        int attempt_count
        string idempotency_key "unique"
        uuid lease_token
        timestamptz lease_expires_at
        jsonb error_history_json
    }
    extraction_runs {
        uuid id PK
        uuid document_id FK
        string provider
        string model_name
        string prompt_version
        int extraction_revision
        jsonb normalized_result_json "immutable machine output"
        jsonb usage_json "tokens, requests"
    }
    invoice_records {
        uuid id PK
        uuid document_id FK
        string invoice_number
        date invoice_date
        string supplier_name
        string customer_name
        string currency "ISO 4217"
        string currency_source "PRINTED DOCUMENT_CONTEXT SUPPLIER_HISTORY ... HUMAN"
        numeric subtotal "NUMERIC(20,4)"
        numeric tax_amount
        numeric total_amount
        jsonb source_evidence_json "page, text, bounding box per field"
        jsonb field_support_json "SUPPORTED UNSUPPORTED HUMAN"
        string validation_outcome
        string review_status
        jsonb corrected_fields_json
        int version "optimistic locking"
        timestamptz superseded_at
    }
    invoice_line_items {
        uuid id PK
        uuid invoice_record_id FK
        int position
        text description
        numeric quantity
        numeric unit_price
        numeric line_total
    }
    validation_issues {
        uuid id PK
        uuid invoice_record_id FK
        string rule_code
        string severity "INFO WARNING ERROR CRITICAL"
        string field_path
        jsonb expected_value_json
        jsonb actual_value_json
        jsonb details_json "formula, difference, tolerance"
        string resolution_status
    }
    review_actions {
        uuid id PK
        uuid invoice_record_id FK
        uuid reviewer_id FK
        string action_type "CORRECTION APPROVAL REJECTION ASSIGNMENT"
        string field_path
        jsonb old_value_json
        jsonb new_value_json
        string reason
    }
    comparison_findings {
        uuid id PK
        uuid comparison_id FK
        string field_name
        string status "MATCH MISMATCH MISSING_LEFT MISSING_RIGHT AMBIGUOUS ..."
        jsonb left_value_json
        jsonb right_value_json
        jsonb evidence_json
    }
```

## How the assignment's data maps to tables

| Requirement | Tables |
|---|---|
| Document metadata | `documents`, `storage_objects` |
| Extracted text | `document_pages.extracted_text` (+ S3 for very long pages), `spreadsheet_rows`, `document_tables` |
| Structured results | `invoice_records`, `invoice_line_items`, `extraction_runs` (immutable machine output) |
| Validation errors | `validation_issues`, `review_tasks` |
| Processing history | `processing_runs` (stage history, progress, errors), `processing_tasks` (attempts, error history), `review_actions`, `audit_events` |
| Search | `document_chunks` (full-text `tsvector` + `vector(1024)`) |

## Design rules

* **Money**: `NUMERIC(20,4)` (quantities and prices `NUMERIC(20,6)`), never
  floats; APIs return decimal strings.
* **Tenant consistency**: every tenant table has `organization_id`; children
  reference `documents (organization_id, id)` through a composite foreign key,
  so a row can never belong to another tenant's document.
* **History is never overwritten**: re-extraction supersedes invoice records
  (`superseded_at`) instead of deleting them; human corrections are stored in
  `review_actions` with old and new values; `audit_events` is append-only
  (a database trigger rejects UPDATE/DELETE).
* **Idempotency keys**: `processing_tasks.idempotency_key` (run + stage + page
  range), `document_pages (document_id, page_number)`, and a partial unique
  index allowing one open review task per invoice.

## Indexes

| Index | Purpose |
|---|---|
| `documents (organization_id, created_at DESC) WHERE deleted_at IS NULL` | listing |
| `documents (organization_id, status)`, `(organization_id, sha256)` | status filters, duplicate files |
| `document_chunks USING gin (text_tsv)` | keyword search |
| `document_chunks USING hnsw (embedding vector_cosine_ops)` | semantic search |
| `invoice_records (organization_id, normalized_supplier, normalized_invoice_number) WHERE superseded_at IS NULL` | duplicate invoices |
| `processing_runs (updated_at) WHERE state NOT IN (terminal)` | recovery sweeps |
| `processing_tasks (lease_expires_at) WHERE task_state='RUNNING'` | expired leases |
| `outbox_events (available_at) WHERE published_at IS NULL` | dispatcher poll |
| `validation_issues (document_id) WHERE resolution_status='OPEN'` | open issues |

Vector search uses `hnsw.iterative_scan = relaxed_order` so tenant-filtered
queries still return enough neighbours; the tenant filter is part of the
candidate query itself.
