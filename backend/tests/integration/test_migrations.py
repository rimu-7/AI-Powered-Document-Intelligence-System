from __future__ import annotations

from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import get_settings
from app.models import Base

pytestmark = pytest.mark.integration


def test_schema_matches_models_and_indexes_exist(configured: Any) -> None:
    engine = create_engine(get_settings().sync_database_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], diff
        indexes = {r[0] for r in conn.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname='public'"))}
        assert {
            "ix_document_chunks_embedding_hnsw",
            "ix_document_chunks_tsv",
            "uq_review_tasks_open_invoice",
            "ix_outbox_events_unpublished",
        } <= indexes
        method = conn.execute(
            text("SELECT am.amname FROM pg_class c JOIN pg_am am ON am.oid = c.relam WHERE c.relname = 'ix_document_chunks_embedding_hnsw'")
        ).scalar_one()
        assert method == "hnsw"
        money_type = conn.execute(
            text(
                "SELECT data_type, numeric_scale FROM information_schema.columns WHERE table_name='invoice_records' AND column_name='total_amount'"
            )
        ).one()
        assert money_type == ("numeric", 4)
    engine.dispose()


def test_downgrade_and_upgrade_roundtrip(configured: Any) -> None:
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    # Pooled connections cache prepared statements for the dropped tables.
    from tests.conftest import _clear_caches

    _clear_caches()
