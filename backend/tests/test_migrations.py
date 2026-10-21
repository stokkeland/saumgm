from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = url
    return config


def test_migrations_upgrade_and_downgrade(test_engine: Engine, test_database_url: str) -> None:
    config = alembic_config(test_database_url)
    command.upgrade(config, "head")
    assert "alembic_version" in inspect(test_engine).get_table_names()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_models_match_migrations(test_engine: Engine, test_database_url: str) -> None:
    """Fails if a model was changed without generating a migration for it."""
    command.upgrade(alembic_config(test_database_url), "head")
    command.check(alembic_config(test_database_url))
