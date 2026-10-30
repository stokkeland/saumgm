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
from typing import Any, Literal

from pydantic import BaseModel, Field

from saumgm.enums import BankAccountKind, BankEntryKind, BankEntryStatus
from saumgm.schemas.types import Amount


def _amount(**kw: Any) -> Any:
    return Field(max_digits=15, decimal_places=4, **kw)


LAST4 = r"^[0-9A-Za-z]{1,4}$"

# -- accounts -------------------------------------------------------------------------------------


class BankAccountCreate(BaseModel):
    party_id: int | None = Field(None, description="The bank (a contact)")
    name: str = Field(min_length=1, max_length=100)
    kind: BankAccountKind
    number_last4: str | None = Field(None, pattern=LAST4)
    opening_date: date = Field(description="The register starts here; no lines before it")
    opening_balance: Amount = _amount(default=0, description="Negative on a card: owed")
    is_active: bool = True
    notes: str | None = None


class BankAccountPatch(BaseModel):
    party_id: int | None = None
    name: str | None = Field(None, min_length=1, max_length=100)
    kind: BankAccountKind | None = None
    number_last4: str | None = Field(None, pattern=LAST4)
    opening_date: date | None = None
    opening_balance: Amount | None = _amount(default=None)
    is_active: bool | None = None
    notes: str | None = None


class BankAccountOut(BaseModel):
    id: int
    party_id: int | None
    bank_name: str | None
    name: str
    kind: BankAccountKind
    number_last4: str | None
    opening_date: date
    opening_balance: Amount
    is_active: bool
    notes: str | None
    balance: Amount
    cleared_balance: Amount
    reconciled_balance: Amount
    uncleared_count: int
    last_reconciled_date: date | None
    last_statement_balance: Amount | None


# -- register -------------------------------------------------------------------------------------


class BankEntryCreate(BaseModel):
    entry_date: date
    amount: Amount = _amount(description="Positive: money in; negative: money out (or a charge)")
    payee: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=500)
    reference: str | None = Field(None, max_length=100)
    account_id: int | None = Field(None, description="Category: an account from the chart")
    status: Literal[BankEntryStatus.UNCLEARED, BankEntryStatus.CLEARED] = BankEntryStatus.UNCLEARED
    kind: Literal[BankEntryKind.MANUAL, BankEntryKind.ADJUSTMENT] = BankEntryKind.MANUAL


class BankEntryPatch(BaseModel):
    entry_date: date | None = None
    amount: Amount | None = _amount(default=None)
    payee: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=500)
    reference: str | None = Field(None, max_length=100)
    account_id: int | None = None
    status: Literal[BankEntryStatus.UNCLEARED, BankEntryStatus.CLEARED] | None = None


class BankEntryOut(BaseModel):
    id: int
    bank_account_id: int
    entry_date: date
    amount: Amount
    payee: str | None
    description: str | None
    reference: str | None
    account_id: int | None
    account_name: str | None
    status: BankEntryStatus
    kind: BankEntryKind
    deposit_id: int | None
    expense_id: int | None
    transfer_entry_id: int | None
    # The account on the other side of a transfer.
    transfer_account_id: int | None
    transfer_account_name: str | None
    reconciliation_id: int | None
    running_balance: Amount


class TransferIn(BaseModel):
    from_account_id: int
    to_account_id: int
    entry_date: date
    amount: Amount = _amount(gt=0)
    description: str | None = Field(None, max_length=500)
    reference: str | None = Field(None, max_length=100)


class TransferOut(BaseModel):
    out: BankEntryOut
    into: BankEntryOut


class ToExpenseIn(BaseModel):
    account_id: int | None = Field(None, description="Empty: the line's category")
    vendor_party_id: int | None = None


# -- reconciling ----------------------------------------------------------------------------------


class ReconcileIn(BaseModel):
    statement_date: date
    statement_balance: Amount = _amount(description="The ending balance on the statement")
    entry_ids: list[int] = Field(description="The lines that appear on the statement")


class ReconciliationOut(BaseModel):
    id: int
    bank_account_id: int
    statement_date: date
    statement_balance: Amount
    created_at: datetime
    created_by: str | None
    entries: int
