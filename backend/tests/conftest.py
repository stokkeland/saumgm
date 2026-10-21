from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from saumgm.config import get_settings
from saumgm.db import get_session, make_engine
from saumgm.main import create_app


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


@pytest.fixture
def session(test_engine: Engine) -> Iterator[Session]:
    with sessionmaker(bind=test_engine)() as session:
        yield session


@pytest.fixture
def client(test_engine: Engine) -> Iterator[TestClient]:
    app = create_app()
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    with TestClient(app) as client:
        yield client
