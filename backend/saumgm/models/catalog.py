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

from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import BillingTiming, ItemType
from saumgm.models.base import (
    ZERO,
    LegacyMixin,
    Money,
    OrgScopedMixin,
    Percent,
    Quantity,
    fk,
    str_enum,
)


class RevenueCategory(IdMixin, OrgScopedMixin, Base):
    """Groups sales for reporting (Hosting, Domains, Development, ...)."""

    __tablename__ = "revenue_category"
    __table_args__ = (UniqueConstraint("organization_id", "name"), TABLE_ARGS)

    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CatalogItem(IdMixin, OrgScopedMixin, LegacyMixin, TimestampMixin, Base):
    """A product or service that can be put on an invoice or subscribed to."""

    __tablename__ = "catalog_item"
    __table_args__ = (UniqueConstraint("organization_id", "sku"), TABLE_ARGS)

    sku: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    item_type: Mapped[ItemType] = mapped_column(str_enum(ItemType))
    unit: Mapped[str | None] = mapped_column(String(20))
    price: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    default_discount_pct: Mapped[Decimal] = mapped_column(Percent, default=ZERO)
    tax_category_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("tax_category.id"), index=True
    )
    revenue_category_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("revenue_category.id"), index=True
    )
    # Subscription defaults
    billing_interval_months: Mapped[int | None] = mapped_column(Integer)
    billing_timing: Mapped[BillingTiming | None] = mapped_column(str_enum(BillingTiming))
    # Cost side, for resold items (domains, hosting, certificates, hardware)
    default_vendor_id: Mapped[int | None] = mapped_column(BigInteger, fk("party.id"), index=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Money)
    cogs_account_id: Mapped[int | None] = mapped_column(BigInteger, fk("account.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CatalogPackage(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """A named set of items with default prices ("Hosting + domain") that fills a new
    subscription's lines in one go. Changing a package later leaves subscriptions alone."""

    __tablename__ = "catalog_package"
    __table_args__ = (UniqueConstraint("organization_id", "name"), TABLE_ARGS)

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    items: Mapped[list["CatalogPackageItem"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="CatalogPackageItem.sort_order",
    )


class CatalogPackageItem(IdMixin, Base):
    __tablename__ = "catalog_package_item"
    __table_args__ = TABLE_ARGS

    package_id: Mapped[int] = mapped_column(
        BigInteger, fk("catalog_package.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    catalog_item_id: Mapped[int] = mapped_column(BigInteger, fk("catalog_item.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal(1))
    # Empty: the item's catalog price.
    price: Mapped[Decimal | None] = mapped_column(Money)
    discount_pct: Mapped[Decimal | None] = mapped_column(Percent)

    package: Mapped[CatalogPackage] = relationship(back_populates="items")
