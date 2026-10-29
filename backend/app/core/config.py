"""Typed application settings loaded from environment variables."""

from __future__ import annotations

import os
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -------------------------------------------------------
    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "DocIntel AI"
    service_name: str = "docintel-api"
    log_level: str = "INFO"
    log_json: bool = True
    api_docs_enabled: bool | None = None
    cors_allowed_origins: CsvList = Field(default_factory=list)
    trusted_hosts: CsvList = Field(default_factory=lambda: ["*"])
    expose_error_details: bool = False

    # --- Database ----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://docintel:docintel@localhost:5432/docintel"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 10
    db_statement_timeout_ms: int = 30_000

    # --- Redis / Celery ----------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_visibility_timeout_seconds: int = 7_200

    # --- Object storage ----------------------------------------------------
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_public_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_bucket_originals: str = "docintel-originals"
    s3_bucket_artifacts: str = "docintel-artifacts"
    s3_server_side_encryption: str | None = None
    s3_create_buckets: bool = False
    s3_connect_timeout_seconds: int = 5
    s3_read_timeout_seconds: int = 60
    s3_presigned_url_ttl_seconds: int = 60

    # --- Original-file storage --------------------------------------------
    # "s3": originals in S3/MinIO. "uploadthing": originals (raw, unmodified
    # bytes) in UploadThing; derived artifacts stay in S3/MinIO.
    originals_storage: Literal["s3", "uploadthing"] = "s3"
    uploadthing_token: SecretStr | None = None
    uploadthing_api_url: str = "https://api.uploadthing.com"
    # Free UploadThing apps only allow public-read (unguessable URL, but public).
    uploadthing_acl: Literal["public-read", "private"] = "public-read"
    uploadthing_allow_public_files: bool = False
    uploadthing_timeout_seconds: float = 120.0
    uploadthing_max_retries: int = 3
    direct_upload_ttl_seconds: int = 3600

    # --- Auth --------------------------------------------------------------
    jwt_secret: SecretStr = SecretStr("")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "docintel-ai"
    jwt_audience: str = "docintel-api"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 14 * 24 * 3600
    registration_mode: Literal["open", "disabled"] = "disabled"
    password_min_length: int = 12

    # --- Upload limits -----------------------------------------------------
    upload_max_file_bytes: int = 200 * 1024 * 1024
    upload_max_request_bytes: int = 1024 * 1024 * 1024
    upload_max_files: int = 20
    upload_duplicate_policy: Literal["allow", "reject"] = "allow"
    org_storage_quota_bytes: int = 50 * 1024 * 1024 * 1024
    max_pdf_pages: int = 1_500
    max_spreadsheet_rows: int = 200_000
    max_spreadsheet_columns: int = 200
    max_image_pixels: int = 89_478_485
    xlsx_max_uncompressed_bytes: int = 512 * 1024 * 1024
    xlsx_max_compression_ratio: int = 200
    xlsx_max_entries: int = 10_000

    # --- Processing --------------------------------------------------------
    page_batch_size: int = 10
    parser_version: str = "1"
    native_text_min_chars: int = 40
    native_text_min_quality: float = 0.6
    pdf_table_extraction: bool = True
    ocr_languages: str = "eng"
    ocr_dpi: int = 200
    ocr_timeout_seconds: int = 120
    max_render_pixels: int = 25_000_000
    page_text_db_max_chars: int = 100_000
    worker_file_cache_bytes: int = 2 * 1024 * 1024 * 1024
    worker_tmp_dir: str | None = None

    # --- Extraction / LLM --------------------------------------------------
    extraction_provider: Literal["local", "hosted"] = "local"
    ai_external_transmission_enabled: bool = False
    llm_base_url: str = "https://api.mistral.ai/v1"
    llm_api_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices("LLM_API_KEY", "MISTRAL_API_KEY"))
    llm_model: str = "open-mistral-nemo"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    llm_max_concurrency: int = 8
    llm_response_format: Literal["json_schema", "json_object"] = "json_schema"
    llm_max_input_chars: int = 24_000
    llm_classification_enabled: bool = False
    # If the LLM cannot process a segment (invalid output, rejected request),
    # extract it with the deterministic rules and flag the invoice.
    extraction_fallback_to_rules: bool = True
    # Also run the rules on every segment and apply arithmetic-verified corrections.
    extraction_cross_check: bool = True
    llm_cost_per_1k_input_tokens: Decimal | None = None
    llm_cost_per_1k_output_tokens: Decimal | None = None
    store_raw_llm_responses: bool = False
    prompt_version: str = "invoice-extract-v1"
    extraction_schema_version: str = "1"

    # --- Embeddings --------------------------------------------------------
    embedding_provider: Literal["local", "hosted"] = "local"
    embedding_model: str = "local-hash-v1"
    embedding_dimensions: int = 1024
    embedding_batch_size: int = 32
    embedding_base_url: str | None = None

    # --- Validation --------------------------------------------------------
    validation_amount_tolerance: Decimal = Decimal("0.01")
    future_date_policy: Literal["allow", "warn", "error"] = "warn"
    future_date_grace_days: int = 1
    date_day_first: bool = True
    low_confidence_threshold: float = 0.6
    classification_version: str = "rules-v1"

    # --- Search ------------------------------------------------------------
    search_hnsw_ef_search: int = 100
    search_rrf_k: int = 60
    search_candidate_limit: int = 200
    chunk_max_chars: int = 1_200
    chunk_overlap_chars: int = 150

    # --- Rate limiting -----------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = 600
    rate_limit_auth_per_minute: int = 10
    rate_limit_fail_open: bool = True

    # --- Observability -----------------------------------------------------
    metrics_token: SecretStr | None = None
    metrics_port: int = 9100

    # --- Jobs / maintenance ------------------------------------------------
    task_max_attempts: int = 5
    task_lease_seconds: int = 900
    task_retry_backoff_base_seconds: int = 5
    task_retry_backoff_max_seconds: int = 300
    task_pending_republish_seconds: int = 300
    outbox_poll_interval_seconds: float = 0.5
    outbox_batch_size: int = 100
    outbox_retention_days: int = 7
    document_retention_days_after_delete: int = 30
    idempotency_ttl_hours: int = 24
    pending_upload_cleanup_seconds: int = 3_600

    @field_validator("metrics_token", "llm_api_key", "s3_access_key_id", "s3_secret_access_key", "uploadthing_token", mode="before")
    @classmethod
    def _empty_secret_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("cors_allowed_origins", "trusted_hosts", mode="before")
    @classmethod
    def _parse_csv(cls, value: object) -> object:
        return _split_csv(value)

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        secret = self.jwt_secret.get_secret_value()
        if self.app_env != Environment.TEST and len(secret) < 32:
            raise ValueError("JWT_SECRET must be set to at least 32 characters")
        if self.app_env == Environment.PRODUCTION:
            if "*" in self.cors_allowed_origins:
                raise ValueError("CORS_ALLOWED_ORIGINS must not contain '*' in production")
            if self.metrics_token is None:
                raise ValueError("METRICS_TOKEN is required in production")
            if self.s3_create_buckets:
                raise ValueError("S3_CREATE_BUCKETS must be false in production")
        if self.originals_storage == "uploadthing":
            if self.uploadthing_token is None:
                raise ValueError("ORIGINALS_STORAGE=uploadthing requires UPLOADTHING_TOKEN")
            if self.is_production and self.uploadthing_acl == "public-read" and not self.uploadthing_allow_public_files:
                raise ValueError(
                    "UPLOADTHING_ACL=public-read makes original files reachable by URL; "
                    "use a paid app with UPLOADTHING_ACL=private or set UPLOADTHING_ALLOW_PUBLIC_FILES=true"
                )
        if self.extraction_provider == "hosted" and not self.ai_external_transmission_enabled:
            raise ValueError("EXTRACTION_PROVIDER=hosted requires AI_EXTERNAL_TRANSMISSION_ENABLED=true")
        if self.embedding_provider == "hosted" and not self.ai_external_transmission_enabled:
            raise ValueError("EMBEDDING_PROVIDER=hosted requires AI_EXTERNAL_TRANSMISSION_ENABLED=true")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def docs_enabled(self) -> bool:
        if self.api_docs_enabled is not None:
            return self.api_docs_enabled
        return not self.is_production

    @property
    def sync_database_url(self) -> str:
        url = self.database_url
        for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url[len(prefix) :]
        return url

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # ENV_FILE="" disables dotenv loading (tests must not depend on a developer's .env).
    env_file = os.environ.get("ENV_FILE", ".env") or None
    return Settings(_env_file=env_file)  # type: ignore[call-arg]
