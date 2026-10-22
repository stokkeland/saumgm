from pathlib import Path

from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import Response

BACKEND_DIR = Path(__file__).resolve().parent.parent

PASSWORD = "correct horse battery"


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = url
    return config


def login(client: TestClient, email: str, password: str = PASSWORD) -> Response:
    """Log in and send the CSRF token on every later request, like the frontend does."""
    response: Response = client.post("/api/auth/login", json={"email": email, "password": password})
    if response.status_code == 200:
        client.headers["X-CSRF-Token"] = client.cookies["saumgm_csrf"]
    return response
