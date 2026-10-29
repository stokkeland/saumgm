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
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import EmailKind, EmailStatus
from saumgm.models.base import OrgScopedMixin, fk, str_enum


class EmailTemplate(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """The business's own subject and message for one kind of email; built-in text otherwise."""

    __tablename__ = "email_template"
    __table_args__ = (UniqueConstraint("organization_id", "kind"), TABLE_ARGS)

    kind: Mapped[EmailKind] = mapped_column(str_enum(EmailKind))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)


class EmailMessage(IdMixin, OrgScopedMixin, Base):
    """Every message sent (or tried), with what it was about. Written once, never changed."""

    __tablename__ = "email_message"
    __table_args__ = (Index("ix_email_message_entity", "entity_type", "entity_id"), TABLE_ARGS)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, index=True
    )
    sent_by_user_id: Mapped[int | None] = mapped_column(BigInteger, fk("app_user.id"), index=True)
    kind: Mapped[EmailKind] = mapped_column(str_enum(EmailKind))
    # The record it belongs to, as in the audit log ("invoice", "42").
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(50))
    from_address: Mapped[str] = mapped_column(String(500))
    to_addresses: Mapped[str] = mapped_column(Text)  # comma-separated, as entered
    cc_addresses: Mapped[str | None] = mapped_column(Text)
    # Set when EMAIL_REDIRECT_TO sent it elsewhere; to/cc then hold the intended recipients.
    redirected_to: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text)
    attachments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(20))
    provider_message_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[EmailStatus] = mapped_column(str_enum(EmailStatus), index=True)
    error: Mapped[str | None] = mapped_column(Text)
