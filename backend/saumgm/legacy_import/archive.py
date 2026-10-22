"""Verbatim copy of every Access table into `legacy_<name>` tables (read-only history).

These tables are outside the application schema: Alembic ignores the `legacy_` prefix.
"""

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    insert,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.engine import Connection
from sqlalchemy.sql.schema import SchemaItem
from sqlalchemy.types import TypeEngine

from saumgm.db import TABLE_ARGS
from saumgm.legacy_import.source import LegacyColumn, LegacyData, LegacyTable

ROW_ID = "_row_id"


def archive_table_name(access_name: str) -> str:
    return f"legacy_{access_name.lower()}"


def column_type(col: LegacyColumn) -> TypeEngine[Any]:
    kind = col.type_name.upper()
    if kind in {"COUNTER", "INTEGER"}:
        return Integer()
    if kind in {"SMALLINT", "BYTE", "TINYINT"}:
        return SmallInteger()
    if kind == "VARCHAR":
        return String(col.size or 255)
    if kind == "CURRENCY":
        return Numeric(19, 4)
    if kind in {"DOUBLE", "FLOAT"}:
        return Float(precision=53)
    if kind == "REAL":
        return Float(precision=24)
    if kind == "DATETIME":
        return DateTime()
    if kind == "BIT":
        return Boolean()
    if kind in {"DECIMAL", "NUMERIC"}:
        return Numeric(28, 8)
    if kind == "GUID":
        return String(38)
    if kind == "LONGBINARY":
        return LargeBinary(length=2**32 - 1)
    return LONGTEXT()


def build_table(metadata: MetaData, source: LegacyTable) -> Table:
    columns: list[SchemaItem] = [Column(ROW_ID, BigInteger, primary_key=True, autoincrement=True)]
    columns += [Column(col.name.lower(), column_type(col), nullable=True) for col in source.columns]
    return Table(
        archive_table_name(source.name),
        metadata,
        *columns,
        comment=f"Raw copy of MS Access table {source.name}",
        **TABLE_ARGS,
    )


def write_archive(conn: Connection, data: LegacyData) -> dict[str, int]:
    """(Re)create the archive tables and copy all rows. Returns row counts per archive table."""
    metadata = MetaData()
    tables = {name: build_table(metadata, source) for name, source in data.items()}
    metadata.drop_all(conn)
    metadata.create_all(conn)
    counts: dict[str, int] = {}
    for name, table in tables.items():
        rows = [{key.lower(): value for key, value in row.items()} for row in data[name].rows]
        if rows:
            conn.execute(insert(table), rows)
        counts[table.name] = len(rows)
    return counts
