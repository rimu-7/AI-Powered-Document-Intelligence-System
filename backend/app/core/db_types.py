"""Reusable column types."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Numeric
from sqlalchemy.dialects.postgresql import JSONB

# Monetary amounts: 20 digits, 4 decimal places. Covers 3-decimal currencies
# (BHD, KWD) and 4-decimal accounting units. Currency precision is applied in
# the application (see app.shared.money); the column never stores floats.
MONEY = Numeric(20, 4, asdecimal=True)
QUANTITY = Numeric(20, 6, asdecimal=True)
UNIT_PRICE = Numeric(20, 6, asdecimal=True)
RATIO = Numeric(6, 4, asdecimal=True)

JSON = JSONB(none_as_null=True)


def enum_type(enum_cls: type[StrEnum], name: str | None = None) -> SAEnum:
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=40,
        validate_strings=True,
        name=name or enum_cls.__name__.lower(),
        values_callable=lambda e: [m.value for m in e],
    )


def json_default() -> dict[str, Any]:
    return {}
