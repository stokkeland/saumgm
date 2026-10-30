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

from sqlalchemy import BigInteger, Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.models.base import ArchivableMixin, LegacyMixin, Money, OrgScopedMixin, fk


class Expense(IdMixin, OrgScopedMixin, ArchivableMixin, LegacyMixin, TimestampMixin, Base):
    """A purchase or cost, split over one or more accounts."""

    __tablename__ = "expense"
    __table_args__ = TABLE_ARGS

    expense_date: Mapped[date] = mapped_column(Date, index=True)
    entered_date: Mapped[date | None] = mapped_column(Date)
    vendor_party_id: Mapped[int | None] = mapped_column(BigInteger, fk("party.id"), index=True)
    # Who the cost was for: the business itself (self party) or a client (re-billable).
    for_party_id: Mapped[int | None] = mapped_column(BigInteger, fk("party.id"), index=True)
    reference: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    # Set when the expense was recorded as a payment of a vendor subscription.
    vendor_subscription_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("vendor_subscription.id"), index=True
    )

    # Paid from this bank or card account; its register gets a line for the total.
    paid_from_account_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("bank_account.id"), index=True
    )

    lines: Mapped[list["ExpenseLine"]] = relationship(
        back_populates="expense", cascade="all, delete-orphan", order_by="ExpenseLine.sort_order"
    )
    attachments: Mapped[list["ExpenseAttachment"]] = relationship(
        back_populates="expense", cascade="all, delete-orphan"
    )


class ExpenseLine(IdMixin, Base):
    __tablename__ = "expense_line"
    __table_args__ = TABLE_ARGS

    expense_id: Mapped[int] = mapped_column(
        BigInteger, fk("expense.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[int] = mapped_column(BigInteger, fk("account.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    description: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    legacy_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    expense: Mapped[Expense] = relationship(back_populates="lines")


class ExpenseAttachment(IdMixin, Base):
    """A receipt or invoice document attached to an expense."""

    __tablename__ = "expense_attachment"
    __table_args__ = TABLE_ARGS

    expense_id: Mapped[int] = mapped_column(
        BigInteger, fk("expense.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[int] = mapped_column(BigInteger, fk("stored_file.id"), index=True)

    expense: Mapped[Expense] = relationship(back_populates="attachments")
