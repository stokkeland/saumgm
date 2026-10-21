from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.models.base import ArchivableMixin, LegacyMixin, OrgScopedMixin, fk, str_enum
from saumgm.models.enums import AddressType, PartyKind, PartyRoleType

if TYPE_CHECKING:
    from saumgm.models.tax import TaxExemption


class Party(IdMixin, OrgScopedMixin, ArchivableMixin, LegacyMixin, TimestampMixin, Base):
    """Anyone the business deals with: clients, vendors, banks, tax authorities, itself.
    `party_no` is the shared identifier (the old Access "file number")."""

    __tablename__ = "party"
    __table_args__ = (
        UniqueConstraint("organization_id", "party_no"),
        UniqueConstraint("organization_id", "short_code"),
        TABLE_ARGS,
    )

    party_no: Mapped[str] = mapped_column(String(20))
    short_code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[PartyKind] = mapped_column(str_enum(PartyKind), default=PartyKind.COMPANY)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    fax: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))
    tax_id: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    # Client defaults
    default_terms_days: Mapped[int | None] = mapped_column(Integer)
    # Vendor defaults
    vendor_account_no: Mapped[str | None] = mapped_column(String(100))
    default_expense_account_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("account.id"), index=True
    )

    roles: Mapped[list["PartyRole"]] = relationship(
        back_populates="party", cascade="all, delete-orphan"
    )
    addresses: Mapped[list["PartyAddress"]] = relationship(
        back_populates="party", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["PartyContact"]] = relationship(
        back_populates="party", cascade="all, delete-orphan"
    )
    tax_exemptions: Mapped[list["TaxExemption"]] = relationship(cascade="all, delete-orphan")


class PartyRole(IdMixin, Base):
    __tablename__ = "party_role"
    __table_args__ = (UniqueConstraint("party_id", "role"), TABLE_ARGS)

    party_id: Mapped[int] = mapped_column(
        BigInteger, fk("party.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[PartyRoleType] = mapped_column(str_enum(PartyRoleType))

    party: Mapped[Party] = relationship(back_populates="roles")


class PartyAddress(IdMixin, Base):
    """A party's addresses. The service address determines the sales-tax location."""

    __tablename__ = "party_address"
    __table_args__ = TABLE_ARGS

    party_id: Mapped[int] = mapped_column(
        BigInteger, fk("party.id", ondelete="CASCADE"), index=True
    )
    address_type: Mapped[AddressType] = mapped_column(str_enum(AddressType))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    line1: Mapped[str | None] = mapped_column(String(200))
    line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country_code: Mapped[str | None] = mapped_column(String(2))
    tax_jurisdiction_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("tax_jurisdiction.id"), index=True
    )

    party: Mapped[Party] = relationship(back_populates="addresses")


class PartyContact(IdMixin, Base):
    """A person at a party."""

    __tablename__ = "party_contact"
    __table_args__ = TABLE_ARGS

    party_id: Mapped[int] = mapped_column(
        BigInteger, fk("party.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50))
    mobile: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    party: Mapped[Party] = relationship(back_populates="contacts")
