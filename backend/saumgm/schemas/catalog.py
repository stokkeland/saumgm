from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from saumgm.enums import AccountType, BillingTiming, ItemType

ORM = ConfigDict(from_attributes=True)


class CatalogItemFields(BaseModel):
    sku: str | None = Field(None, max_length=50)
    description: str | None = None
    unit: str | None = Field(None, max_length=20)
    price: Decimal = Field(Decimal(0), ge=0, max_digits=15, decimal_places=4)
    default_discount_pct: Decimal = Field(Decimal(0), ge=0, le=100, decimal_places=4)
    tax_category_id: int | None = None
    revenue_category_id: int | None = None
    billing_interval_months: int | None = Field(None, ge=1, le=120)
    billing_timing: BillingTiming | None = None
    default_vendor_id: int | None = None
    unit_cost: Decimal | None = Field(None, ge=0, max_digits=15, decimal_places=4)
    cogs_account_id: int | None = None
    is_active: bool = True


class CatalogItemCreate(CatalogItemFields):
    name: str = Field(min_length=1, max_length=200)
    item_type: ItemType

    @model_validator(mode="after")
    def subscriptions_need_an_interval(self) -> "CatalogItemCreate":
        if self.item_type == ItemType.SUBSCRIPTION and not self.billing_interval_months:
            raise ValueError("Subscription items need billing_interval_months")
        return self


class CatalogItemPatch(BaseModel):
    sku: str | None = Field(None, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    item_type: ItemType | None = None
    unit: str | None = Field(None, max_length=20)
    price: Decimal | None = Field(None, ge=0, max_digits=15, decimal_places=4)
    default_discount_pct: Decimal | None = Field(None, ge=0, le=100, decimal_places=4)
    tax_category_id: int | None = None
    revenue_category_id: int | None = None
    billing_interval_months: int | None = Field(None, ge=1, le=120)
    billing_timing: BillingTiming | None = None
    default_vendor_id: int | None = None
    unit_cost: Decimal | None = Field(None, ge=0, max_digits=15, decimal_places=4)
    cogs_account_id: int | None = None
    is_active: bool | None = None


class CatalogItemOut(CatalogItemFields):
    model_config = ORM
    id: int
    name: str
    item_type: ItemType
    legacy_data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class RevenueCategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True


class RevenueCategoryPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None


class RevenueCategoryOut(RevenueCategoryIn):
    model_config = ORM
    id: int


class TaxCategoryIn(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    is_active: bool = True


class TaxCategoryPatch(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    is_active: bool | None = None


class TaxCategoryOut(TaxCategoryIn):
    model_config = ORM
    id: int


class AccountIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    account_type: AccountType = AccountType.EXPENSE
    is_active: bool = True


class AccountPatch(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=20)
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    account_type: AccountType | None = None
    is_active: bool | None = None


class AccountOut(AccountIn):
    model_config = ORM
    id: int
