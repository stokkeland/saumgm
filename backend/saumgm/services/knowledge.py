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

"""Knowledge base: tags, the category tree, search, versions, and sending an article."""

import html
import re
from typing import Any

from sqlalchemy import case, desc, func, literal, or_, select
from sqlalchemy.dialects.mysql import match
from sqlalchemy.orm import Session

from saumgm import markup
from saumgm.config import get_settings
from saumgm.email import Attachment, EmailError
from saumgm.enums import ArticleStatus, ArticleVisibility
from saumgm.models import (
    KbArticle,
    KbArticleVersion,
    KbCategory,
    Organization,
    Party,
    StoredFile,
)
from saumgm.storage import read_file

MAX_TAG = 50
TEXT_FIELDS = ("title", "tags", "body")


class KnowledgeError(ValueError):
    """A change the knowledge base refuses; the text says why."""


class StaleVersion(KnowledgeError):
    """The change was made on an older version than the one saved now."""


# -- tags -----------------------------------------------------------------------------------------


def clean_tags(tags: list[str]) -> str | None:
    """Stored lower case and comma-separated, each once, in the order given."""
    seen: list[str] = []
    for tag in tags:
        tag = re.sub(r"\s+", " ", tag.replace(",", " ")).strip().lower()
        if not tag:
            continue
        if len(tag) > MAX_TAG:
            raise KnowledgeError(f"A tag can have at most {MAX_TAG} characters: {tag}")
        if tag not in seen:
            seen.append(tag)
    stored = ",".join(seen)
    if len(stored) > 500:
        raise KnowledgeError("Too many tags")
    return stored or None


def tag_list(stored: str | None) -> list[str]:
    return [t for t in (stored or "").split(",") if t]


# -- categories -----------------------------------------------------------------------------------


def categories(session: Session, org_id: int) -> list[KbCategory]:
    return list(
        session.scalars(
            select(KbCategory)
            .where(KbCategory.organization_id == org_id)
            .order_by(KbCategory.sort_order, KbCategory.name)
        )
    )


def category_paths(rows: list[KbCategory]) -> dict[int, str]:
    """ "Clients / Client X" for every category."""
    by_id = {c.id: c for c in rows}
    paths: dict[int, str] = {}

    def path(c: KbCategory, depth: int = 0) -> str:
        if c.id in paths:
            return paths[c.id]
        parent = by_id.get(c.parent_id) if c.parent_id else None
        # depth guards against a loop in damaged data
        paths[c.id] = f"{path(parent, depth + 1)} / {c.name}" if parent and depth < 50 else c.name
        return paths[c.id]

    for c in rows:
        path(c)
    return paths


def descendants(rows: list[KbCategory], category_id: int) -> set[int]:
    """The category and everything below it."""
    found = {category_id}
    changed = True
    while changed:
        changed = False
        for c in rows:
            if c.parent_id in found and c.id not in found:
                found.add(c.id)
                changed = True
    return found


def check_parent(rows: list[KbCategory], category_id: int | None, parent_id: int | None) -> None:
    if parent_id is None:
        return
    if parent_id not in {c.id for c in rows}:
        raise LookupError("Category")
    if category_id is not None and parent_id in descendants(rows, category_id):
        raise KnowledgeError("A category cannot go inside itself or one of its subcategories")


# -- search ---------------------------------------------------------------------------------------


def search_terms(q: str | None) -> list[str]:
    return re.findall(r"[^\s\"'()+\-<>~*@]+", (q or "").lower())[:10]


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(stmt: Any, q: str) -> Any:
    """Articles with every word of `q` in the title, tags or text, best matches first.

    The full-text index ranks them; the words themselves are matched as parts of words, so
    short ones (IP, NY) and ones the index leaves out are found too.
    """
    terms = search_terms(q)
    if not terms:
        return stmt
    for term in terms:
        pattern = _like(term)
        stmt = stmt.where(
            or_(*(getattr(KbArticle, f).ilike(pattern, escape="\\") for f in TEXT_FIELDS))
        )
    in_title = sum(
        (case((KbArticle.title.ilike(_like(t), escape="\\"), 1), else_=0) for t in terms),
        start=literal(0),
    )
    columns = (KbArticle.__table__.c.title, KbArticle.__table__.c.tags, KbArticle.__table__.c.body)
    relevance = match(*columns, against=" ".join(terms))
    return stmt.order_by(None).order_by(desc(in_title), desc(relevance), desc(KbArticle.updated_at))


def with_tag(stmt: Any, tag: str) -> Any:
    return stmt.where(func.find_in_set(tag.strip().lower(), KbArticle.tags) > 0)


def tag_counts(session: Session, org_id: int) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for stored in session.scalars(
        select(KbArticle.tags).where(
            KbArticle.organization_id == org_id, KbArticle.tags.is_not(None)
        )
    ):
        for tag in tag_list(stored):
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items())


# -- saving and versions --------------------------------------------------------------------------


def add_version(session: Session, article: KbArticle, user_id: int | None) -> None:
    session.add(
        KbArticleVersion(
            article_id=article.id,
            version=article.version,
            title=article.title,
            tags=article.tags,
            body=article.body,
            saved_by_user_id=user_id,
        )
    )


def apply(
    session: Session, article: KbArticle, changes: dict[str, Any], user_id: int | None
) -> None:
    """Change the article; a change to the title, tags or text is kept as a new version."""
    base = changes.pop("base_version", None)
    if base is not None and base != article.version:
        raise StaleVersion(
            "Someone saved a newer version of this article meanwhile; open it again to see it"
        )
    if "tags" in changes:
        changes["tags"] = clean_tags(changes["tags"] or [])
    text_changed = any(
        key in changes and changes[key] != getattr(article, key) for key in TEXT_FIELDS
    )
    for key, value in changes.items():
        setattr(article, key, value)
    article.updated_by_user_id = user_id
    if text_changed:
        article.version += 1
        add_version(session, article, user_id)


def versions(session: Session, article_id: int) -> list[KbArticleVersion]:
    return list(
        session.scalars(
            select(KbArticleVersion)
            .where(KbArticleVersion.article_id == article_id)
            .order_by(KbArticleVersion.version.desc())
        )
    )


# -- the article's own files ----------------------------------------------------------------------


def own_files(session: Session, article: KbArticle) -> dict[int, StoredFile]:
    """The files attached to the article; the only ones a sent or printed article may carry
    (the text could point to any file, a W-9 among them)."""
    ids = [a.file_id for a in article.attachments]
    return {f.id: f for f in session.scalars(select(StoredFile).where(StoredFile.id.in_(ids)))}


def image_loader(session: Session, article: KbArticle) -> Any:
    files = own_files(session, article)

    def load(url: str) -> bytes | None:
        fid = markup.file_id(url)
        stored = files.get(fid) if fid is not None else None
        if stored is None or not stored.content_type.startswith("image/"):
            return None
        return read_file(stored)

    return load


# -- sending --------------------------------------------------------------------------------------


def file_name(article: KbArticle) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", article.title.lower()).strip("-")[:60].strip("-")
    return slug or f"article-{article.id}"


def check_sendable(article: KbArticle) -> None:
    if article.visibility != ArticleVisibility.SHAREABLE:
        raise EmailError("This article is internal; make it shareable to send it")
    if article.status != ArticleStatus.PUBLISHED:
        raise EmailError("Publish the article before sending it")


def email_content(session: Session, article: KbArticle) -> tuple[str, str, list[Attachment]]:
    """The article for an email: HTML (images inline), plain text, and the files it carries.

    Images attached to the article go inline; other attached files it links to go along as
    attachments (the link itself would need a login). Links elsewhere in the app point to it
    when APP_URL is set and are left out otherwise.
    """
    files = own_files(session, article)
    app_url = (get_settings().app_url or "").rstrip("/")
    carried: dict[int, Attachment] = {}

    def rewrite(url: str, is_image: bool) -> str | None:
        fid = markup.file_id(url)
        if fid is not None:
            stored = files.get(fid)
            if stored is None:
                return None
            image = is_image and stored.content_type.startswith("image/")
            if fid not in carried:
                carried[fid] = Attachment(
                    stored.original_name,
                    read_file(stored),
                    stored.content_type,
                    inline_id=f"kb-{fid}" if image else None,
                )
            return f"cid:kb-{fid}" if image else None
        if url.startswith("/"):
            return f"{app_url}{url}" if app_url else None
        return url

    body = markup.to_html(article.body, rewrite)
    page = (
        '<hr style="border: 0; border-top: 1px solid #ddd; margin: 16px 0">'
        '<div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; '
        f'line-height: 1.5; color: #222"><h2>{html.escape(article.title)}</h2>{body}</div>'
    )
    text = f"{article.title}\n{'=' * len(article.title)}\n\n{article.body.strip()}\n"
    return page, text, list(carried.values())


def placeholders(org: Organization, article: KbArticle, party: Party | None) -> dict[str, str]:
    return {
        "article_title": article.title,
        "client_name": party.name if party else "",
        "business_name": org.display_name,
    }
