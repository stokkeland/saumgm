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

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import IdentityProvider, UserRoleType
from saumgm.models.base import fk, str_enum


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "app_user"
    __table_args__ = TABLE_ARGS

    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    identities: Mapped[list["UserIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserIdentity(IdMixin, Base):
    """One way of signing in. A user can have a local password and SSO identities at once."""

    __tablename__ = "user_identity"
    __table_args__ = (UniqueConstraint("provider", "issuer", "subject"), TABLE_ARGS)

    user_id: Mapped[int] = mapped_column(
        BigInteger, fk("app_user.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[IdentityProvider] = mapped_column(str_enum(IdentityProvider))
    # OIDC issuer URL / SAML entity id; empty for local accounts.
    issuer: Mapped[str] = mapped_column(String(255), default="")
    # Local: the login name; OIDC: `sub` claim; SAML: NameID.
    subject: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="identities")


class UserRole(IdMixin, Base):
    __tablename__ = "user_role"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", "role"), TABLE_ARGS)

    user_id: Mapped[int] = mapped_column(
        BigInteger, fk("app_user.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int] = mapped_column(
        BigInteger, fk("organization.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[UserRoleType] = mapped_column(str_enum(UserRoleType))

    user: Mapped[User] = relationship(back_populates="roles")


class AuthSession(Base):
    """Server-side login session. The browser holds the token; only its SHA-256 is stored."""

    __tablename__ = "auth_session"
    __table_args__ = TABLE_ARGS

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, fk("app_user.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int] = mapped_column(
        BigInteger, fk("organization.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
