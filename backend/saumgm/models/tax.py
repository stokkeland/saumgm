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

"""Sales tax configuration (docs/design.md section 4.7).

Jurisdictions form a tree (country > state/province > county > city). Tax is only charged in
jurisdictions where the business has a registration; whether an item is taxable comes from its
tax category and the jurisdiction's taxability rules; clients can hold exemptions.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import FilingFrequency, JurisdictionLevel
from saumgm.models.base import Money, OrgScopedMixin, Rate, fk, str_enum


class TaxJurisdiction(IdMixin, OrgScopedMixin, Base):
    __tablename__ = "tax_jurisdiction"
    __table_args__ = (UniqueConstraint("organization_id", "code"), TABLE_ARGS)

    parent_id: Mapped[int | None] = mapped_column(BigInteger, fk("tax_jurisdiction.id"), index=True)
    level: Mapped[JurisdictionLevel] = mapped_column(str_enum(JurisdictionLevel))
    # ISO 3166 style: "US", "US-NY", then free-form below, e.g. "US-NY-CATTARAUGUS".
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    # Code used on tax returns (e.g. NY jurisdiction reporting codes).
    reporting_code: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    parent: Mapped["TaxJurisdiction | None"] = relationship(remote_side="TaxJurisdiction.id")
    rates: Mapped[list["TaxRate"]] = relationship(
        back_populates="jurisdiction", cascade="all, delete-orphan"
    )


class TaxRate(IdMixin, Base):
    """A rate in force for a period. Old invoices keep the rate they were issued with."""

    __tablename__ = "tax_rate"
    __table_args__ = TABLE_ARGS

    jurisdiction_id: Mapped[int] = mapped_column(
        BigInteger, fk("tax_jurisdiction.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    rate: Mapped[Decimal] = mapped_column(Rate)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)

    jurisdiction: Mapped[TaxJurisdiction] = relationship(back_populates="rates")


class TaxRegistration(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """Where the business is registered to collect tax."""

    __tablename__ = "tax_registration"
    __table_args__ = TABLE_ARGS

    jurisdiction_id: Mapped[int] = mapped_column(BigInteger, fk("tax_jurisdiction.id"), index=True)
    registration_number: Mapped[str | None] = mapped_column(String(100))
    filing_frequency: Mapped[FilingFrequency | None] = mapped_column(str_enum(FilingFrequency))
    # First month of the filing year: 1 = calendar quarters/years; New York uses 3
    # (quarters Mar-May, Jun-Aug, Sep-Nov, Dec-Feb; annual Mar-Feb).
    period_start_month: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class TaxFiling(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """A tax return filed for one period of a registration."""

    __tablename__ = "tax_filing"
    __table_args__ = (UniqueConstraint("registration_id", "period_start"), TABLE_ARGS)

    registration_id: Mapped[int] = mapped_column(
        BigInteger, fk("tax_registration.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    filed_on: Mapped[date] = mapped_column(Date)
    amount_paid: Mapped[Decimal | None] = mapped_column(Money)
    reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)


class TaxCategory(IdMixin, OrgScopedMixin, Base):
    """Taxability class of a catalog item (tangible goods, hosting, labor, ...)."""

    __tablename__ = "tax_category"
    __table_args__ = (UniqueConstraint("organization_id", "code"), TABLE_ARGS)

    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TaxabilityRule(IdMixin, Base):
    """Whether a tax category is taxable in a jurisdiction. Inherited down the jurisdiction tree
    unless a lower level overrides it."""

    __tablename__ = "taxability_rule"
    __table_args__ = (UniqueConstraint("jurisdiction_id", "tax_category_id"), TABLE_ARGS)

    jurisdiction_id: Mapped[int] = mapped_column(
        BigInteger, fk("tax_jurisdiction.id", ondelete="CASCADE"), index=True
    )
    tax_category_id: Mapped[int] = mapped_column(
        BigInteger, fk("tax_category.id", ondelete="CASCADE"), index=True
    )
    is_taxable: Mapped[bool] = mapped_column(Boolean)


class TaxExemption(IdMixin, TimestampMixin, Base):
    """A client's exemption certificate; jurisdiction NULL means it applies everywhere."""

    __tablename__ = "tax_exemption"
    __table_args__ = TABLE_ARGS

    party_id: Mapped[int] = mapped_column(
        BigInteger, fk("party.id", ondelete="CASCADE"), index=True
    )
    jurisdiction_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("tax_jurisdiction.id"), index=True
    )
    certificate_type: Mapped[str] = mapped_column(String(50))
    certificate_number: Mapped[str | None] = mapped_column(String(100))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    file_id: Mapped[int | None] = mapped_column(BigInteger, fk("stored_file.id"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
