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

"""Client subscriptions and the billing run that turns due periods into draft invoices, and
vendor subscriptions with their payments.

Pricing: each subscription line bills `quantity` x unit price for each billing period, where the
unit price is the line's override or the catalog item's price. Periods are billed in advance (the
period starts on the bill date) unless the line's catalog item says arrears (the period ends the
day before the bill date).

Costs: a vendor subscription used by several client subscription lines (one server, many hosting
clients) is shared equally between the active ones. The figures are information only.
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from saumgm.enums import BillingTiming, SubscriptionStatus
from saumgm.models import (
    CatalogItem,
    Expense,
    ExpenseLine,
    Invoice,
    Organization,
    Party,
    Subscription,
    SubscriptionLine,
    SubscriptionUse,
    VendorSubscription,
)
from saumgm.models.base import ZERO
from saumgm.schemas.invoices import LineIn
from saumgm.services import invoices as invoice_service
from saumgm.services import money
from saumgm.timeutil import today_in

MAX_PERIODS_PER_RUN = 24  # catch-up limit per subscription and run


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def billing_period(interval: int, item: CatalogItem, bill_date: date) -> tuple[date, date]:
    if item.billing_timing == BillingTiming.ARREARS:
        start = add_months(bill_date, -interval)
        return start, bill_date - timedelta(days=1)
    return bill_date, add_months(bill_date, interval) - timedelta(days=1)


def unit_price(line: SubscriptionLine, item: CatalogItem) -> Decimal:
    return line.price_override if line.price_override is not None else item.price


def line_total(line: SubscriptionLine, item: CatalogItem, currency: str) -> Decimal:
    """Per billing period, before tax, as the invoice line will show it."""
    price = unit_price(line, item)
    pct = line.discount_pct if line.discount_pct is not None else item.default_discount_pct
    return money.line_total(price, money.discount_amount(price, pct), line.quantity, currency)


def monthly(amount: Decimal, months: int, currency: str) -> Decimal:
    return money.round_money(amount / months, currency)


def advance(next_date: date | None, interval: int) -> date | None:
    return add_months(next_date, interval) if next_date is not None else None


def finish_if_ended(
    sub: Subscription | VendorSubscription, next_date: date | None, auto_renew: bool
) -> None:
    """Past its end date and not renewing: nothing more is due."""
    if (
        sub.end_date is not None
        and next_date is not None
        and next_date > sub.end_date
        and not auto_renew
    ):
        sub.status = SubscriptionStatus.CANCELLED


def users_of(session: Session, vendor_ids: set[int]) -> dict[int, int]:
    """How many lines of active client subscriptions use each vendor subscription."""
    if not vendor_ids:
        return {}
    rows = session.execute(
        select(SubscriptionUse.vendor_subscription_id, func.count())
        .join(SubscriptionLine, SubscriptionLine.id == SubscriptionUse.subscription_line_id)
        .join(Subscription, Subscription.id == SubscriptionLine.subscription_id)
        .where(
            SubscriptionUse.vendor_subscription_id.in_(vendor_ids),
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        .group_by(SubscriptionUse.vendor_subscription_id)
    )
    return {vendor_id: count for vendor_id, count in rows}


# -- billing run ----------------------------------------------------------------------------------


@dataclass
class RunResult:
    invoices: list[Invoice] = field(default_factory=list)
    lines_created: int = 0
    subscriptions_billed: int = 0


def due_subscriptions(session: Session, org_id: int, through: date) -> list[Subscription]:
    return list(
        session.scalars(
            select(Subscription)
            .where(
                Subscription.organization_id == org_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.next_bill_date.is_not(None),
                Subscription.next_bill_date <= through,
                or_(
                    Subscription.end_date.is_(None),
                    Subscription.next_bill_date <= Subscription.end_date,
                ),
                Subscription.lines.any(),
            )
            .order_by(Subscription.party_id, Subscription.next_bill_date, Subscription.id)
        )
    )


def _period_lines(session: Session, sub: Subscription, bill_date: date) -> list[LineIn]:
    lines = []
    for line in sub.lines:
        item = session.get(CatalogItem, line.catalog_item_id)
        assert item is not None
        start, end = billing_period(sub.billing_interval_months, item, bill_date)
        label = (
            f"{line.description} - {sub.service_identifier}"
            if sub.service_identifier
            else line.description
        )
        lines.append(
            LineIn(
                catalog_item_id=item.id,
                subscription_id=sub.id,
                description=f"{label} ({start.isoformat()} to {end.isoformat()})",
                quantity=line.quantity,
                unit_price=unit_price(line, item),
                discount_pct=line.discount_pct,
            )
        )
    return lines


def run_billing(
    session: Session, org: Organization, through: date, *, combine: bool = False
) -> RunResult:
    """Create a draft invoice per subscription for every period due through `through` (with
    `combine`, one per client for its subscriptions due on the same day), and move each
    subscription's next bill date forward."""
    result = RunResult()
    groups: dict[tuple[int, int | date], list[LineIn]] = defaultdict(list)

    for sub in due_subscriptions(session, org.id, through):
        assert sub.next_bill_date is not None
        key: tuple[int, int | date] = (
            (sub.party_id, sub.next_bill_date) if combine else (sub.party_id, sub.id)
        )
        periods = 0
        while (
            sub.next_bill_date <= through
            and (sub.end_date is None or sub.next_bill_date <= sub.end_date)
            and periods < MAX_PERIODS_PER_RUN
        ):
            groups[key].extend(_period_lines(session, sub, sub.next_bill_date))
            sub.next_bill_date = add_months(sub.next_bill_date, sub.billing_interval_months)
            periods += 1
        finish_if_ended(sub, sub.next_bill_date, sub.auto_renew)
        if periods:
            result.subscriptions_billed += 1

    for (party_id, _), lines in groups.items():
        party = session.get(Party, party_id)
        assert party is not None
        invoice = invoice_service.create_invoice(
            session, org, party, {"notes": "Subscription billing"}, lines
        )
        result.invoices.append(invoice)
        result.lines_created += len(lines)
    session.flush()
    return result


# -- vendor subscriptions -------------------------------------------------------------------------


class VendorPaymentError(ValueError):
    pass


def record_payment(
    session: Session,
    org: Organization,
    sub: VendorSubscription,
    paid_date: date,
    *,
    amount: Decimal | None = None,
    account_id: int | None = None,
    reference: str | None = None,
    description: str | None = None,
) -> Expense:
    """The expense for one period, and the next due date one interval on. Nothing else."""
    account_id = account_id or sub.expense_account_id
    if account_id is None:
        raise VendorPaymentError("Choose the expense account (the subscription has none)")
    amount = amount if amount is not None else sub.amount
    if amount <= ZERO:
        raise VendorPaymentError("The amount must be more than zero")
    label = f"{sub.name} - {sub.service_identifier}" if sub.service_identifier else sub.name
    expense = Expense(
        organization_id=org.id,
        expense_date=paid_date,
        entered_date=today_in(org.timezone),
        vendor_party_id=sub.party_id,
        for_party_id=org.self_party_id,
        reference=reference,
        description=description or label,
        vendor_subscription_id=sub.id,
    )
    expense.lines = [ExpenseLine(account_id=account_id, amount=amount, description=label)]
    session.add(expense)
    sub.next_due_date = advance(sub.next_due_date, sub.interval_months)
    finish_if_ended(sub, sub.next_due_date, sub.auto_renew)
    session.flush()
    return expense
