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

"""Who is acting, attached to the database session (`session.info`).

FastAPI runs normal endpoints in worker threads, so a ContextVar set in a dependency would not
reliably reach code running later; the session object, however, is shared by the dependency, the
endpoint and the audit hook.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from saumgm.enums import AuditActor, UserRoleType

CTX_KEY = "saumgm_ctx"
AUDIT_ROWS_KEY = "saumgm_audit_rows"


@dataclass(frozen=True)
class RequestContext:
    organization_id: int | None = None
    user_id: int | None = None
    role: UserRoleType | None = None
    actor: AuditActor = AuditActor.SYSTEM
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    batch_id: str | None = None
    reason: str | None = None


def set_context(session: Session, ctx: RequestContext) -> None:
    session.info[CTX_KEY] = ctx


def get_context(session: Session) -> RequestContext:
    ctx = session.info.get(CTX_KEY)
    return ctx if isinstance(ctx, RequestContext) else RequestContext()


def set_audit_rows(session: Session, enabled: bool) -> None:
    """Bulk jobs (the Access import) write one summary entry instead of one per row."""
    session.info[AUDIT_ROWS_KEY] = enabled
