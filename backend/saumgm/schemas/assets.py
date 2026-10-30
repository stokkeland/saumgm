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
from typing import Any

from pydantic import BaseModel, Field

from saumgm.enums import AssetFieldType, AssetStatus
from saumgm.schemas.types import Amount

# A value of an extra field: text, a number, a date (as YYYY-MM-DD) or yes/no.
AttributeValue = str | int | float | bool | None


def _amount(**kw: Any) -> Any:
    return Field(max_digits=15, decimal_places=4, **kw)


# -- categories -----------------------------------------------------------------------------------


class AssetFieldDef(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$", description="Stored name, e.g. ram")
    label: str = Field(min_length=1, max_length=100)
    type: AssetFieldType = AssetFieldType.TEXT


class AssetCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = 0
    is_active: bool = True
    fields: list[AssetFieldDef] = Field(default=[], max_length=40)


class AssetCategoryPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    sort_order: int | None = None
    is_active: bool | None = None
    fields: list[AssetFieldDef] | None = Field(None, max_length=40)


class AssetCategoryOut(BaseModel):
    id: int
    name: str
    sort_order: int
    is_active: bool
    fields: list[AssetFieldDef]
    assets: int = Field(description="How many assets are in it")


# -- assets ---------------------------------------------------------------------------------------


class AssetFields(BaseModel):
    category_id: int | None = None
    manufacturer: str | None = Field(None, max_length=100)
    model: str | None = Field(None, max_length=100)
    serial_number: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=200)
    assigned_to: str | None = Field(None, max_length=200)
    purchase_date: date | None = None
    purchase_price: Amount | None = _amount(default=None, ge=0)
    vendor_party_id: int | None = None
    expense_id: int | None = Field(None, description="The expense that paid for it")
    warranty_expires: date | None = None
    support_ends: date | None = Field(None, description="Support or maintenance contract")
    notes: str | None = None


class AssetCreate(AssetFields):
    tag: str | None = Field(None, max_length=50, description="Empty: the next number (A-0001)")
    name: str = Field(min_length=1, max_length=200)
    status: AssetStatus = AssetStatus.IN_USE
    owner_party_id: int | None = Field(None, description="Empty: the business itself")
    attributes: dict[str, AttributeValue] = {}


class AssetPatch(AssetFields):
    tag: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=200)
    status: AssetStatus | None = None
    owner_party_id: int | None = None
    attributes: dict[str, AttributeValue] | None = None


class AssetAttachmentOut(BaseModel):
    id: int
    file_id: int
    name: str
    content_type: str | None
    size: int
    uploaded_at: datetime


class AssetOut(AssetFields):
    id: int
    tag: str
    name: str
    status: AssetStatus
    owner_party_id: int | None
    owner_name: str | None
    category_name: str | None
    vendor_name: str | None
    attributes: dict[str, AttributeValue]
    attachments: list[AssetAttachmentOut]
    created_at: datetime
    updated_at: datetime
