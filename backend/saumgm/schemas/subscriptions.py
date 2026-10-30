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

"""Client subscriptions, vendor subscriptions, catalog packages and the billing run."""

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from saumgm.enums import SubscriptionStatus
from saumgm.schemas.invoices import InvoiceListItem
from saumgm.schemas.types import Amount


def _amount(**kw: Any) -> Any:
    return Field(max_digits=15, decimal_places=4, **kw)


def _quantity(**kw: Any) -> Any:
    return Field(gt=0, max_digits=12, decimal_places=4, **kw)


def _percent(**kw: Any) -> Any:
    return Field(ge=0, le=100, decimal_places=4, **kw)


# -- client subscriptions -------------------------------------------------------------------------


class SubscriptionLineIn(BaseModel):
    catalog_item_id: int
    description: str | None = Field(None, max_length=500, description="Empty: the item's name")
    quantity: Amount = _quantity(default=Decimal(1))
    price_override: Amount | None = _amount(default=None, ge=0)
    discount_pct: Amount | None = _percent(default=None)
    uses: list[int] = Field(
        default_factory=list, description="Vendor subscriptions this line depends on"
    )


class VendorUse(BaseModel):
    """A vendor subscription a client subscription line uses, with its share of the cost."""

    vendor_subscription_id: int
    name: str
    vendor_name: str
    status: SubscriptionStatus
    monthly_amount: Amount
    shared_by: int = Field(description="Client subscription lines that use it")
    monthly_share: Amount


class SubscriptionLineOut(BaseModel):
    id: int
    catalog_item_id: int
    item_name: str
    sku: str | None
    description: str
    quantity: Amount
    price_override: Amount | None
    unit_price: Amount
    discount_pct: Amount | None
    total: Amount = Field(description="Per billing period")
    uses: list[VendorUse]


class SubscriptionCreate(BaseModel):
    party_id: int
    service_identifier: str | None = Field(None, max_length=255)
    billing_interval_months: int | None = Field(
        None, ge=1, le=120, description="Empty: the first line's catalog interval"
    )
    start_date: date
    next_bill_date: date | None = None
    end_date: date | None = None
    auto_renew: bool = True
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    notes: str | None = None
    lines: list[SubscriptionLineIn] = Field(min_length=1)


class SubscriptionPatch(BaseModel):
    service_identifier: str | None = Field(None, max_length=255)
    billing_interval_months: int | None = Field(None, ge=1, le=120)
    start_date: date | None = None
    next_bill_date: date | None = None
    end_date: date | None = None
    auto_renew: bool | None = None
    status: SubscriptionStatus | None = None
    notes: str | None = None
    lines: list[SubscriptionLineIn] | None = Field(None, min_length=1)


class SubscriptionOut(BaseModel):
    id: int
    party_id: int
    party_name: str
    service_identifier: str | None
    summary: str = Field(description="The lines' descriptions, for lists")
    billing_interval_months: int
    start_date: date
    next_bill_date: date | None
    end_date: date | None
    auto_renew: bool
    status: SubscriptionStatus
    notes: str | None
    lines: list[SubscriptionLineOut]
    total: Amount = Field(description="Per billing period, before tax")
    monthly_revenue: Amount
    monthly_cost: Amount = Field(description="Share of the vendor subscriptions the lines use")
    billed: bool = Field(description="Has invoice lines (cannot be deleted)")


class BillingRunRequest(BaseModel):
    through: date
    dry_run: bool = False
    combine: bool = Field(
        False, description="One invoice per client for subscriptions due on the same day"
    )


class BillingRunInvoice(InvoiceListItem):
    lines: list[str] = Field(description="The draft's line descriptions")


class BillingRunResult(BaseModel):
    dry_run: bool
    subscriptions_billed: int
    lines_created: int
    invoices: list[BillingRunInvoice]


# -- vendor subscriptions -------------------------------------------------------------------------


class VendorSubscriptionFields(BaseModel):
    service_identifier: str | None = Field(None, max_length=255)
    next_due_date: date | None = None
    end_date: date | None = None
    expense_account_id: int | None = None
    autopay: bool = False
    auto_renew: bool = True
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    notes: str | None = None


class VendorSubscriptionCreate(VendorSubscriptionFields):
    party_id: int
    name: str = Field(min_length=1, max_length=200)
    amount: Amount = _amount(ge=0)
    interval_months: int = Field(ge=1, le=120)


class VendorSubscriptionPatch(BaseModel):
    party_id: int | None = None
    name: str | None = Field(None, min_length=1, max_length=200)
    service_identifier: str | None = Field(None, max_length=255)
    amount: Amount | None = _amount(default=None, ge=0)
    interval_months: int | None = Field(None, ge=1, le=120)
    next_due_date: date | None = None
    end_date: date | None = None
    expense_account_id: int | None = None
    autopay: bool | None = None
    auto_renew: bool | None = None
    status: SubscriptionStatus | None = None
    notes: str | None = None


class UsedBy(BaseModel):
    """A client subscription that depends on a vendor subscription."""

    subscription_id: int
    party_id: int
    party_name: str
    service_identifier: str | None
    description: str
    status: SubscriptionStatus


class VendorSubscriptionOut(VendorSubscriptionFields):
    id: int
    party_id: int
    vendor_name: str
    name: str
    amount: Amount
    interval_months: int
    monthly_amount: Amount
    expense_account_code: str | None
    expense_account_name: str | None
    last_paid_date: date | None
    payments: int
    used_by: list[UsedBy]


class VendorPaymentIn(BaseModel):
    """Record a payment: makes an expense and moves the next due date on by one interval."""

    paid_date: date
    amount: Amount | None = _amount(default=None, gt=0, description="Empty: the usual amount")
    expense_account_id: int | None = Field(None, description="Empty: the subscription's account")
    reference: str | None = Field(None, max_length=100)
    description: str | None = None


class VendorPaymentOut(BaseModel):
    expense_id: int
    subscription: VendorSubscriptionOut


# -- catalog packages -----------------------------------------------------------------------------


class PackageItemIn(BaseModel):
    catalog_item_id: int
    quantity: Amount = _quantity(default=Decimal(1))
    price: Amount | None = _amount(default=None, ge=0, description="Empty: the catalog price")
    discount_pct: Amount | None = _percent(default=None)


class PackageItemOut(PackageItemIn):
    item_name: str
    unit_price: Amount
    billing_interval_months: int | None


class PackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    is_active: bool = True
    items: list[PackageItemIn] = Field(min_length=1)


class PackagePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None
    items: list[PackageItemIn] | None = Field(None, min_length=1)


class PackageOut(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    items: list[PackageItemOut]
    total: Amount
