import pytest

from saumgm.config import Settings


def test_cors_origins_split_from_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://u:p@localhost/db")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, https://app.example.com")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:5173", "https://app.example.com"]


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError):
        Settings(_env_file=None)
