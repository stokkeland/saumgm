from collections.abc import Iterator

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
from tests.support import PASSWORD, alembic_config, login


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
