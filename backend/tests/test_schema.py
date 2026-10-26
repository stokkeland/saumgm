# SauMGM - Sauen Management System: billing, sales tax and bookkeeping for small businesses
# Copyright (C) 2026 J. Thomas Stokkeland - https://www.saumgm.com/
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details. You should have received a copy of the
# GNU General Public License along with this program (the LICENSE file); if not, see
# <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
