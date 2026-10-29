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

"""invoice line sku, drop legacy tables

Invoice lines get their own SKU, filled for existing lines from their catalog item.

The legacy_* tables (verbatim copies of the MS Access tables, written by the importer) are
dropped: the application never reads them. This deletes data; the backup update.sh makes first,
the original .mdb and the 1.0 SQL export keep it. Downgrading does not bring them back.

Revision ID: 0a95d8d70569
Revises: 48d37bf42439
Create Date: 2026-10-28 22:33:12.614854
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0a95d8d70569"
down_revision: str | None = "48d37bf42439"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("invoice_line", sa.Column("sku", sa.String(length=50), nullable=True))
    op.execute(
        "UPDATE invoice_line JOIN catalog_item ON catalog_item.id = invoice_line.catalog_item_id "
        "SET invoice_line.sku = catalog_item.sku"
    )

    # The names come from the Access database, so find them rather than list them. `\_` is a
    # literal underscore in LIKE (MariaDB keeps it as is inside a string literal).
    names = op.get_bind().scalars(
        sa.text(
            "SELECT table_name FROM information_schema.tables "
            r"WHERE table_schema = DATABASE() AND table_name LIKE 'legacy\_%'"
        )
    )
    for name in list(names):
        op.drop_table(name)


def downgrade() -> None:
    op.drop_column("invoice_line", "sku")
