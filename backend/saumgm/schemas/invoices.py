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

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from saumgm.enums import InvoiceKind, InvoiceStatus, PaymentChannel, PaymentMethod, PaymentStatus
from saumgm.schemas.types import Amount, RateValue

ORM = ConfigDict(from_attributes=True)


def _money(**kw: Any) -> Any:
    return Field(max_digits=15, decimal_places=4, **kw)


class LineIn(BaseModel):
    """An invoice line. With a catalog item, missing fields come from the item."""

    catalog_item_id: int | None = None
    subscription_id: int | None = None
    sku: str | None = Field(None, max_length=50)
    description: str | None = Field(None, max_length=500)
    quantity: Amount = Field(Decimal(1), max_digits=12, decimal_places=4)
    unit: str | None = Field(None, max_length=20)
    unit_price: Amount | None = _money(default=None)
    unit_discount: Amount | None = _money(default=None, ge=0)
    discount_pct: Amount | None = Field(None, ge=0, le=100, decimal_places=4)
    tax_category_id: int | None = None
    revenue_category_id: int | None = None


class HeaderFields(BaseModel):
    issue_date: date | None = None
    terms_days: int | None = Field(None, ge=0, le=3650)
    terms_text: str | None = Field(None, max_length=100)
    tax_jurisdiction_id: int | None = None
    bill_to_company: str | None = Field(None, max_length=200)
    bill_to_name: str | None = Field(None, max_length=200)
    bill_to_line1: str | None = Field(None, max_length=200)
    bill_to_line2: str | None = Field(None, max_length=200)
    bill_to_city: str | None = Field(None, max_length=100)
    bill_to_region: str | None = Field(None, max_length=100)
    bill_to_postal_code: str | None = Field(None, max_length=20)
    bill_to_country: str | None = Field(None, max_length=100)
    bill_to_phone: str | None = Field(None, max_length=50)
    bill_to_email: str | None = Field(None, max_length=255)
    freight: Amount | None = _money(default=None, ge=0)
    adjustment: Amount | None = _money(default=None)
    adjustment_note: str | None = Field(None, max_length=200)
    notes: str | None = None


class InvoiceCreate(HeaderFields):
    party_id: int
    lines: list[LineIn] = []


class InvoicePatch(HeaderFields):
    party_id: int | None = None
    lines: list[LineIn] | None = None


class InvoiceRevise(HeaderFields):
    reason: str = Field(min_length=3, max_length=2000)
    lines: list[LineIn] | None = None


class IssueRequest(BaseModel):
    issue_date: date | None = None


class VoidRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class WriteOffRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    write_off_date: date | None = Field(None, description="Defaults to today")


class BulkWriteOffRequest(WriteOffRequest):
    invoice_ids: list[int] = Field(min_length=1, max_length=500)


class WrittenOff(BaseModel):
    invoice_id: int
    number: str | None
    amount: Amount


class Skipped(BaseModel):
    invoice_id: int
    number: str | None
    reason: str


class BulkWriteOffResult(BaseModel):
    written_off: list[WrittenOff]
    skipped: list[Skipped]


class UndoWriteOffRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class CreditNoteCreate(BaseModel):
    lines: list[LineIn] = Field(min_length=1)
    notes: str | None = None


class CalculateRequest(BaseModel):
    party_id: int
    tax_jurisdiction_id: int | None = None
    issue_date: date | None = None
    freight: Amount = _money(default=Decimal(0), ge=0)
    adjustment: Amount = _money(default=Decimal(0))
    lines: list[LineIn]


class LineOut(BaseModel):
    model_config = ORM
    id: int | None = None
    sort_order: int
    catalog_item_id: int | None
    subscription_id: int | None
    sku: str | None = None
    description: str
    quantity: Amount
    unit: str | None
    unit_price: Amount
    unit_discount: Amount
    line_total: Amount
    tax_category_id: int | None
    revenue_category_id: int | None
    legacy_unit_tax: Amount | None = None


class TaxOut(BaseModel):
    model_config = ORM
    jurisdiction_id: int | None
    name: str
    rate: RateValue | None
    taxable_base: Amount
    amount: Amount


class CalculateResult(BaseModel):
    lines: list[LineOut]
    subtotal: Amount
    taxes: list[TaxOut]
    tax_total: Amount
    total: Amount


class RevisionSummary(BaseModel):
    model_config = ORM
    revision_no: int
    reason: str
    changed_by_user_id: int | None
    changed_at: datetime
    pdf_file_id: int | None  # the document as it was sent before this revision


class RevisionOut(RevisionSummary):
    snapshot: dict[str, Any]


class InvoicePayment(BaseModel):
    payment_id: int
    amount: Amount
    received_date: date | None
    method: PaymentMethod | None
    channel: PaymentChannel | None
    reference: str | None


class Balance(BaseModel):
    amount_paid: Amount
    amount_credited: Amount
    balance_due: Amount
    payment_status: PaymentStatus
    is_overdue: bool


class InvoiceListItem(Balance):
    id: int
    kind: InvoiceKind
    number: str | None
    status: InvoiceStatus
    party_id: int
    party_name: str
    issue_date: date | None
    due_date: date | None
    total: Amount
    is_historical: bool
    archived_at: datetime | None


class InvoiceOut(InvoiceListItem):
    credited_invoice_id: int | None
    terms_days: int | None
    terms_text: str | None
    bill_to_company: str | None
    bill_to_name: str | None
    bill_to_line1: str | None
    bill_to_line2: str | None
    bill_to_city: str | None
    bill_to_region: str | None
    bill_to_postal_code: str | None
    bill_to_country: str | None
    bill_to_phone: str | None
    bill_to_email: str | None
    tax_jurisdiction_id: int | None
    tax_location_text: str | None
    freight: Amount
    adjustment: Amount
    adjustment_note: str | None
    notes: str | None
    subtotal: Amount
    tax_total: Amount
    revision_no: int
    issued_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    write_off_date: date | None
    write_off_amount: Amount | None
    write_off_reason: str | None
    lines: list[LineOut]
    taxes: list[TaxOut]
    payments: list[InvoicePayment]
    credit_note_ids: list[int]
    revisions: list[RevisionSummary]
    legacy_data: dict[str, Any] | None
    warnings: list[str] = []
