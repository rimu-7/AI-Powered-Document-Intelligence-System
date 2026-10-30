"""Automatic currency resolution: organization currency policy and currency source

* organizations.default_currency, organizations.currency_symbol_rules
* invoice_records.currency_source (how the currency was decided), backfilled
  for existing rows

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copies of the enums at this revision.
CURRENCY_CODES = (
    "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "DKK", "PLN", "CZK",
    "HUF", "INR", "BDT", "PKR", "LKR", "SGD", "HKD", "KRW", "TWD", "THB", "MYR", "IDR", "PHP", "VND",
    "AED", "SAR", "QAR", "BHD", "KWD", "OMR", "JOD", "TND", "ILS", "TRY", "ZAR", "NGN", "KES", "EGP",
    "MAD", "BRL", "MXN", "ARS", "CLP", "COP", "PEN", "RUB", "UAH", "RON", "BGN", "ISK", "CLF",
)  # fmt: skip
CURRENCY_SOURCES = (
    "PRINTED", "DOCUMENT_CONTEXT", "SUPPLIER_HISTORY", "ORGANIZATION_RULE", "LEARNED", "ORGANIZATION_DEFAULT", "HUMAN",
)  # fmt: skip

ORG_CURRENCY_CHECK = "ck_organizations_currencycode"
SOURCE_CHECK = "ck_invoice_records_currencysource"


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.add_column("organizations", sa.Column("default_currency", sa.String(length=3), nullable=True))
    op.create_check_constraint(op.f(ORG_CURRENCY_CHECK), "organizations", f"default_currency IN ({_in(CURRENCY_CODES)})")
    op.add_column(
        "organizations",
        sa.Column(
            "currency_symbol_rules",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("organizations", "currency_symbol_rules", server_default=None)

    op.add_column("invoice_records", sa.Column("currency_source", sa.String(length=40), nullable=True))
    op.create_check_constraint(op.f(SOURCE_CHECK), "invoice_records", f"currency_source IN ({_in(CURRENCY_SOURCES)})")
    # Existing rows: a reviewer's correction, an earlier address-based inference
    # (evidence marked DERIVED), or printed on the invoice.
    op.execute(
        """
        UPDATE invoice_records SET currency_source = CASE
            WHEN corrected_fields_json ? 'currency' THEN 'HUMAN'
            WHEN source_evidence_json -> 'currency' ->> 'support' = 'DERIVED' THEN 'DOCUMENT_CONTEXT'
            ELSE 'PRINTED'
        END
        WHERE currency IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(op.f(SOURCE_CHECK), "invoice_records", type_="check")
    op.drop_column("invoice_records", "currency_source")
    op.drop_column("organizations", "currency_symbol_rules")
    op.drop_constraint(op.f(ORG_CURRENCY_CHECK), "organizations", type_="check")
    op.drop_column("organizations", "default_currency")
