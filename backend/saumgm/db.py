"""Database engine, sessions and the declarative base.

Compatibility rules (production runs MariaDB 10.11, possibly Galera later):
- InnoDB only, utf8mb4, every table has a primary key.
- Lowercase snake_case names (Windows dev servers fold table-name case, Linux does not).
- Never rely on AUTO_INCREMENT values being contiguous; business numbers (invoice no.,
  party no.) come from counter rows, not from ids.
- No LOCK TABLES / GET_LOCK; keep transactions short.
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, MetaData, create_engine, func, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from saumgm.config import get_settings

# Deterministic constraint names, so Alembic migrations are stable across databases.
# Foreign-key names must be unique per *database* on MariaDB 10.x, so their parts are separated by
# double underscores: fk_invoice__tax_jurisdiction_id__... can't collide with fk_invoice_tax__...
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s__%(column_0_name)s__%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

TABLE_ARGS: dict[str, Any] = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


def make_engine(url: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=3600,
        # Store and compare all timestamps in UTC regardless of server time zone.
        connect_args={"init_command": "SET time_zone = '+00:00'"},
    )


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        _engine = make_engine(get_settings().database_url)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, committed by the caller."""
    get_engine()
    assert _session_factory is not None
    with _session_factory() as session:
        yield session


def server_version(session: Session) -> str:
    return str(session.execute(text("SELECT VERSION()")).scalar_one())
