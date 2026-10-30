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

"""knowledge base: articles, categories, versions, attachments

Revision ID: 6de73665add4
Revises: e311844aa18d
Create Date: 2026-10-30 08:07:39.539297
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "6de73665add4"
down_revision: str | None = "e311844aa18d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kb_category",
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_kb_category__organization_id__organization"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["kb_category.id"], name=op.f("fk_kb_category__parent_id__kb_category")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_category")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_kb_category_organization_id"), "kb_category", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_kb_category_parent_id"), "kb_category", ["parent_id"], unique=False)
    op.create_table(
        "kb_article",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        sa.Column("tags", sa.String(length=500), nullable=True),
        sa.Column("body", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "published", name="articlestatus", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column(
            "visibility",
            sa.Enum(
                "internal", "shareable", name="articlevisibility", native_enum=False, length=20
            ),
            nullable=False,
        ),
        sa.Column("party_id", sa.BigInteger(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["kb_category.id"],
            name=op.f("fk_kb_article__category_id__kb_category"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_kb_article__created_by_user_id__app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_kb_article__organization_id__organization"),
        ),
        sa.ForeignKeyConstraint(
            ["party_id"], ["party.id"], name=op.f("fk_kb_article__party_id__party")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_kb_article__updated_by_user_id__app_user"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_article")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ft_kb_article",
        "kb_article",
        ["title", "tags", "body"],
        unique=False,
        mysql_prefix="FULLTEXT",
    )
    op.create_index(op.f("ix_kb_article_category_id"), "kb_article", ["category_id"], unique=False)
    op.create_index(
        op.f("ix_kb_article_organization_id"), "kb_article", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_kb_article_party_id"), "kb_article", ["party_id"], unique=False)
    op.create_table(
        "kb_article_version",
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("tags", sa.String(length=500), nullable=True),
        sa.Column("body", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("saved_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "saved_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["kb_article.id"],
            name=op.f("fk_kb_article_version__article_id__kb_article"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["saved_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_kb_article_version__saved_by_user_id__app_user"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_article_version")),
        sa.UniqueConstraint(
            "article_id", "version", name=op.f("uq_kb_article_version_article_id_version")
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_kb_article_version_article_id"), "kb_article_version", ["article_id"], unique=False
    )
    op.create_table(
        "kb_attachment",
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["kb_article.id"],
            name=op.f("fk_kb_attachment__article_id__kb_article"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["stored_file.id"], name=op.f("fk_kb_attachment__file_id__stored_file")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_attachment")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_kb_attachment_article_id"), "kb_attachment", ["article_id"], unique=False
    )
    op.create_index(op.f("ix_kb_attachment_file_id"), "kb_attachment", ["file_id"], unique=False)


def downgrade() -> None:
    # Dropping the tables drops their indexes (MariaDB refuses to drop one a foreign key needs).
    op.drop_table("kb_attachment")
    op.drop_table("kb_article_version")
    op.drop_table("kb_article")
    op.drop_table("kb_category")
