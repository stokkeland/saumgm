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

"""Bank and credit-card accounts, their registers, and statement reconciliations.

Balances are computed from the opening balance and the entries, never stored.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import BankAccountKind, BankEntryKind, BankEntryStatus
from saumgm.models.base import ZERO, Money, OrgScopedMixin, fk, str_enum


class BankAccount(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """A checking, savings or credit-card account (or PayPal), at a bank contact."""

    __tablename__ = "bank_account"
    __table_args__ = (UniqueConstraint("organization_id", "name"), TABLE_ARGS)

    party_id: Mapped[int | None] = mapped_column(BigInteger, fk("party.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[BankAccountKind] = mapped_column(str_enum(BankAccountKind))
    # Only the last digits are kept.
    number_last4: Mapped[str | None] = mapped_column(String(4))
    # The register starts here: the balance on that day. Entries before it are refused.
    opening_date: Mapped[date] = mapped_column(Date)
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class BankReconciliation(IdMixin, OrgScopedMixin, Base):
    """A statement the register was matched against; its entries became reconciled."""

    __tablename__ = "bank_reconciliation"
    __table_args__ = TABLE_ARGS

    bank_account_id: Mapped[int] = mapped_column(BigInteger, fk("bank_account.id"), index=True)
    statement_date: Mapped[date] = mapped_column(Date)
    statement_balance: Mapped[Decimal] = mapped_column(Money)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, fk("app_user.id"))


class BankEntry(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """One line of an account's register. Positive = money in, negative = money out (on a credit
    card a charge is negative: it adds to what is owed)."""

    __tablename__ = "bank_entry"
    __table_args__ = TABLE_ARGS

    bank_account_id: Mapped[int] = mapped_column(BigInteger, fk("bank_account.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    payee: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(100))  # check number
    # For reports and to make an expense from it later.
    account_id: Mapped[int | None] = mapped_column(BigInteger, fk("account.id"), index=True)
    status: Mapped[BankEntryStatus] = mapped_column(
        str_enum(BankEntryStatus), default=BankEntryStatus.UNCLEARED
    )
    kind: Mapped[BankEntryKind] = mapped_column(
        str_enum(BankEntryKind), default=BankEntryKind.MANUAL
    )
    # At most one of these links; deleting the deposit or expense deletes its line.
    deposit_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("deposit.id", ondelete="CASCADE"), index=True, unique=True
    )
    expense_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("expense.id", ondelete="CASCADE"), index=True, unique=True
    )
    # The other side of a transfer (each side points at the other).
    transfer_entry_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("bank_entry.id", ondelete="SET NULL"), index=True
    )
    reconciliation_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("bank_reconciliation.id"), index=True
    )
