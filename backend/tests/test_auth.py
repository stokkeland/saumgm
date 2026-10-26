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

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.enums import UserRoleType
from saumgm.models import AuditLog, AuthSession, Organization, User
from saumgm.services.auth import MAX_FAILED_LOGINS, create_user
from tests.support import PASSWORD, login


def test_login_me_logout(client: TestClient, owner: User) -> None:
    response = login(client, "  Owner@Example.com ")
    assert response.status_code == 200
    assert response.json()["role"] == "owner"
    assert response.json()["organization"]["currency_code"] == "USD"
    assert "httponly" in response.headers["set-cookie"].lower()

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "owner@example.com"

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_is_rejected_and_audited(
    client: TestClient, owner: User, db_session: Session
) -> None:
    assert login(client, owner.email, "wrong password!").status_code == 401
    assert login(client, "nobody@example.com", "whatever").status_code == 401
    failures = db_session.scalars(select(AuditLog).where(AuditLog.action == "login_failed")).all()
    assert [f.entity_id for f in failures] == ["owner@example.com", "nobody@example.com"]


def test_too_many_failures_lock_the_login(client: TestClient, owner: User) -> None:
    for _ in range(MAX_FAILED_LOGINS):
        assert login(client, owner.email, "wrong password!").status_code == 401
    assert login(client, owner.email).status_code == 429


def test_requests_need_a_session(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_state_changes_need_the_csrf_token(client: TestClient, owner: User) -> None:
    login(client, owner.email)
    del client.headers["X-CSRF-Token"]
    body = {"current_password": PASSWORD, "new_password": "another long password"}
    assert client.post("/api/auth/password", json=body).status_code == 403


def test_change_password_signs_out_other_sessions(
    client: TestClient, owner: User, db_session: Session
) -> None:
    login(client, owner.email)
    first_cookie = client.cookies["saumgm_session"]
    login(client, owner.email)  # a second "device"
    assert len(db_session.scalars(select(AuthSession)).all()) == 2

    short = {"current_password": PASSWORD, "new_password": "short"}
    assert client.post("/api/auth/password", json=short).status_code == 422
    body = {"current_password": PASSWORD, "new_password": "another long password"}
    assert client.post("/api/auth/password", json=body).status_code == 204

    assert len(db_session.scalars(select(AuthSession)).all()) == 1
    client.cookies.set("saumgm_session", first_cookie)
    assert client.get("/api/auth/me").status_code == 401
    assert login(client, owner.email, "another long password").status_code == 200


def test_inactive_users_cannot_log_in(
    client: TestClient, db_session: Session, org: Organization
) -> None:
    user = create_user(
        db_session, org.id, "gone@example.com", "Gone", UserRoleType.VIEWER, PASSWORD
    )
    user.is_active = False
    db_session.flush()
    assert login(client, "gone@example.com").status_code == 401
