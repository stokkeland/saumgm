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

"""Shared FastAPI dependencies: database session, the logged-in user, CSRF and role checks.

Authentication uses an HttpOnly session cookie. Because cookies are sent automatically, every
state-changing request must also carry the CSRF token (double-submit: the `saumgm_csrf` cookie,
readable by the frontend, echoed in the `X-CSRF-Token` header).
"""

import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from saumgm.context import RequestContext, set_context
from saumgm.db import get_session
from saumgm.enums import AuditActor, UserRoleType
from saumgm.models import User
from saumgm.request_logging import request_id_var
from saumgm.security import token_hash
from saumgm.services.auth import load_session

SESSION_COOKIE = "saumgm_session"
CSRF_COOKIE = "saumgm_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

DbSession = Annotated[Session, Depends(get_session)]


@dataclass
class Auth:
    user: User
    organization_id: int
    role: UserRoleType
    token_hash: str


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def request_context(request: Request, **fields: object) -> RequestContext:
    return RequestContext(
        request_id=request_id_var.get(),
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        **fields,  # type: ignore[arg-type]
    )


def verify_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")


def current_auth(request: Request, db: DbSession) -> Auth:
    token = request.cookies.get(SESSION_COOKIE)
    loaded = load_session(db, token) if token else None
    if loaded is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    verify_csrf(request)
    org_id = loaded.auth_session.organization_id
    set_context(
        db,
        request_context(
            request,
            organization_id=org_id,
            user_id=loaded.user.id,
            role=loaded.role,
            actor=AuditActor.USER,
        ),
    )
    return Auth(loaded.user, org_id, loaded.role, token_hash(token or ""))


CurrentAuth = Annotated[Auth, Depends(current_auth)]


def require_role(*roles: UserRoleType) -> object:
    def check(auth: CurrentAuth) -> Auth:
        if auth.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not allow this")
        return auth

    return Depends(check)


# Anyone logged in can read; owners and bookkeepers can change data; owners manage settings/users.
Reader = CurrentAuth
Editor = Annotated[Auth, require_role(UserRoleType.OWNER, UserRoleType.BOOKKEEPER)]
Owner = Annotated[Auth, require_role(UserRoleType.OWNER)]
