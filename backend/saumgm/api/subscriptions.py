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

"""Client subscriptions (hosting, domains, support agreements) and the billing run."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import select
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
from saumgm.models import CatalogItem, InvoiceLine, Organization, Party, Subscription
from saumgm.schemas.invoices import InvoiceListItem
from saumgm.schemas.money import (
    BillingRunRequest,
    BillingRunResult,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionPatch,
)
from saumgm.services import invoices as invoice_service
from saumgm.services import subscriptions as service
from saumgm.timeutil import today_in

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def subscription_out(db: Session, sub: Subscription) -> SubscriptionOut:
    party = db.get(Party, sub.party_id)
    item = db.get(CatalogItem, sub.catalog_item_id)
    assert party is not None and item is not None
    return SubscriptionOut(
        id=sub.id,
        party_id=sub.party_id,
        party_name=party.name,
        catalog_item_id=sub.catalog_item_id,
        item_name=item.name,
        quantity=sub.quantity,
        price_override=sub.price_override,
        unit_price=sub.price_override if sub.price_override is not None else item.price,
        discount_pct=sub.discount_pct,
        service_identifier=sub.service_identifier,
        billing_interval_months=sub.billing_interval_months,
        start_date=sub.start_date,
        next_bill_date=sub.next_bill_date,
        end_date=sub.end_date,
        auto_renew=sub.auto_renew,
        status=sub.status,
        vendor_party_id=sub.vendor_party_id,
        vendor_renewal_date=sub.vendor_renewal_date,
        unit_cost=sub.unit_cost,
        notes=sub.notes,
    )


def _item(db: Session, auth: Auth, item_id: int) -> CatalogItem:
    return get_owned(db, CatalogItem, item_id, auth.organization_id)


@router.get("")
def list_subscriptions(
    auth: Reader,
    db: DbSession,
    party_id: int | None = None,
    status_: SubscriptionStatus | None = Query(None, alias="status"),
    due_through: date | None = Query(None, description="Next bill date on or before this day"),
    vendor_renewal_through: date | None = None,
    q: str | None = Query(None, description="Search the service identifier"),
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[SubscriptionOut]:
    stmt: Any = (
        select(Subscription)
        .where(Subscription.organization_id == auth.organization_id)
        .order_by(Subscription.next_bill_date, Subscription.id)
    )
    if party_id is not None:
        stmt = stmt.where(Subscription.party_id == party_id)
    if status_ is not None:
        stmt = stmt.where(Subscription.status == status_)
    if due_through is not None:
        stmt = stmt.where(Subscription.next_bill_date <= due_through)
    if vendor_renewal_through is not None:
        stmt = stmt.where(Subscription.vendor_renewal_date <= vendor_renewal_through)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(Subscription.service_identifier.ilike(pattern))
    items, total = paginate(db, stmt, limit, offset)
    return Page(
        items=[subscription_out(db, s) for s in items], total=total, limit=limit, offset=offset
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_subscription(body: SubscriptionCreate, auth: Editor, db: DbSession) -> SubscriptionOut:
    get_owned(db, Party, body.party_id, auth.organization_id)
    if body.vendor_party_id is not None:
        get_owned(db, Party, body.vendor_party_id, auth.organization_id)
    item = _item(db, auth, body.catalog_item_id)
    interval = body.billing_interval_months or item.billing_interval_months
    if not interval:
        raise conflict("Set billing_interval_months (the catalog item has no default)")
    sub = Subscription(
        organization_id=auth.organization_id,
        **body.model_dump(exclude={"billing_interval_months", "next_bill_date"}),
        billing_interval_months=interval,
        next_bill_date=body.next_bill_date or body.start_date,
    )
    db.add(sub)
    db.flush()
    db.commit()
    return subscription_out(db, sub)


@router.get("/{subscription_id}")
def get_subscription(subscription_id: int, auth: Reader, db: DbSession) -> SubscriptionOut:
    return subscription_out(db, get_owned(db, Subscription, subscription_id, auth.organization_id))


@router.patch("/{subscription_id}")
def update_subscription(
    subscription_id: int, body: SubscriptionPatch, auth: Editor, db: DbSession
) -> SubscriptionOut:
    sub = get_owned(db, Subscription, subscription_id, auth.organization_id)
    if body.catalog_item_id is not None:
        _item(db, auth, body.catalog_item_id)
    if body.vendor_party_id is not None:
        get_owned(db, Party, body.vendor_party_id, auth.organization_id)
    apply_changes(sub, body)
    db.commit()
    return subscription_out(db, sub)


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(subscription_id: int, auth: Editor, db: DbSession) -> None:
    sub = get_owned(db, Subscription, subscription_id, auth.organization_id)
    if db.scalars(select(InvoiceLine.id).where(InvoiceLine.subscription_id == sub.id)).first():
        raise conflict("This subscription has been billed; cancel it instead")
    db.delete(sub)
    db.commit()


@router.post("/billing-run")
def billing_run(body: BillingRunRequest, auth: Editor, db: DbSession) -> BillingRunResult:
    """Create draft invoices for everything due through a date. With dry_run nothing is saved."""
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    savepoint = db.begin_nested() if body.dry_run else None
    result = service.run_billing(db, org, body.through)
    infos = invoice_service.balances(db, result.invoices, today_in(org.timezone))
    invoices = []
    for invoice in result.invoices:
        party = db.get(Party, invoice.party_id)
        info = infos[invoice.id]
        invoices.append(
            InvoiceListItem(
                id=invoice.id,
                kind=invoice.kind,
                number=invoice.number,
                status=invoice.status,
                party_id=invoice.party_id,
                party_name=party.name if party else "",
                issue_date=invoice.issue_date,
                due_date=invoice.due_date,
                total=invoice.total,
                is_historical=invoice.is_historical,
                archived_at=invoice.archived_at,
                amount_paid=info.paid,
                amount_credited=info.credited,
                balance_due=info.balance_due,
                payment_status=info.status,
                is_overdue=info.overdue,
            )
        )
    if savepoint is not None:
        savepoint.rollback()
    else:
        db.commit()
    return BillingRunResult(
        dry_run=body.dry_run,
        subscriptions_billed=result.subscriptions_billed,
        lines_created=result.lines_created,
        invoices=invoices,
    )
