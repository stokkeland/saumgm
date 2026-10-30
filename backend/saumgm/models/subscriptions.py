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

"""Recurring things: client subscriptions (what is billed) and vendor subscriptions (what is
paid). They are separate lists, joined only by an information-only link from a client
subscription line to the vendor subscriptions it uses."""

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import SubscriptionStatus
from saumgm.models.base import ZERO, Money, OrgScopedMixin, Percent, Quantity, fk, str_enum


class Subscription(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """A recurring service a client has (hosting, a domain, a support agreement): a header with
    one or more lines, billed together on one invoice."""

    __tablename__ = "subscription"
    __table_args__ = TABLE_ARGS

    party_id: Mapped[int] = mapped_column(BigInteger, fk("party.id"), index=True)
    # What the subscription is for: a domain name, hosting account, server, contract no.
    service_identifier: Mapped[str | None] = mapped_column(String(255), index=True)
    billing_interval_months: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    next_bill_date: Mapped[date | None] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        str_enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE
    )
    notes: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list["SubscriptionLine"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        order_by="SubscriptionLine.sort_order",
    )


class SubscriptionLine(IdMixin, Base):
    __tablename__ = "subscription_line"
    __table_args__ = TABLE_ARGS

    subscription_id: Mapped[int] = mapped_column(
        BigInteger, fk("subscription.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    catalog_item_id: Mapped[int] = mapped_column(BigInteger, fk("catalog_item.id"), index=True)
    # Copied from the catalog item when the line is made; editable per client.
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal(1))
    price_override: Mapped[Decimal | None] = mapped_column(Money)
    discount_pct: Mapped[Decimal | None] = mapped_column(Percent)

    subscription: Mapped[Subscription] = relationship(back_populates="lines")
    uses: Mapped[list["SubscriptionUse"]] = relationship(
        back_populates="line", cascade="all, delete-orphan"
    )


class SubscriptionUse(IdMixin, Base):
    """A client subscription line depends on a vendor subscription (the server, the registrar
    account). Information only: shows the cost behind a sale and who depends on a cost."""

    __tablename__ = "subscription_use"
    __table_args__ = (
        UniqueConstraint("subscription_line_id", "vendor_subscription_id"),
        TABLE_ARGS,
    )

    subscription_line_id: Mapped[int] = mapped_column(
        BigInteger, fk("subscription_line.id", ondelete="CASCADE"), index=True
    )
    vendor_subscription_id: Mapped[int] = mapped_column(
        BigInteger, fk("vendor_subscription.id"), index=True
    )

    line: Mapped[SubscriptionLine] = relationship(back_populates="uses")


class VendorSubscription(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """Something the business pays for regularly: a rented server, a domain registration, a
    software license, phone and internet."""

    __tablename__ = "vendor_subscription"
    __table_args__ = TABLE_ARGS

    party_id: Mapped[int] = mapped_column(BigInteger, fk("party.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    service_identifier: Mapped[str | None] = mapped_column(String(255), index=True)
    amount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    interval_months: Mapped[int] = mapped_column(Integer)
    next_due_date: Mapped[date | None] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    expense_account_id: Mapped[int | None] = mapped_column(BigInteger, fk("account.id"), index=True)
    # Charged automatically (a card on file) rather than paid by hand; only changes how a
    # reminder is worded.
    autopay: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        str_enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE
    )
    notes: Mapped[str | None] = mapped_column(Text)
