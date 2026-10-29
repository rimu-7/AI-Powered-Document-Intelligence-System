"""storage_objects: original filename + metadata (direct uploads, UploadThing originals)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("storage_objects", sa.Column("original_filename", sa.String(length=255), nullable=True))
    op.add_column(
        "storage_objects",
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("storage_objects", "metadata_json")
    op.drop_column("storage_objects", "original_filename")
