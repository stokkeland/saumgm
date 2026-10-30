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

"""Assets: equipment and licenses, the business's own and those it manages for clients.

A first step toward a CMDB: relationships between assets, a maintenance log and links to
subscriptions can be added later without changing these tables.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import AssetStatus
from saumgm.models.base import Money, OrgScopedMixin, fk, str_enum


class AssetCategory(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """Laptop, Server, Software license... Each can define extra fields for its assets:
    `fields` is a list of {"key", "label", "type"} (type: text, number, date, bool)."""

    __tablename__ = "asset_category"
    __table_args__ = (UniqueConstraint("organization_id", "name"), TABLE_ARGS)

    name: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class Asset(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    __tablename__ = "asset"
    __table_args__ = (UniqueConstraint("organization_id", "tag"), TABLE_ARGS)

    # Numbered like invoices (A-0001) unless given.
    tag: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int | None] = mapped_column(BigInteger, fk("asset_category.id"), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[AssetStatus] = mapped_column(str_enum(AssetStatus), default=AssetStatus.IN_USE)
    # Whose it is: the business itself (the self party) or a client whose equipment is managed.
    owner_party_id: Mapped[int | None] = mapped_column(BigInteger, fk("party.id"), index=True)
    location: Mapped[str | None] = mapped_column(String(200))
    assigned_to: Mapped[str | None] = mapped_column(String(200))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_price: Mapped[Decimal | None] = mapped_column(Money)
    vendor_party_id: Mapped[int | None] = mapped_column(BigInteger, fk("party.id"), index=True)
    # The expense that paid for it.
    expense_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("expense.id", ondelete="SET NULL"), index=True
    )
    warranty_expires: Mapped[date | None] = mapped_column(Date, index=True)
    support_ends: Mapped[date | None] = mapped_column(Date, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    # The category's extra fields: {key: value}.
    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    attachments: Mapped[list["AssetAttachment"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class AssetAttachment(IdMixin, Base):
    """A receipt, photo or configuration file kept with an asset."""

    __tablename__ = "asset_attachment"
    __table_args__ = TABLE_ARGS

    asset_id: Mapped[int] = mapped_column(
        BigInteger, fk("asset.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[int] = mapped_column(BigInteger, fk("stored_file.id"), index=True)

    asset: Mapped[Asset] = relationship(back_populates="attachments")
