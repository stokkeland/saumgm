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

from datetime import date

from sqlalchemy import BigInteger, Boolean, Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import AddressType, TaxBasis
from saumgm.models.base import fk, str_enum


class Organization(IdMixin, TimestampMixin, Base):
    """The business using the app. One row per business; everything else hangs off it."""

    __tablename__ = "organization"
    __table_args__ = TABLE_ARGS

    legal_name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200))
    payable_to: Mapped[str | None] = mapped_column(String(200))
    tagline: Mapped[str | None] = mapped_column(String(255))
    footer_text: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))
    tax_id: Mapped[str | None] = mapped_column(String(50))

    # The business as a party (expenses "for" itself, etc.). Nullable only to break the
    # organization <-> party creation cycle.
    self_party_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("party.id", use_alter=True), index=True
    )
    logo_file_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("stored_file.id", use_alter=True), index=True
    )

    # Localization
    country_code: Mapped[str] = mapped_column(String(2))
    currency_code: Mapped[str] = mapped_column(String(3))
    locale: Mapped[str] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(50))
    date_format: Mapped[str | None] = mapped_column(String(20))
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=1)

    # Tax
    tax_label: Mapped[str] = mapped_column(String(50), default="Sales Tax")
    prices_include_tax: Mapped[bool] = mapped_column(Boolean, default=False)
    tax_basis: Mapped[TaxBasis] = mapped_column(str_enum(TaxBasis), default=TaxBasis.ACCRUAL)
    # Sales and profit & loss: count income by invoice date (accrual) or payment date (cash).
    income_basis: Mapped[TaxBasis] = mapped_column(
        str_enum(TaxBasis), default=TaxBasis.ACCRUAL, server_default=TaxBasis.ACCRUAL.value
    )

    # Invoicing defaults
    default_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    invoice_revision_owner_only: Mapped[bool] = mapped_column(Boolean, default=False)
    # Email sender (Admin -> Email). The address must be on a domain verified with the provider.
    email_from_address: Mapped[str | None] = mapped_column(String(255))
    email_from_name: Mapped[str | None] = mapped_column(String(200))
    email_reply_to: Mapped[str | None] = mapped_column(String(255))
    # Reminders (Admin -> Reminders): how many days ahead the to-do list and the digest show
    # subscriptions to bill and vendor payments due; who gets the digest (empty: the owners).
    remind_bill_days: Mapped[int] = mapped_column(Integer, default=14, server_default="14")
    remind_pay_days: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    remind_to: Mapped[str | None] = mapped_column(String(1000))
    # Bank accounts whose last reconciled statement is older than this many days.
    remind_reconcile_days: Mapped[int] = mapped_column(Integer, default=35, server_default="35")

    addresses: Mapped[list["OrganizationAddress"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationAddress(IdMixin, Base):
    """Business addresses with validity periods, so old documents show the address in force."""

    __tablename__ = "organization_address"
    __table_args__ = TABLE_ARGS

    organization_id: Mapped[int] = mapped_column(
        BigInteger, fk("organization.id", ondelete="CASCADE"), index=True
    )
    address_type: Mapped[AddressType] = mapped_column(str_enum(AddressType))
    line1: Mapped[str | None] = mapped_column(String(200))
    line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country_code: Mapped[str | None] = mapped_column(String(2))
    phone: Mapped[str | None] = mapped_column(String(50))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)

    organization: Mapped[Organization] = relationship(back_populates="addresses")


class NumberSequence(IdMixin, Base):
    """Business number counters (invoice no., party no.). Never derived from AUTO_INCREMENT ids,
    which are not contiguous under Galera."""

    __tablename__ = "number_sequence"
    __table_args__ = (UniqueConstraint("organization_id", "name"), TABLE_ARGS)

    organization_id: Mapped[int] = mapped_column(
        BigInteger, fk("organization.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(30))
    next_value: Mapped[int] = mapped_column(BigInteger)
    prefix: Mapped[str] = mapped_column(String(20), default="")
    pad_width: Mapped[int] = mapped_column(Integer, default=0)

    def format(self, value: int) -> str:
        return f"{self.prefix}{str(value).zfill(self.pad_width)}"
