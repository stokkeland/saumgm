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
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import PaymentChannel, PaymentMethod
from saumgm.models.base import ArchivableMixin, LegacyMixin, Money, OrgScopedMixin, fk, str_enum


class Deposit(IdMixin, OrgScopedMixin, ArchivableMixin, LegacyMixin, TimestampMixin, Base):
    """A bank deposit (one deposit slip)."""

    __tablename__ = "deposit"
    __table_args__ = TABLE_ARGS

    bank_party_id: Mapped[int | None] = mapped_column(BigInteger, fk("party.id"), index=True)
    # Required for new deposits; one imported historical deposit has no date.
    deposit_date: Mapped[date | None] = mapped_column(Date, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    payments: Mapped[list["Payment"]] = relationship(back_populates="deposit")
    items: Mapped[list["DepositItem"]] = relationship(
        back_populates="deposit", cascade="all, delete-orphan"
    )


class DepositItem(IdMixin, Base):
    """A deposit line that is not a recorded payment (e.g. historical deposit details)."""

    __tablename__ = "deposit_item"
    __table_args__ = TABLE_ARGS

    deposit_id: Mapped[int] = mapped_column(
        BigInteger, fk("deposit.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Money)
    description: Mapped[str | None] = mapped_column(String(255))
    legacy_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    deposit: Mapped[Deposit] = relationship(back_populates="items")


class Payment(IdMixin, OrgScopedMixin, ArchivableMixin, LegacyMixin, TimestampMixin, Base):
    """Money received. Applied to invoices through allocations; waits as "undeposited funds"
    until it is put on a deposit."""

    __tablename__ = "payment"
    __table_args__ = TABLE_ARGS

    party_id: Mapped[int] = mapped_column(BigInteger, fk("party.id"), index=True)
    # Required for new payments; one imported historical payment has no date.
    received_date: Mapped[date | None] = mapped_column(Date, index=True)
    method: Mapped[PaymentMethod | None] = mapped_column(str_enum(PaymentMethod))
    channel: Mapped[PaymentChannel | None] = mapped_column(str_enum(PaymentChannel))
    reference: Mapped[str | None] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)
    deposit_id: Mapped[int | None] = mapped_column(BigInteger, fk("deposit.id"), index=True)
    # Imported: deposit tracking did not link payments, so these never show as undeposited.
    is_historical: Mapped[bool] = mapped_column(Boolean, default=False)

    deposit: Mapped[Deposit | None] = relationship(back_populates="payments")
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentAllocation(IdMixin, Base):
    """The part of a payment applied to one invoice."""

    __tablename__ = "payment_allocation"
    __table_args__ = TABLE_ARGS

    payment_id: Mapped[int] = mapped_column(
        BigInteger, fk("payment.id", ondelete="CASCADE"), index=True
    )
    invoice_id: Mapped[int] = mapped_column(BigInteger, fk("invoice.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    # The old system recorded tax and taxable amount per payment (cash-basis tax reports).
    legacy_sales_tax: Mapped[Decimal | None] = mapped_column(Money)
    legacy_taxable_amount: Mapped[Decimal | None] = mapped_column(Money)
    legacy_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    payment: Mapped[Payment] = relationship(back_populates="allocations")
