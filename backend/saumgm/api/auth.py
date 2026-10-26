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

import secrets

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from saumgm import audit
from saumgm.api.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    CurrentAuth,
    DbSession,
    request_context,
)
from saumgm.config import get_settings
from saumgm.context import set_context
from saumgm.enums import AuditActor, UserRoleType
from saumgm.models import Organization
from saumgm.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=1, max_length=1024)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str


class OrganizationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    country_code: str
    currency_code: str
    locale: str
    timezone: str


class Me(BaseModel):
    user: UserOut
    organization: OrganizationBrief
    role: UserRoleType


def _me(db: DbSession, auth_user: object, organization_id: int, role: UserRoleType) -> Me:
    org = db.get(Organization, organization_id)
    assert org is not None
    return Me(
        user=UserOut.model_validate(auth_user),
        organization=OrganizationBrief.model_validate(org),
        role=role,
    )


def _set_cookies(response: Response, token: str) -> None:
    settings = get_settings()
    max_age = settings.session_days * 86400
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(24),
        max_age=max_age,
        httponly=False,  # the frontend reads it and echoes it in X-CSRF-Token
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> Me:
    set_context(db, request_context(request, actor=AuditActor.USER))
    try:
        user = auth_service.authenticate(db, body.email, body.password)
    except auth_service.TooManyAttempts:
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts; try again later"
        ) from None
    except auth_service.AuthError:
        db.commit()  # keep the failed-attempt record
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password") from None

    org_id = auth_service.default_organization_id(db, user)
    role = auth_service.role_in(db, user.id, org_id) if org_id else None
    if org_id is None or role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has no access")

    set_context(
        db,
        request_context(
            request, organization_id=org_id, user_id=user.id, role=role, actor=AuditActor.USER
        ),
    )
    token = auth_service.start_session(
        db,
        user,
        org_id,
        days=get_settings().session_days,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    audit.record(db, "login", entity_type="app_user", entity_id=str(user.id))
    db.commit()
    _set_cookies(response, token)
    return _me(db, user, org_id, role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, auth: CurrentAuth, db: DbSession) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        auth_service.end_session(db, token)
    audit.record(db, "logout", entity_type="app_user", entity_id=str(auth.user.id))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/me")
def me(auth: CurrentAuth, db: DbSession) -> Me:
    db.commit()  # persist the session's last-seen time
    return _me(db, auth.user, auth.organization_id, auth.role)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, auth: CurrentAuth, db: DbSession) -> None:
    try:
        auth_service.authenticate(db, auth.user.email, body.current_password)
    except auth_service.AuthError:
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong") from None
    try:
        auth_service.set_password(db, auth.user, body.new_password)
    except auth_service.PasswordPolicyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    # Sign out every other device.
    auth_service.end_all_sessions(db, auth.user.id, keep_token_hash=auth.token_hash)
    audit.record(db, "password_change", entity_type="app_user", entity_id=str(auth.user.id))
    db.commit()
