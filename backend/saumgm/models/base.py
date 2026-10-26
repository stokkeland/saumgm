# SauMGM - Sauen Management System: billing, sales tax and bookkeeping for small businesses
# Copyright (C) 2026 J. Thomas Stokkeland - https://www.saumgm.com/
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details. You should have received a copy of the
# GNU General Public License along with this program (the LICENSE file); if not, see
# <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared column types and mixins for all models."""

import enum
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Enum, ForeignKey, Numeric
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


class ArchivableMixin:
    """Records can be archived: kept in place, but hidden from everyday lists unless asked for.
    NULL means current; otherwise when it was archived."""

    archived_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class LegacyMixin:
    """Identifiers and unmapped values carried over from the MS Access application."""

    legacy_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    legacy_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
