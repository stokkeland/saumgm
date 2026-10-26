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

"""Payments, deposits, expenses and subscriptions."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from saumgm.enums import PaymentChannel, PaymentMethod, SubscriptionStatus
from saumgm.schemas.invoices import InvoiceListItem
from saumgm.schemas.types import Amount


def _amount(**kw: Any) -> Any:
    return Field(max_digits=15, decimal_places=4, **kw)


# -- payments -------------------------------------------------------------------------------------


class AllocationIn(BaseModel):
    invoice_id: int
    amount: Amount = _amount(gt=0)


class PaymentCreate(BaseModel):
    party_id: int
    received_date: date
    amount: Amount = _amount(gt=0)
    method: PaymentMethod | None = None
    channel: PaymentChannel | None = None
    reference: str | None = Field(None, max_length=100)
    notes: str | None = None
    allocations: list[AllocationIn] | None = Field(
        None, description="Apply to these invoices; omit to apply oldest-first automatically"
    )
    auto_allocate: bool = True


class PaymentPatch(BaseModel):
    received_date: date | None = None
    amount: Amount | None = _amount(default=None, gt=0)
    method: PaymentMethod | None = None
    channel: PaymentChannel | None = None
    reference: str | None = Field(None, max_length=100)
    notes: str | None = None
    allocations: list[AllocationIn] | None = None
    reallocate: bool = Field(False, description="Re-apply oldest-first automatically")


class AllocationOut(BaseModel):
    invoice_id: int
    invoice_number: str | None
    amount: Amount


class PaymentOut(BaseModel):
    id: int
    party_id: int
    party_name: str
    received_date: date | None
    amount: Amount
    unapplied: Amount
    method: PaymentMethod | None
    channel: PaymentChannel | None
    reference: str | None
    notes: str | None
    deposit_id: int | None
    is_historical: bool
    archived_at: datetime | None
    allocations: list[AllocationOut]


class PartyBalanceOut(BaseModel):
    receivable: Amount
    overdue: Amount
    open_invoices: int
    unapplied_credit: Amount
    net: Amount


# -- deposits -------------------------------------------------------------------------------------


class DepositItemIn(BaseModel):
    amount: Amount = _amount()
    description: str | None = Field(None, max_length=255)


class DepositCreate(BaseModel):
    deposit_date: date
    bank_party_id: int | None = None
    notes: str | None = None
    payment_ids: list[int] = []
    items: list[DepositItemIn] = []


class DepositPatch(BaseModel):
    deposit_date: date | None = None
    bank_party_id: int | None = None
    notes: str | None = None
    payment_ids: list[int] | None = None
    items: list[DepositItemIn] | None = None


class DepositItemOut(DepositItemIn):
    id: int


class DepositOut(BaseModel):
    id: int
    deposit_date: date | None
    bank_party_id: int | None
    notes: str | None
    total: Amount
    payments: list[PaymentOut]
    items: list[DepositItemOut]
    archived_at: datetime | None


# -- expenses -------------------------------------------------------------------------------------


class ExpenseLineIn(BaseModel):
    account_id: int
    amount: Amount = _amount()
    description: str | None = Field(None, max_length=255)


class ExpenseCreate(BaseModel):
    expense_date: date
    entered_date: date | None = None
    vendor_party_id: int | None = None
    for_party_id: int | None = Field(None, description="Defaults to the business itself")
    reference: str | None = Field(None, max_length=100)
    description: str | None = None
    lines: list[ExpenseLineIn] = Field(min_length=1)


class ExpensePatch(BaseModel):
    expense_date: date | None = None
    entered_date: date | None = None
    vendor_party_id: int | None = None
    for_party_id: int | None = None
    reference: str | None = Field(None, max_length=100)
    description: str | None = None
    lines: list[ExpenseLineIn] | None = Field(None, min_length=1)


class ExpenseLineOut(BaseModel):
    id: int
    account_id: int
    account_code: str
    account_name: str
    amount: Amount
    description: str | None


class ExpenseOut(BaseModel):
    id: int
    expense_date: date
    entered_date: date | None
    vendor_party_id: int | None
    vendor_name: str | None
    for_party_id: int | None
    for_name: str | None
    reference: str | None
    description: str | None
    total: Amount
    lines: list[ExpenseLineOut]
    archived_at: datetime | None
    legacy_data: dict[str, Any] | None


# -- subscriptions --------------------------------------------------------------------------------


class SubscriptionCreate(BaseModel):
    party_id: int
    catalog_item_id: int
    quantity: Amount = Field(Decimal(1), gt=0, max_digits=12, decimal_places=4)
    price_override: Amount | None = _amount(default=None, ge=0)
    discount_pct: Amount | None = Field(None, ge=0, le=100, decimal_places=4)
    service_identifier: str | None = Field(None, max_length=255)
    billing_interval_months: int | None = Field(None, ge=1, le=120)
    start_date: date
    next_bill_date: date | None = None
    end_date: date | None = None
    auto_renew: bool = True
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    vendor_party_id: int | None = None
    vendor_renewal_date: date | None = None
    unit_cost: Amount | None = _amount(default=None, ge=0)
    notes: str | None = None


class SubscriptionPatch(BaseModel):
    catalog_item_id: int | None = None
    quantity: Amount | None = Field(None, gt=0, max_digits=12, decimal_places=4)
    price_override: Amount | None = _amount(default=None, ge=0)
    discount_pct: Amount | None = Field(None, ge=0, le=100, decimal_places=4)
    service_identifier: str | None = Field(None, max_length=255)
    billing_interval_months: int | None = Field(None, ge=1, le=120)
    start_date: date | None = None
    next_bill_date: date | None = None
    end_date: date | None = None
    auto_renew: bool | None = None
    status: SubscriptionStatus | None = None
    vendor_party_id: int | None = None
    vendor_renewal_date: date | None = None
    unit_cost: Amount | None = _amount(default=None, ge=0)
    notes: str | None = None


class SubscriptionOut(BaseModel):
    id: int
    party_id: int
    party_name: str
    catalog_item_id: int
    item_name: str
    quantity: Amount
    price_override: Amount | None
    unit_price: Amount
    discount_pct: Amount | None
    service_identifier: str | None
    billing_interval_months: int
    start_date: date
    next_bill_date: date | None
    end_date: date | None
    auto_renew: bool
    status: SubscriptionStatus
    vendor_party_id: int | None
    vendor_renewal_date: date | None
    unit_cost: Amount | None
    notes: str | None


class BillingRunRequest(BaseModel):
    through: date
    dry_run: bool = False


class BillingRunResult(BaseModel):
    dry_run: bool
    subscriptions_billed: int
    lines_created: int
    invoices: list[InvoiceListItem]
