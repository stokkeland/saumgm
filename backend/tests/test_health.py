from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from saumgm import __version__
from saumgm.db import get_session, make_engine
from saumgm.main import create_app


def test_health_ok(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"] == __version__
    assert "MariaDB" in body["database_version"]
    assert response.headers["X-Request-ID"]


def test_health_reports_unreachable_database() -> None:
    app = create_app()
    # Nothing listens on port 1, so the connection fails fast.
    engine = make_engine("mysql+pymysql://nobody:nothing@127.0.0.1:1/none")

    def broken_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = broken_session
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["database"] == "error"


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"
