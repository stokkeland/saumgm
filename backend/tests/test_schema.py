from sqlalchemy import ForeignKeyConstraint

from saumgm.models import Base

MAX_IDENTIFIER = 64  # MariaDB limit for table, column, index and constraint names


def test_foreign_key_names_are_unique_in_the_database() -> None:
    """MariaDB 10.x requires foreign-key names to be unique per database, not per table."""
    names = [
        str(c.name)
        for table in Base.metadata.sorted_tables
        for c in table.constraints
        if isinstance(c, ForeignKeyConstraint)
    ]
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates


def test_identifiers_fit_mariadb_limit() -> None:
    too_long = [
        str(name)
        for table in Base.metadata.sorted_tables
        for name in (
            [table.name]
            + [c.name for c in table.columns]
            + [c.name for c in table.constraints if c.name]
            + [i.name for i in table.indexes if i.name]
        )
        if len(str(name)) > MAX_IDENTIFIER
    ]
    assert not too_long
