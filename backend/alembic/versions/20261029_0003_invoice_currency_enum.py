"""invoice_records.currency: restrict to the CurrencyCode enum

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of app.shared.enums.CurrencyCode at this revision. A later change
# to the enum needs its own migration that replaces this constraint.
CURRENCY_CODES = (
    "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "DKK", "PLN", "CZK",
    "HUF", "INR", "BDT", "PKR", "LKR", "SGD", "HKD", "KRW", "TWD", "THB", "MYR", "IDR", "PHP", "VND",
    "AED", "SAR", "QAR", "BHD", "KWD", "OMR", "JOD", "TND", "ILS", "TRY", "ZAR", "NGN", "KES", "EGP",
    "MAD", "BRL", "MXN", "ARS", "CLP", "COP", "PEN", "RUB", "UAH", "RON", "BGN", "ISK", "CLF",
)  # fmt: skip

# Same name SQLAlchemy gives the enum CHECK on the model (ck_<table>_<enum name>).
CONSTRAINT = "ck_invoice_records_currencycode"


def upgrade() -> None:
    codes = ", ".join(f"'{c}'" for c in CURRENCY_CODES)
    bad = (
        op.get_bind()
        .execute(sa.text(f"SELECT DISTINCT currency FROM invoice_records WHERE currency IS NOT NULL AND currency NOT IN ({codes})"))
        .scalars()
        .all()
    )
    if bad:
        raise RuntimeError(f"invoice_records.currency has values outside CurrencyCode: {sorted(bad)}; correct them first")
    op.create_check_constraint(op.f(CONSTRAINT), "invoice_records", f"currency IN ({codes})")


def downgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "invoice_records", type_="check")
