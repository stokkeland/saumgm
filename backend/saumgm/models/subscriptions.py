from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import SubscriptionStatus
from saumgm.models.base import Money, OrgScopedMixin, Percent, Quantity, fk, str_enum


class Subscription(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """A recurring service a client has (hosting, a domain, a support agreement)."""

    __tablename__ = "subscription"
    __table_args__ = TABLE_ARGS

    party_id: Mapped[int] = mapped_column(BigInteger, fk("party.id"), index=True)
    catalog_item_id: Mapped[int] = mapped_column(BigInteger, fk("catalog_item.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal(1))
    price_override: Mapped[Decimal | None] = mapped_column(Money)
    discount_pct: Mapped[Decimal | None] = mapped_column(Percent)
    # What the subscription is for: a domain name, hosting account, server, contract no.
    service_identifier: Mapped[str | None] = mapped_column(String(255), index=True)
    billing_interval_months: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    next_bill_date: Mapped[date | None] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        str_enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE
    )
    vendor_party_id: Mapped[int | None] = mapped_column(BigInteger, fk("party.id"), index=True)
    vendor_renewal_date: Mapped[date | None] = mapped_column(Date)
    unit_cost: Mapped[Decimal | None] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)
