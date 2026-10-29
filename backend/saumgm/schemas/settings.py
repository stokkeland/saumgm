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

from pydantic import BaseModel, ConfigDict, Field

from saumgm.enums import (
    AddressType,
    FilingFrequency,
    JurisdictionLevel,
    TaxBasis,
    UserRoleType,
)
from saumgm.schemas.types import Amount, RateValue

ORM = ConfigDict(from_attributes=True)


class OrganizationOut(BaseModel):
    model_config = ORM

    id: int
    legal_name: str
    display_name: str
    payable_to: str | None
    tagline: str | None
    footer_text: str | None
    phone: str | None
    email: str | None
    website: str | None
    tax_id: str | None
    self_party_id: int | None
    logo_file_id: int | None
    country_code: str
    currency_code: str
    locale: str
    timezone: str
    date_format: str | None
    fiscal_year_start_month: int
    tax_label: str
    prices_include_tax: bool
    tax_basis: TaxBasis
    income_basis: TaxBasis
    default_terms_days: int
    invoice_revision_owner_only: bool


class OrganizationPatch(BaseModel):
    legal_name: str | None = Field(None, min_length=1, max_length=200)
    display_name: str | None = Field(None, min_length=1, max_length=200)
    payable_to: str | None = Field(None, max_length=200)
    tagline: str | None = Field(None, max_length=255)
    footer_text: str | None = None
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    website: str | None = Field(None, max_length=255)
    tax_id: str | None = Field(None, max_length=50)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    currency_code: str | None = Field(None, min_length=3, max_length=3)
    locale: str | None = Field(None, min_length=2, max_length=20)
    timezone: str | None = Field(None, min_length=1, max_length=50)
    date_format: str | None = Field(None, max_length=20)
    fiscal_year_start_month: int | None = Field(None, ge=1, le=12)
    tax_label: str | None = Field(None, min_length=1, max_length=50)
    prices_include_tax: bool | None = None
    tax_basis: TaxBasis | None = None
    income_basis: TaxBasis | None = None
    default_terms_days: int | None = Field(None, ge=0, le=3650)
    invoice_revision_owner_only: bool | None = None


class OrgAddressIn(BaseModel):
    address_type: AddressType
    line1: str | None = Field(None, max_length=200)
    line2: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    phone: str | None = Field(None, max_length=50)
    effective_from: date | None = None
    effective_to: date | None = None


class OrgAddressPatch(BaseModel):
    address_type: AddressType | None = None
    line1: str | None = Field(None, max_length=200)
    line2: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    phone: str | None = Field(None, max_length=50)
    effective_from: date | None = None
    effective_to: date | None = None


class OrgAddressOut(OrgAddressIn):
    model_config = ORM
    id: int


class SequenceOut(BaseModel):
    model_config = ORM
    name: str
    next_value: int
    prefix: str
    pad_width: int


class SequencePatch(BaseModel):
    next_value: int | None = Field(None, ge=1)
    prefix: str | None = Field(None, max_length=20)
    pad_width: int | None = Field(None, ge=0, le=12)


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=200)
    role: UserRoleType
    password: str = Field(min_length=1, max_length=1024)


class UserPatch(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=200)
    is_active: bool | None = None
    role: UserRoleType | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=1, max_length=1024)


class UserListItem(BaseModel):
    id: int
    email: str
    display_name: str
    is_active: bool
    role: UserRoleType
    last_login_at: datetime | None


# -- tax setup ------------------------------------------------------------------------------------


class JurisdictionIn(BaseModel):
    parent_id: int
    level: JurisdictionLevel
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    reporting_code: str | None = Field(None, max_length=20)
    is_active: bool = True


class JurisdictionPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    reporting_code: str | None = Field(None, max_length=20)
    is_active: bool | None = None


class JurisdictionOut(BaseModel):
    model_config = ORM
    id: int
    parent_id: int | None
    level: JurisdictionLevel
    code: str
    name: str
    reporting_code: str | None
    is_active: bool


class TaxRateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rate: RateValue = Field(ge=0, lt=1, max_digits=9, decimal_places=6, description="0.04 = 4%")
    effective_from: date
    effective_to: date | None = None


class TaxRatePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    rate: RateValue | None = Field(None, ge=0, lt=1, max_digits=9, decimal_places=6)
    effective_from: date | None = None
    effective_to: date | None = None


class TaxRateOut(TaxRateIn):
    model_config = ORM
    id: int
    jurisdiction_id: int


class RegistrationIn(BaseModel):
    jurisdiction_id: int
    registration_number: str | None = Field(None, max_length=100)
    filing_frequency: FilingFrequency | None = None
    period_start_month: int = Field(
        1, ge=1, le=12, description="First month of the filing year (New York: 3)"
    )
    effective_from: date
    effective_to: date | None = None


class RegistrationPatch(BaseModel):
    registration_number: str | None = Field(None, max_length=100)
    filing_frequency: FilingFrequency | None = None
    period_start_month: int | None = Field(None, ge=1, le=12)
    effective_from: date | None = None
    effective_to: date | None = None


class RegistrationOut(RegistrationIn):
    model_config = ORM
    id: int


class FilingIn(BaseModel):
    registration_id: int
    period_start: date
    filed_on: date
    amount_paid: Amount | None = Field(None, ge=0, max_digits=15, decimal_places=4)
    reference: str | None = Field(None, max_length=100)
    notes: str | None = None


class FilingOut(FilingIn):
    model_config = ORM
    id: int
    period_end: date


class TaxPeriod(BaseModel):
    registration_id: int
    period_start: date
    period_end: date
    filing: FilingOut | None


class TaxabilityRuleIn(BaseModel):
    jurisdiction_id: int
    tax_category_id: int
    is_taxable: bool


class TaxabilityRuleOut(TaxabilityRuleIn):
    model_config = ORM
    id: int
