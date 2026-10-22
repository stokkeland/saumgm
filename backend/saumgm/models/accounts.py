from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import AccountType
from saumgm.models.base import LegacyMixin, OrgScopedMixin, str_enum


class Account(IdMixin, OrgScopedMixin, LegacyMixin, TimestampMixin, Base):
    """Chart of accounts used to classify expenses (and cost of goods sold)."""

    __tablename__ = "account"
    __table_args__ = (UniqueConstraint("organization_id", "code"), TABLE_ARGS)

    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    account_type: Mapped[AccountType] = mapped_column(str_enum(AccountType))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
