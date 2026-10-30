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

"""Knowledge base: articles in Markdown, a category tree, every saved version, attachments."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import ArticleStatus, ArticleVisibility
from saumgm.models.base import OrgScopedMixin, fk, str_enum

# MEDIUMTEXT (16 MB): long articles with pasted logs or configurations (the database is MariaDB).
LONG_TEXT = MEDIUMTEXT()


class KbCategory(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    """A folder in the category tree (Clients -> Client X, How-to, Servers...)."""

    __tablename__ = "kb_category"
    __table_args__ = TABLE_ARGS

    parent_id: Mapped[int | None] = mapped_column(BigInteger, fk("kb_category.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class KbArticle(IdMixin, OrgScopedMixin, TimestampMixin, Base):
    __tablename__ = "kb_article"
    __table_args__ = (
        # Ranks search results; MariaDB 10.x InnoDB supports it.
        Index("ft_kb_article", "title", "tags", "body", mysql_prefix="FULLTEXT"),
        TABLE_ARGS,
    )

    title: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int | None] = mapped_column(BigInteger, fk("kb_category.id"), index=True)
    # Comma-separated and lower case ("email,outlook"); the API speaks lists.
    tags: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(LONG_TEXT, default="")
    status: Mapped[ArticleStatus] = mapped_column(
        str_enum(ArticleStatus), default=ArticleStatus.DRAFT
    )
    visibility: Mapped[ArticleVisibility] = mapped_column(
        str_enum(ArticleVisibility), default=ArticleVisibility.INTERNAL
    )
    # "How to set up email for Client X"
    party_id: Mapped[int | None] = mapped_column(BigInteger, fk("party.id"), index=True)
    # The number of the latest kb_article_version.
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, fk("app_user.id"))
    updated_by_user_id: Mapped[int | None] = mapped_column(BigInteger, fk("app_user.id"))

    attachments: Mapped[list["KbAttachment"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class KbArticleVersion(IdMixin, Base):
    """The article as it was saved; one row per save that changed the title, tags or text."""

    __tablename__ = "kb_article_version"
    __table_args__ = (UniqueConstraint("article_id", "version"), TABLE_ARGS)

    article_id: Mapped[int] = mapped_column(
        BigInteger, fk("kb_article.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    tags: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(LONG_TEXT)
    saved_by_user_id: Mapped[int | None] = mapped_column(BigInteger, fk("app_user.id"))
    saved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class KbAttachment(IdMixin, Base):
    """An image or file kept with an article; the text can show or link it."""

    __tablename__ = "kb_attachment"
    __table_args__ = TABLE_ARGS

    article_id: Mapped[int] = mapped_column(
        BigInteger, fk("kb_article.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[int] = mapped_column(BigInteger, fk("stored_file.id"), index=True)

    article: Mapped[KbArticle] = relationship(back_populates="attachments")
