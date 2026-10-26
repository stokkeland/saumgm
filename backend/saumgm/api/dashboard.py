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

"""Numbers for the dashboard: what is owed, what waits to be deposited, the year so far."""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from saumgm.api.deps import DbSession, Reader
from saumgm.enums import InvoiceKind, InvoiceStatus, SubscriptionStatus
from saumgm.models import (
    CatalogItem,
    Expense,
    ExpenseLine,
    Invoice,
    Organization,
    Party,
    Payment,
    Subscription,
)
from saumgm.schemas.types import Amount
from saumgm.services import invoices as invoice_service
from saumgm.services.payments import unapplied
from saumgm.timeutil import today_in

router = APIRouter(tags=["dashboard"])

RENEWAL_DAYS = 30


class Renewal(BaseModel):
    subscription_id: int
    party_id: int
    party_name: str
    item_name: str
    service_identifier: str | None
    next_bill_date: date


class Dashboard(BaseModel):
    today: date
    receivable: Amount
    open_invoices: int
    overdue: Amount
    overdue_invoices: int
    drafts: int
    undeposited: Amount
    undeposited_payments: int
    unapplied_credit: Amount
    year_start: date
    sales_this_year: Amount
    expenses_this_year: Amount
    renewals: list[Renewal]


@router.get("/dashboard")
def dashboard(auth: Reader, db: DbSession) -> Dashboard:
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    today = today_in(org.timezone)
    year_start = date(today.year if today.month >= org.fiscal_year_start_month else today.year - 1,
                      org.fiscal_year_start_month, 1)  # fmt: skip
    zero = Decimal(0)

    issued = db.scalars(
        select(Invoice).where(
            Invoice.organization_id == org.id,
            Invoice.kind == InvoiceKind.INVOICE,
            Invoice.status == InvoiceStatus.ISSUED,
        )
    ).all()
    infos = invoice_service.balances(db, issued, today)
    due = [i for i in infos.values() if i.balance_due > invoice_service.PAID_TOLERANCE]
    overdue = [i for i in due if i.overdue]

    drafts = db.scalar(
        select(func.count())
        .select_from(Invoice)
        .where(Invoice.organization_id == org.id, Invoice.status == InvoiceStatus.DRAFT)
    )
    waiting = db.scalars(
        select(Payment).where(
            Payment.organization_id == org.id,
            Payment.deposit_id.is_(None),
            Payment.is_historical.is_(False),
            Payment.archived_at.is_(None),
        )
    ).all()
    payments = db.scalars(select(Payment).where(Payment.organization_id == org.id)).all()

    sales = db.scalar(
        select(func.coalesce(func.sum(Invoice.subtotal), 0)).where(
            Invoice.organization_id == org.id,
            Invoice.status == InvoiceStatus.ISSUED,
            Invoice.kind == InvoiceKind.INVOICE,
            Invoice.issue_date >= year_start,
        )
    )
    credits = db.scalar(
        select(func.coalesce(func.sum(Invoice.subtotal), 0)).where(
            Invoice.organization_id == org.id,
            Invoice.status == InvoiceStatus.ISSUED,
            Invoice.kind == InvoiceKind.CREDIT_NOTE,
            Invoice.issue_date >= year_start,
        )
    )
    expenses = db.scalar(
        select(func.coalesce(func.sum(ExpenseLine.amount), 0))
        .join(Expense, Expense.id == ExpenseLine.expense_id)
        .where(Expense.organization_id == org.id, Expense.expense_date >= year_start)
    )

    renewals = db.execute(
        select(Subscription, Party.name, CatalogItem.name)
        .join(Party, Party.id == Subscription.party_id)
        .join(CatalogItem, CatalogItem.id == Subscription.catalog_item_id)
        .where(
            Subscription.organization_id == org.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.next_bill_date <= today + timedelta(days=RENEWAL_DAYS),
        )
        .order_by(Subscription.next_bill_date)
        .limit(20)
    ).all()

    return Dashboard(
        today=today,
        receivable=sum((i.balance_due for i in due), zero),
        open_invoices=len(due),
        overdue=sum((i.balance_due for i in overdue), zero),
        overdue_invoices=len(overdue),
        drafts=drafts or 0,
        undeposited=sum((p.amount for p in waiting), zero),
        undeposited_payments=len(waiting),
        unapplied_credit=sum((unapplied(p) for p in payments if unapplied(p) > 0), zero),
        year_start=year_start,
        sales_this_year=Decimal(sales or 0) - Decimal(credits or 0),
        expenses_this_year=Decimal(expenses or 0),
        renewals=[
            Renewal(
                subscription_id=sub.id,
                party_id=sub.party_id,
                party_name=party_name,
                item_name=item_name,
                service_identifier=sub.service_identifier,
                next_bill_date=sub.next_bill_date,
            )
            for sub, party_name, item_name in renewals
            if sub.next_bill_date is not None
        ],
    )
