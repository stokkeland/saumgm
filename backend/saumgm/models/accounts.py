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
