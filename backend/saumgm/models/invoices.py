from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.models.base import (
    ZERO,
    LegacyMixin,
    Money,
    OrgScopedMixin,
    Quantity,
    Rate,
    fk,
    str_enum,
)
from saumgm.models.enums import InvoiceKind, InvoiceStatus


class Invoice(IdMixin, OrgScopedMixin, LegacyMixin, TimestampMixin, Base):
    """An invoice or credit note. Paid / partially paid / overdue are computed from payment
    allocations and the due date, not stored."""

    __tablename__ = "invoice"
    __table_args__ = (UniqueConstraint("organization_id", "kind", "number"), TABLE_ARGS)

    kind: Mapped[InvoiceKind] = mapped_column(str_enum(InvoiceKind), default=InvoiceKind.INVOICE)
    # Assigned when issued; drafts have none.
    number: Mapped[str | None] = mapped_column(String(30))
    party_id: Mapped[int] = mapped_column(BigInteger, fk("party.id"), index=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        str_enum(InvoiceStatus), default=InvoiceStatus.DRAFT, index=True
    )
    credited_invoice_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("invoice.id"), index=True
    )

    issue_date: Mapped[date | None] = mapped_column(Date, index=True)
    terms_days: Mapped[int | None] = mapped_column(Integer)
    # Terms as printed, e.g. "Net 30 days" or "50/50 start/completion".
    terms_text: Mapped[str | None] = mapped_column(String(100))
    due_date: Mapped[date | None] = mapped_column(Date, index=True)

    # Bill-to snapshot, copied from the party when the invoice is created/issued.
    bill_to_company: Mapped[str | None] = mapped_column(String(200))
    bill_to_name: Mapped[str | None] = mapped_column(String(200))
    bill_to_line1: Mapped[str | None] = mapped_column(String(200))
    bill_to_line2: Mapped[str | None] = mapped_column(String(200))
    bill_to_city: Mapped[str | None] = mapped_column(String(100))
    bill_to_region: Mapped[str | None] = mapped_column(String(100))
    bill_to_postal_code: Mapped[str | None] = mapped_column(String(20))
    bill_to_country: Mapped[str | None] = mapped_column(String(100))
    bill_to_phone: Mapped[str | None] = mapped_column(String(50))
    bill_to_email: Mapped[str | None] = mapped_column(String(255))

    tax_jurisdiction_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("tax_jurisdiction.id"), index=True
    )
    tax_location_text: Mapped[str | None] = mapped_column(String(100))

    freight: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    adjustment: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    adjustment_note: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

    # Stored totals: recomputed while draft, frozen at issue (historical ones kept exactly).
    subtotal: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    tax_total: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    total: Mapped[Decimal] = mapped_column(Money, default=ZERO)

    revision_no: Mapped[int] = mapped_column(Integer, default=0)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    void_reason: Mapped[str | None] = mapped_column(Text)
    pdf_file_id: Mapped[int | None] = mapped_column(BigInteger, fk("stored_file.id"), index=True)
    # Imported from the old system: totals are kept as they were, never recomputed.
    is_historical: Mapped[bool] = mapped_column(Boolean, default=False)

    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.sort_order"
    )
    taxes: Mapped[list["InvoiceTax"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLine(IdMixin, Base):
    __tablename__ = "invoice_line"
    __table_args__ = TABLE_ARGS

    invoice_id: Mapped[int] = mapped_column(
        BigInteger, fk("invoice.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    catalog_item_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("catalog_item.id"), index=True
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("subscription.id"), index=True
    )
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Quantity)
    unit: Mapped[str | None] = mapped_column(String(20))
    unit_price: Mapped[Decimal] = mapped_column(Money)
    # Discount per unit as an amount (the UI also accepts a percentage).
    unit_discount: Mapped[Decimal] = mapped_column(Money, default=ZERO)
    # (unit_price - unit_discount) * quantity
    line_total: Mapped[Decimal] = mapped_column(Money)
    tax_category_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("tax_category.id"), index=True
    )
    revenue_category_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("revenue_category.id"), index=True
    )
    # The old system stored tax per unit on each line; kept for historical invoices only.
    legacy_unit_tax: Mapped[Decimal | None] = mapped_column(Money)
    legacy_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class InvoiceTax(IdMixin, Base):
    """Tax charged on an invoice, one row per jurisdiction rate (a snapshot at issue time)."""

    __tablename__ = "invoice_tax"
    __table_args__ = TABLE_ARGS

    invoice_id: Mapped[int] = mapped_column(
        BigInteger, fk("invoice.id", ondelete="CASCADE"), index=True
    )
    jurisdiction_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("tax_jurisdiction.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    rate: Mapped[Decimal | None] = mapped_column(Rate)
    taxable_base: Mapped[Decimal] = mapped_column(Money)
    amount: Mapped[Decimal] = mapped_column(Money)

    invoice: Mapped[Invoice] = relationship(back_populates="taxes")


class InvoiceRevision(IdMixin, Base):
    """The complete invoice as it was before a revision, plus who changed it and why."""

    __tablename__ = "invoice_revision"
    __table_args__ = (UniqueConstraint("invoice_id", "revision_no"), TABLE_ARGS)

    invoice_id: Mapped[int] = mapped_column(
        BigInteger, fk("invoice.id", ondelete="CASCADE"), index=True
    )
    revision_no: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    changed_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("app_user.id"), index=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    pdf_file_id: Mapped[int | None] = mapped_column(BigInteger, fk("stored_file.id"), index=True)
