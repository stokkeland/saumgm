"""Shared column types and mixins for all models."""

import enum
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, Enum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

# Money: 4 decimals keeps unit prices with fractions of a cent exact; totals are rounded to the
# currency's minor units by the application.
Money = Numeric(15, 4)
Quantity = Numeric(12, 4)
# Tax rates as fractions (0.08 = 8%).
Rate = Numeric(9, 6)
# Percentages (5 = 5%).
Percent = Numeric(7, 4)

ZERO = Decimal("0")


def str_enum(enum_cls: type[enum.Enum], length: int = 20) -> Enum:
    """Store a Python enum as VARCHAR of its values (no native ENUM; adding values needs no
    ALTER TABLE)."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        length=length,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )


def fk(target: str, *, ondelete: str | None = None, use_alter: bool = False) -> ForeignKey:
    return ForeignKey(target, ondelete=ondelete, use_alter=use_alter)


class OrgScopedMixin:
    """Top-level business records belong to one organization (see docs/design.md section 3)."""

    @declared_attr
    def organization_id(cls) -> Mapped[int]:
        return mapped_column(BigInteger, fk("organization.id"), index=True, nullable=False)


class LegacyMixin:
    """Identifiers and unmapped values carried over from the MS Access application."""

    legacy_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    legacy_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
