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

"""Client subscriptions and the billing run that turns due periods into draft invoices.

Pricing: a subscription bills `quantity` x unit price for each billing period, where the unit price
is the subscription's override or the catalog item's price. Periods are billed in advance (the
period starts on the bill date) unless the catalog item says arrears (the period ends the day
before the bill date).
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from saumgm.enums import BillingTiming, SubscriptionStatus
from saumgm.models import CatalogItem, Invoice, Organization, Party, Subscription
from saumgm.schemas.invoices import LineIn
from saumgm.services import invoices as invoice_service

MAX_PERIODS_PER_RUN = 24  # catch-up limit per subscription and run


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def billing_period(sub: Subscription, item: CatalogItem, bill_date: date) -> tuple[date, date]:
    if item.billing_timing == BillingTiming.ARREARS:
        start = add_months(bill_date, -sub.billing_interval_months)
        return start, bill_date - timedelta(days=1)
    return bill_date, add_months(bill_date, sub.billing_interval_months) - timedelta(days=1)


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
            )
            .order_by(Subscription.party_id, Subscription.next_bill_date, Subscription.id)
        )
    )


def run_billing(session: Session, org: Organization, through: date) -> RunResult:
    """Create one draft invoice per client for every subscription period due through `through`,
    and move each subscription's next bill date forward."""
    result = RunResult()
    lines_by_party: dict[int, list[LineIn]] = defaultdict(list)

    for sub in due_subscriptions(session, org.id, through):
        item = session.get(CatalogItem, sub.catalog_item_id)
        assert item is not None
        assert sub.next_bill_date is not None
        periods = 0
        while (
            sub.next_bill_date <= through
            and (sub.end_date is None or sub.next_bill_date <= sub.end_date)
            and periods < MAX_PERIODS_PER_RUN
        ):
            start, end = billing_period(sub, item, sub.next_bill_date)
            label = (
                f"{item.name} - {sub.service_identifier}" if sub.service_identifier else item.name
            )
            lines_by_party[sub.party_id].append(
                LineIn(
                    catalog_item_id=item.id,
                    subscription_id=sub.id,
                    description=f"{label} ({start.isoformat()} to {end.isoformat()})",
                    quantity=sub.quantity,
                    unit_price=sub.price_override if sub.price_override is not None else item.price,
                    discount_pct=sub.discount_pct,
                )
            )
            sub.next_bill_date = add_months(sub.next_bill_date, sub.billing_interval_months)
            periods += 1
        if sub.end_date is not None and sub.next_bill_date > sub.end_date and not sub.auto_renew:
            sub.status = SubscriptionStatus.CANCELLED
        if periods:
            result.subscriptions_billed += 1

    for party_id, lines in lines_by_party.items():
        party = session.get(Party, party_id)
        assert party is not None
        invoice = invoice_service.create_invoice(
            session, org, party, {"notes": "Subscription billing"}, lines
        )
        result.invoices.append(invoice)
        result.lines_created += len(lines)
    session.flush()
    return result
