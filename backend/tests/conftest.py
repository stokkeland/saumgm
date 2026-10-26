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

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from saumgm.config import get_settings
from saumgm.db import get_session, make_engine
from saumgm.enums import UserRoleType
from saumgm.main import create_app
from saumgm.models import Organization, User
from saumgm.seed import OrganizationSetup, create_organization
from saumgm.services.auth import create_user
from saumgm.storage import LocalStorage, set_storage
from tests.support import PASSWORD, alembic_config, login


@pytest.fixture(autouse=True)
def file_storage(tmp_path: Path) -> Iterator[LocalStorage]:
    """Every test stores files in its own temporary folder."""
    storage = LocalStorage(tmp_path / "files")
    set_storage(storage)
    yield storage
    set_storage(None)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = get_settings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    return url


@pytest.fixture(scope="session")
def test_engine(test_database_url: str) -> Iterator[Engine]:
    """A freshly recreated, empty test database for this test run."""
    url = make_url(test_database_url)
    name = url.database
    assert name and name.startswith("test_"), "refusing to wipe a database not named test_*"

    server = make_engine(url.set(database="").render_as_string(hide_password=False))
    with server.begin() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{name}`"))
        conn.execute(
            text(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        )
    server.dispose()

    engine = make_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrated_engine(test_engine: Engine, test_database_url: str) -> Engine:
    command.upgrade(alembic_config(test_database_url), "head")
    return test_engine


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session on the migrated test schema; everything it writes is rolled back afterwards,
    even if the code under test commits."""
    conn = migrated_engine.connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """API client whose requests all use the rolled-back test session."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client


@pytest.fixture
def org(db_session: Session) -> Organization:
    return create_organization(
        db_session, OrganizationSetup(legal_name="Test Company LLC", display_name="Test Co")
    )


@pytest.fixture
def owner(db_session: Session, org: Organization) -> User:
    return create_user(
        db_session, org.id, "owner@example.com", "Olivia Owner", UserRoleType.OWNER, PASSWORD
    )


@pytest.fixture
def owner_client(client: TestClient, owner: User) -> TestClient:
    login(client, owner.email)
    return client
