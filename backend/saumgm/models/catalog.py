from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.models.base import ZERO, LegacyMixin, Money, OrgScopedMixin, Percent, fk, str_enum
from saumgm.models.enums import BillingTiming, ItemType


class RevenueCategory(IdMixin, OrgScopedMixin, Base):
    """Groups sales for reporting (Hosting, Domains, Development, ...)."""

    __tablename__ = "revenue_category"
    __table_args__ = (UniqueConstraint("organization_id", "name"), TABLE_ARGS)

    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CatalogItem(IdMixin, OrgScopedMixin, LegacyMixin, TimestampMixin, Base):
    """A product or service that can be put on an invoice or subscribed to."""

    __tablename__ = "catalog_item"
    __table_args__ = (UniqueConstraint("organization_id", "sku"), TABLE_ARGS)

    sku: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    item_type: Mapped[ItemType] = mapped_column(str_enum(ItemType))
    unit: Mapped[str | None] = mapped_column(String(20))
    price: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    default_discount_pct: Mapped[Decimal] = mapped_column(Percent, default=ZERO)
    tax_category_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("tax_category.id"), index=True
    )
    revenue_category_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("revenue_category.id"), index=True
    )
    # Subscription defaults
    billing_interval_months: Mapped[int | None] = mapped_column(Integer)
    billing_timing: Mapped[BillingTiming | None] = mapped_column(str_enum(BillingTiming))
    # Cost side, for resold items (domains, hosting, certificates, hardware)
    default_vendor_id: Mapped[int | None] = mapped_column(BigInteger, fk("party.id"), index=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Money)
    cogs_account_id: Mapped[int | None] = mapped_column(BigInteger, fk("account.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
