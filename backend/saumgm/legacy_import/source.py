"""Reading the Access database into plain Python rows.

Everything downstream (archive, mapping, reconciliation) works on `LegacyData`, so it can be
tested without Access or Windows.
"""

import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

Row = dict[str, Any]


@dataclass
class LegacyColumn:
    name: str
    type_name: str  # Access/ODBC type: COUNTER, INTEGER, VARCHAR, LONGCHAR, CURRENCY, ...
    size: int | None
    nullable: bool


@dataclass
class LegacyTable:
    name: str
    columns: list[LegacyColumn]
    rows: list[Row] = field(default_factory=list)


LegacyData = dict[str, LegacyTable]

ACCESS_DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"


def read_access(mdb_path: Path) -> LegacyData:
    """Read every user table. Works on a temporary copy so the original file is never touched."""
    import pyodbc  # Windows-only dependency, needed just for this step

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / mdb_path.name
        shutil.copy2(mdb_path, copy)
        conn = pyodbc.connect(f"DRIVER={{{ACCESS_DRIVER}}};DBQ={copy};ReadOnly=1")
        try:
            cursor = conn.cursor()
            names = [t.table_name for t in cursor.tables(tableType="TABLE")]
            data: LegacyData = {}
            for name in names:
                cursor.execute(f"SELECT * FROM [{name}]")
                # cursor.columns() is broken in the Access driver (garbage in REMARKS), so the
                # column types come from the result description instead.
                columns = [_column(d) for d in cursor.description]
                fields = [c.name for c in columns]
                rows = [dict(zip(fields, row, strict=True)) for row in cursor.fetchall()]
                data[name] = LegacyTable(name=name, columns=columns, rows=rows)
            return data
        finally:
            conn.close()


def _column(description: tuple[Any, ...]) -> LegacyColumn:
    """Map a DB-API description (name, python type, display size, internal size, precision,
    scale, nullable) to the Access type it came from."""
    name, py_type, _, internal_size, precision, scale, nullable = description
    if py_type is bool:
        type_name = "BIT"
    elif py_type is int:
        type_name = "INTEGER"
    elif py_type is float:
        type_name = "DOUBLE"
    elif py_type is Decimal:
        type_name = "CURRENCY" if (precision, scale) == (19, 4) else "DECIMAL"
    elif py_type is datetime:
        type_name = "DATETIME"
    elif py_type in (bytes, bytearray):
        type_name = "LONGBINARY"
    elif py_type is str and internal_size and internal_size <= 255:
        type_name = "VARCHAR"
    else:
        type_name = "LONGCHAR"
    size = internal_size if type_name == "VARCHAR" else None
    return LegacyColumn(name=name, type_name=type_name, size=size, nullable=bool(nullable))
