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

from sqlalchemy import JSON, BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from saumgm.db import TABLE_ARGS, Base, IdMixin
from saumgm.enums import AuditActor
from saumgm.models.base import fk, str_enum


class AuditLog(IdMixin, Base):
    """Append-only record of every change and security event. Never updated or deleted."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_parent", "parent_type", "parent_id"),
        TABLE_ARGS,
    )

    organization_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("organization.id"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), index=True
    )
    actor: Mapped[AuditActor] = mapped_column(str_enum(AuditActor), default=AuditActor.USER)
    user_id: Mapped[int | None] = mapped_column(BigInteger, fk("app_user.id"), index=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    # For child rows (invoice lines, addresses, ...) the record they belong to, so the parent's
    # history includes them.
    parent_type: Mapped[str | None] = mapped_column(String(64))
    parent_id: Mapped[str | None] = mapped_column(String(64))
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
