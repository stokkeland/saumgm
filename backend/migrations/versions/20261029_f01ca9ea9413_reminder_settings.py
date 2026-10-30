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

"""Reminder settings: lead times and digest recipients (organization.remind_*)

Revision ID: f01ca9ea9413
Revises: 305b8779b040
Create Date: 2026-10-29 15:02:11.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f01ca9ea9413"
down_revision: str | None = "305b8779b040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization",
        sa.Column("remind_bill_days", sa.Integer(), server_default="14", nullable=False),
    )
    op.add_column(
        "organization",
        sa.Column("remind_pay_days", sa.Integer(), server_default="10", nullable=False),
    )
    op.add_column("organization", sa.Column("remind_to", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("organization", "remind_to")
    op.drop_column("organization", "remind_pay_days")
    op.drop_column("organization", "remind_bill_days")
