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

from alembic import command
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from tests.support import alembic_config


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
