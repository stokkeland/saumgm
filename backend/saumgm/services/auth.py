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

"""Local accounts and login sessions. SSO identities (OIDC/SAML) plug into the same tables later."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saumgm import audit
from saumgm.enums import IdentityProvider, UserRoleType
from saumgm.models import AuditLog, AuthSession, Organization, User, UserIdentity, UserRole
from saumgm.security import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    new_token,
    token_hash,
    verify_password,
)
from saumgm.timeutil import utcnow

MAX_FAILED_LOGINS = 5
FAILED_LOGIN_WINDOW = timedelta(minutes=15)
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
ROLE_RANK = {UserRoleType.OWNER: 3, UserRoleType.BOOKKEEPER: 2, UserRoleType.VIEWER: 1}


class AuthError(Exception):
    """Wrong credentials or inactive account (deliberately not saying which)."""


class TooManyAttempts(AuthError):
    pass


class PasswordPolicyError(ValueError):
    pass


@dataclass
class LoadedSession:
    auth_session: AuthSession
    user: User
    role: UserRoleType


def normalize_email(email: str) -> str:
    return email.strip().lower()


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def create_user(
    session: Session,
    organization_id: int,
    email: str,
    display_name: str,
    role: UserRoleType,
    password: str | None = None,
) -> User:
    email = normalize_email(email)
    user = User(email=email, display_name=display_name)
    user.roles.append(UserRole(organization_id=organization_id, role=role))
    if password is not None:
        check_password_policy(password)
        user.identities.append(
            UserIdentity(
                provider=IdentityProvider.LOCAL,
                subject=email,
                password_hash=hash_password(password),
            )
        )
    session.add(user)
    session.flush()
    return user


def local_identity(session: Session, email: str) -> UserIdentity | None:
    return session.scalars(
        select(UserIdentity).where(
            UserIdentity.provider == IdentityProvider.LOCAL,
            UserIdentity.issuer == "",
            UserIdentity.subject == normalize_email(email),
        )
    ).one_or_none()


def set_password(session: Session, user: User, password: str) -> None:
    check_password_policy(password)
    identity = local_identity(session, user.email)
    if identity is None:
        user.identities.append(
            UserIdentity(
                provider=IdentityProvider.LOCAL,
                subject=user.email,
                password_hash=hash_password(password),
            )
        )
    else:
        identity.password_hash = hash_password(password)
    session.flush()


def recent_failures(session: Session, email: str, now: datetime) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "login_failed",
                AuditLog.entity_id == normalize_email(email),
                AuditLog.occurred_at >= now - FAILED_LOGIN_WINDOW,
            )
        )
        or 0
    )


def authenticate(session: Session, email: str, password: str) -> User:
    """Check a local password. Failures are recorded in the audit log (commit them!)."""
    now = utcnow()
    email = normalize_email(email)
    if recent_failures(session, email, now) >= MAX_FAILED_LOGINS:
        raise TooManyAttempts()
    identity = local_identity(session, email)
    if (
        identity is None
        or not identity.user.is_active
        or not verify_password(identity.password_hash, password)
    ):
        audit.record(session, "login_failed", entity_type="login", entity_id=email)
        session.flush()
        raise AuthError()
    if identity.password_hash and needs_rehash(identity.password_hash):
        identity.password_hash = hash_password(password)
    identity.last_used_at = now
    identity.user.last_login_at = now
    return identity.user


def role_in(session: Session, user_id: int, organization_id: int) -> UserRoleType | None:
    roles = session.scalars(
        select(UserRole.role).where(
            UserRole.user_id == user_id, UserRole.organization_id == organization_id
        )
    ).all()
    return max(roles, key=lambda r: ROLE_RANK[r]) if roles else None


def default_organization_id(session: Session, user: User) -> int | None:
    return session.scalars(
        select(UserRole.organization_id)
        .join(Organization, Organization.id == UserRole.organization_id)
        .where(UserRole.user_id == user.id)
        .order_by(UserRole.organization_id)
    ).first()


def start_session(
    session: Session,
    user: User,
    organization_id: int,
    *,
    days: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Create a login session; returns the token for the cookie (only its hash is stored)."""
    token = new_token()
    now = utcnow()
    session.add(
        AuthSession(
            token_hash=token_hash(token),
            user_id=user.id,
            organization_id=organization_id,
            created_at=now,
            expires_at=now + timedelta(days=days),
            last_seen_at=now,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )
    session.flush()
    return token


def load_session(session: Session, token: str) -> LoadedSession | None:
    now = utcnow()
    auth_session = session.get(AuthSession, token_hash(token))
    if auth_session is None or auth_session.expires_at <= now:
        return None
    user = session.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        return None
    role = role_in(session, user.id, auth_session.organization_id)
    if role is None:
        return None
    if (
        auth_session.last_seen_at is None
        or now - auth_session.last_seen_at > SESSION_TOUCH_INTERVAL
    ):
        auth_session.last_seen_at = now
    return LoadedSession(auth_session, user, role)


def end_session(session: Session, token: str) -> None:
    auth_session = session.get(AuthSession, token_hash(token))
    if auth_session is not None:
        session.delete(auth_session)
        session.flush()


def end_all_sessions(session: Session, user_id: int, keep_token_hash: str | None = None) -> None:
    for auth_session in session.scalars(select(AuthSession).where(AuthSession.user_id == user_id)):
        if auth_session.token_hash != keep_token_hash:
            session.delete(auth_session)
    session.flush()
