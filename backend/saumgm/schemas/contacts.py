from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from saumgm.enums import AddressType, PartyKind, PartyRoleType

ORM = ConfigDict(from_attributes=True)


class AddressIn(BaseModel):
    address_type: AddressType = AddressType.BILLING
    is_default: bool = False
    line1: str | None = Field(None, max_length=200)
    line2: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    tax_jurisdiction_id: int | None = None


class AddressPatch(BaseModel):
    address_type: AddressType | None = None
    is_default: bool | None = None
    line1: str | None = Field(None, max_length=200)
    line2: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    tax_jurisdiction_id: int | None = None


class AddressOut(AddressIn):
    model_config = ORM
    id: int


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    title: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=50)
    mobile: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    is_primary: bool = False
    notes: str | None = None


class PersonPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    title: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=50)
    mobile: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    is_primary: bool | None = None
    notes: str | None = None


class PersonOut(PersonIn):
    model_config = ORM
    id: int


class ExemptionIn(BaseModel):
    """A tax exemption; jurisdiction_id None means it applies everywhere."""

    jurisdiction_id: int | None = None
    certificate_type: str = Field(min_length=1, max_length=50)
    certificate_number: str | None = Field(None, max_length=100)
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None


class ExemptionPatch(BaseModel):
    jurisdiction_id: int | None = None
    certificate_type: str | None = Field(None, min_length=1, max_length=50)
    certificate_number: str | None = Field(None, max_length=100)
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None


class ExemptionOut(ExemptionIn):
    model_config = ORM
    id: int
    file_id: int | None


class PartyFields(BaseModel):
    short_code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    kind: PartyKind = PartyKind.COMPANY
    phone: str | None = Field(None, max_length=50)
    fax: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    website: str | None = Field(None, max_length=255)
    tax_id: str | None = Field(None, max_length=50)
    notes: str | None = None
    default_terms_days: int | None = Field(None, ge=0, le=3650)
    vendor_account_no: str | None = Field(None, max_length=100)
    default_expense_account_id: int | None = None


class PartyCreate(PartyFields):
    roles: list[PartyRoleType] = Field(min_length=1)
    addresses: list[AddressIn] = []
    people: list[PersonIn] = []


class PartyPatch(BaseModel):
    short_code: str | None = Field(None, min_length=1, max_length=30)
    name: str | None = Field(None, min_length=1, max_length=200)
    kind: PartyKind | None = None
    is_active: bool | None = None
    phone: str | None = Field(None, max_length=50)
    fax: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    website: str | None = Field(None, max_length=255)
    tax_id: str | None = Field(None, max_length=50)
    notes: str | None = None
    default_terms_days: int | None = Field(None, ge=0, le=3650)
    vendor_account_no: str | None = Field(None, max_length=100)
    default_expense_account_id: int | None = None
    roles: list[PartyRoleType] | None = Field(None, min_length=1)


class PartySummary(BaseModel):
    id: int
    party_no: str
    short_code: str
    name: str
    kind: PartyKind
    roles: list[PartyRoleType]
    is_active: bool
    archived_at: datetime | None
    email: str | None
    phone: str | None
    city: str | None
    region: str | None
    country_code: str | None


class PartyDetail(PartySummary):
    fax: str | None
    website: str | None
    tax_id: str | None
    notes: str | None
    default_terms_days: int | None
    vendor_account_no: str | None
    default_expense_account_id: int | None
    addresses: list[AddressOut]
    people: list[PersonOut]
    tax_exemptions: list[ExemptionOut]
    legacy_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
