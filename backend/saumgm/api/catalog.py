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

"""Catalog (products and services), revenue categories, tax categories and accounts."""

from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import exists, or_, select
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
from saumgm.api.deps import DbSession, Editor, Owner, Reader
from saumgm.enums import ItemType
from saumgm.models import (
    Account,
    CatalogItem,
    ExpenseLine,
    InvoiceLine,
    Party,
    RevenueCategory,
    Subscription,
    TaxCategory,
)
from saumgm.schemas.catalog import (
    AccountIn,
    AccountOut,
    AccountPatch,
    CatalogItemCreate,
    CatalogItemOut,
    CatalogItemPatch,
    RevenueCategoryIn,
    RevenueCategoryOut,
    RevenueCategoryPatch,
    TaxCategoryIn,
    TaxCategoryOut,
    TaxCategoryPatch,
)

router = APIRouter(tags=["catalog"])

REFS: dict[str, Any] = {
    "tax_category_id": TaxCategory,
    "revenue_category_id": RevenueCategory,
    "default_vendor_id": Party,
    "cogs_account_id": Account,
}


def _check_refs(db: Session, org_id: int, body: CatalogItemCreate | CatalogItemPatch) -> None:
    for key, model in REFS.items():
        value = getattr(body, key)
        if value is not None:
            get_owned(db, model, value, org_id)


# -- catalog items --------------------------------------------------------------------------------


@router.get("/catalog")
def list_items(
    auth: Reader,
    db: DbSession,
    q: str | None = Query(None, description="Search name, SKU or description"),
    item_type: ItemType | None = None,
    active: bool | None = None,
    revenue_category_id: int | None = None,
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[CatalogItemOut]:
    stmt = (
        select(CatalogItem)
        .where(CatalogItem.organization_id == auth.organization_id)
        .order_by(CatalogItem.name)
    )
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                CatalogItem.name.ilike(pattern),
                CatalogItem.sku.ilike(pattern),
                CatalogItem.description.ilike(pattern),
            )
        )
    if item_type:
        stmt = stmt.where(CatalogItem.item_type == item_type)
    if active is not None:
        stmt = stmt.where(CatalogItem.is_active == active)
    if revenue_category_id is not None:
        stmt = stmt.where(CatalogItem.revenue_category_id == revenue_category_id)
    items, total = paginate(db, stmt, limit, offset)
    return Page(
        items=[CatalogItemOut.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/catalog", status_code=status.HTTP_201_CREATED)
def create_item(body: CatalogItemCreate, auth: Editor, db: DbSession) -> CatalogItemOut:
    _check_refs(db, auth.organization_id, body)
    item = CatalogItem(organization_id=auth.organization_id, **body.model_dump())
    db.add(item)
    db.flush()
    db.commit()
    return CatalogItemOut.model_validate(item)


@router.get("/catalog/{item_id}")
def get_item(item_id: int, auth: Reader, db: DbSession) -> CatalogItemOut:
    return CatalogItemOut.model_validate(get_owned(db, CatalogItem, item_id, auth.organization_id))


@router.patch("/catalog/{item_id}")
def update_item(
    item_id: int, body: CatalogItemPatch, auth: Editor, db: DbSession
) -> CatalogItemOut:
    item = get_owned(db, CatalogItem, item_id, auth.organization_id)
    _check_refs(db, auth.organization_id, body)
    apply_changes(item, body)
    if item.item_type == ItemType.SUBSCRIPTION and not item.billing_interval_months:
        raise conflict("Subscription items need billing_interval_months")
    db.commit()
    return CatalogItemOut.model_validate(item)


@router.delete("/catalog/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, auth: Editor, db: DbSession) -> None:
    item = get_owned(db, CatalogItem, item_id, auth.organization_id)
    used = db.scalar(
        select(
            exists().where(InvoiceLine.catalog_item_id == item.id)
            | exists().where(Subscription.catalog_item_id == item.id)
        )
    )
    if used:
        raise conflict("This item is used on invoices or subscriptions; mark it inactive instead.")
    db.delete(item)
    db.commit()


# -- revenue categories ---------------------------------------------------------------------------


@router.get("/revenue-categories")
def list_revenue_categories(auth: Reader, db: DbSession) -> list[RevenueCategoryOut]:
    rows = db.scalars(
        select(RevenueCategory)
        .where(RevenueCategory.organization_id == auth.organization_id)
        .order_by(RevenueCategory.name)
    )
    return [RevenueCategoryOut.model_validate(r) for r in rows]


@router.post("/revenue-categories", status_code=status.HTTP_201_CREATED)
def create_revenue_category(
    body: RevenueCategoryIn, auth: Editor, db: DbSession
) -> RevenueCategoryOut:
    category = RevenueCategory(organization_id=auth.organization_id, **body.model_dump())
    db.add(category)
    db.flush()
    db.commit()
    return RevenueCategoryOut.model_validate(category)


@router.patch("/revenue-categories/{category_id}")
def update_revenue_category(
    category_id: int, body: RevenueCategoryPatch, auth: Editor, db: DbSession
) -> RevenueCategoryOut:
    category = get_owned(db, RevenueCategory, category_id, auth.organization_id)
    apply_changes(category, body)
    db.commit()
    return RevenueCategoryOut.model_validate(category)


# -- tax categories -------------------------------------------------------------------------------


@router.get("/tax/categories")
def list_tax_categories(auth: Reader, db: DbSession) -> list[TaxCategoryOut]:
    rows = db.scalars(
        select(TaxCategory)
        .where(TaxCategory.organization_id == auth.organization_id)
        .order_by(TaxCategory.name)
    )
    return [TaxCategoryOut.model_validate(r) for r in rows]


@router.post("/tax/categories", status_code=status.HTTP_201_CREATED)
def create_tax_category(body: TaxCategoryIn, auth: Owner, db: DbSession) -> TaxCategoryOut:
    category = TaxCategory(organization_id=auth.organization_id, **body.model_dump())
    db.add(category)
    db.flush()
    db.commit()
    return TaxCategoryOut.model_validate(category)


@router.patch("/tax/categories/{category_id}")
def update_tax_category(
    category_id: int, body: TaxCategoryPatch, auth: Owner, db: DbSession
) -> TaxCategoryOut:
    category = get_owned(db, TaxCategory, category_id, auth.organization_id)
    apply_changes(category, body)
    db.commit()
    return TaxCategoryOut.model_validate(category)


# -- accounts -------------------------------------------------------------------------------------


@router.get("/accounts")
def list_accounts(auth: Reader, db: DbSession, active: bool | None = None) -> list[AccountOut]:
    stmt = select(Account).where(Account.organization_id == auth.organization_id)
    if active is not None:
        stmt = stmt.where(Account.is_active == active)
    return [AccountOut.model_validate(a) for a in db.scalars(stmt.order_by(Account.code))]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(body: AccountIn, auth: Owner, db: DbSession) -> AccountOut:
    account = Account(organization_id=auth.organization_id, **body.model_dump())
    db.add(account)
    db.flush()
    db.commit()
    return AccountOut.model_validate(account)


@router.patch("/accounts/{account_id}")
def update_account(account_id: int, body: AccountPatch, auth: Owner, db: DbSession) -> AccountOut:
    account = get_owned(db, Account, account_id, auth.organization_id)
    apply_changes(account, body)
    db.commit()
    return AccountOut.model_validate(account)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, auth: Owner, db: DbSession) -> None:
    account = get_owned(db, Account, account_id, auth.organization_id)
    if db.scalar(select(exists().where(ExpenseLine.account_id == account.id))):
        raise conflict("This account has expenses; mark it inactive instead.")
    db.delete(account)
    db.commit()
