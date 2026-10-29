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

"""Vendor subscriptions: what the business pays for regularly, and recording those payments."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from saumgm.api.common import (
    LimitParam,
    OffsetParam,
    Page,
    apply_changes,
    conflict,
    get_owned,
    paginate,
)
from saumgm.api.deps import Auth, DbSession, Editor, Reader
from saumgm.enums import SubscriptionStatus
from saumgm.models import (
    Account,
    Expense,
    Organization,
    Party,
    Subscription,
    SubscriptionLine,
    SubscriptionUse,
    VendorSubscription,
)
from saumgm.schemas.subscriptions import (
    UsedBy,
    VendorPaymentIn,
    VendorPaymentOut,
    VendorSubscriptionCreate,
    VendorSubscriptionOut,
    VendorSubscriptionPatch,
)
from saumgm.services import subscriptions as service

router = APIRouter(prefix="/vendor-subscriptions", tags=["vendor subscriptions"])


def vendor_subscription_out(db: Session, sub: VendorSubscription) -> VendorSubscriptionOut:
    vendor = db.get(Party, sub.party_id)
    org = db.get(Organization, sub.organization_id)
    assert org is not None
    account = db.get(Account, sub.expense_account_id) if sub.expense_account_id else None
    last_paid, payments = db.execute(
        select(func.max(Expense.expense_date), func.count()).where(
            Expense.vendor_subscription_id == sub.id
        )
    ).one()
    used_by = db.execute(
        select(Subscription, Party.name, SubscriptionLine.description)
        .join(SubscriptionLine, SubscriptionLine.subscription_id == Subscription.id)
        .join(SubscriptionUse, SubscriptionUse.subscription_line_id == SubscriptionLine.id)
        .join(Party, Party.id == Subscription.party_id)
        .where(SubscriptionUse.vendor_subscription_id == sub.id)
        .order_by(Party.name, Subscription.id)
    ).all()
    return VendorSubscriptionOut(
        id=sub.id,
        party_id=sub.party_id,
        vendor_name=vendor.name if vendor else "",
        name=sub.name,
        service_identifier=sub.service_identifier,
        amount=sub.amount,
        interval_months=sub.interval_months,
        monthly_amount=service.monthly(sub.amount, sub.interval_months, org.currency_code),
        next_due_date=sub.next_due_date,
        end_date=sub.end_date,
        expense_account_id=sub.expense_account_id,
        expense_account_code=account.code if account else None,
        expense_account_name=account.name if account else None,
        autopay=sub.autopay,
        auto_renew=sub.auto_renew,
        status=sub.status,
        notes=sub.notes,
        last_paid_date=last_paid,
        payments=payments,
        used_by=[
            UsedBy(
                subscription_id=client_sub.id,
                party_id=client_sub.party_id,
                party_name=party_name,
                service_identifier=client_sub.service_identifier,
                description=description,
                status=client_sub.status,
            )
            for client_sub, party_name, description in used_by
        ],
    )


def _check_refs(
    db: Session, auth: Auth, body: VendorSubscriptionCreate | VendorSubscriptionPatch
) -> None:
    if body.party_id is not None:
        get_owned(db, Party, body.party_id, auth.organization_id)
    if body.expense_account_id is not None:
        get_owned(db, Account, body.expense_account_id, auth.organization_id)


@router.get("")
def list_vendor_subscriptions(
    auth: Reader,
    db: DbSession,
    party_id: int | None = None,
    status_: SubscriptionStatus | None = Query(None, alias="status"),
    due_through: date | None = Query(None, description="Next due date on or before this day"),
    q: str | None = Query(None, description="Search the name and what it is for"),
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[VendorSubscriptionOut]:
    stmt: Any = (
        select(VendorSubscription)
        .where(VendorSubscription.organization_id == auth.organization_id)
        .order_by(VendorSubscription.next_due_date, VendorSubscription.id)
    )
    if party_id is not None:
        stmt = stmt.where(VendorSubscription.party_id == party_id)
    if status_ is not None:
        stmt = stmt.where(VendorSubscription.status == status_)
    if due_through is not None:
        stmt = stmt.where(VendorSubscription.next_due_date <= due_through)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                VendorSubscription.name.ilike(pattern),
                VendorSubscription.service_identifier.ilike(pattern),
            )
        )
    items, total = paginate(db, stmt, limit, offset)
    return Page(
        items=[vendor_subscription_out(db, s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_vendor_subscription(
    body: VendorSubscriptionCreate, auth: Editor, db: DbSession
) -> VendorSubscriptionOut:
    _check_refs(db, auth, body)
    sub = VendorSubscription(organization_id=auth.organization_id, **body.model_dump())
    db.add(sub)
    db.flush()
    db.commit()
    return vendor_subscription_out(db, sub)


@router.get("/{subscription_id}")
def get_vendor_subscription(
    subscription_id: int, auth: Reader, db: DbSession
) -> VendorSubscriptionOut:
    sub = get_owned(db, VendorSubscription, subscription_id, auth.organization_id)
    return vendor_subscription_out(db, sub)


@router.patch("/{subscription_id}")
def update_vendor_subscription(
    subscription_id: int, body: VendorSubscriptionPatch, auth: Editor, db: DbSession
) -> VendorSubscriptionOut:
    sub = get_owned(db, VendorSubscription, subscription_id, auth.organization_id)
    _check_refs(db, auth, body)
    apply_changes(sub, body)
    db.commit()
    return vendor_subscription_out(db, sub)


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor_subscription(subscription_id: int, auth: Editor, db: DbSession) -> None:
    sub = get_owned(db, VendorSubscription, subscription_id, auth.organization_id)
    if db.scalars(select(Expense.id).where(Expense.vendor_subscription_id == sub.id)).first():
        raise conflict("This subscription has payments; cancel it instead")
    for use in db.scalars(
        select(SubscriptionUse).where(SubscriptionUse.vendor_subscription_id == sub.id)
    ):
        db.delete(use)  # one by one, so the audit log sees each link go
    db.delete(sub)
    db.commit()


@router.post("/{subscription_id}/payments", status_code=status.HTTP_201_CREATED)
def record_payment(
    subscription_id: int, body: VendorPaymentIn, auth: Editor, db: DbSession
) -> VendorPaymentOut:
    """Book the payment as an expense and move the next due date on by one interval."""
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    sub = get_owned(db, VendorSubscription, subscription_id, auth.organization_id)
    if body.expense_account_id is not None:
        get_owned(db, Account, body.expense_account_id, auth.organization_id)
    try:
        expense = service.record_payment(
            db, org, sub, body.paid_date, amount=body.amount, account_id=body.expense_account_id,
            reference=body.reference, description=body.description,
        )  # fmt: skip
    except service.VendorPaymentError as exc:
        raise conflict(str(exc)) from exc
    db.commit()
    return VendorPaymentOut(expense_id=expense.id, subscription=vendor_subscription_out(db, sub))
