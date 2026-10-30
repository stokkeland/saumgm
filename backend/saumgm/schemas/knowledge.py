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

from datetime import datetime

from pydantic import BaseModel, Field

from saumgm.enums import ArticleStatus, ArticleVisibility


class KbCategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    sort_order: int = 0


class KbCategoryPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    parent_id: int | None = None
    sort_order: int | None = None


class KbCategoryOut(BaseModel):
    id: int
    name: str
    parent_id: int | None
    sort_order: int
    # "Clients / Client X"
    path: str
    articles: int


class ArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category_id: int | None = None
    tags: list[str] = []
    body: str = ""
    status: ArticleStatus = ArticleStatus.DRAFT
    visibility: ArticleVisibility = ArticleVisibility.INTERNAL
    party_id: int | None = None


class ArticlePatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    category_id: int | None = None
    tags: list[str] | None = None
    body: str | None = None
    status: ArticleStatus | None = None
    visibility: ArticleVisibility | None = None
    party_id: int | None = None
    # The version the change was made on; refused if someone saved a newer one meanwhile.
    base_version: int | None = None


class KbAttachmentOut(BaseModel):
    id: int
    file_id: int
    name: str
    content_type: str
    size: int
    uploaded_at: datetime
    # Where the text can point to it: ![name](url) or [name](url).
    url: str


class ArticleSummary(BaseModel):
    id: int
    title: str
    category_id: int | None
    category_path: str | None
    tags: list[str]
    status: ArticleStatus
    visibility: ArticleVisibility
    party_id: int | None
    party_name: str | None
    version: int
    updated_at: datetime
    updated_by: str | None
    # Search results: the part of the text around the first match.
    snippet: str | None = None


class ArticleOut(ArticleSummary):
    body: str
    created_at: datetime
    created_by: str | None
    attachments: list[KbAttachmentOut]


class ArticleVersionSummary(BaseModel):
    version: int
    title: str
    saved_at: datetime
    saved_by: str | None


class ArticleVersionOut(ArticleVersionSummary):
    tags: list[str]
    body: str


class TagCount(BaseModel):
    tag: str
    articles: int
