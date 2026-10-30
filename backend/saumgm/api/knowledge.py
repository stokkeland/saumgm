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

"""Knowledge base: articles, their categories, versions and files; PDF and email."""

from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saumgm import markup
from saumgm.api.common import (
    LimitParam,
    OffsetParam,
    Page,
    conflict,
    get_owned,
    not_found,
    paginate,
)
from saumgm.api.deps import Auth, DbSession, Editor, Owner, Reader
from saumgm.api.email import draft_out, send_draft
from saumgm.documents import article_pdf
from saumgm.email import EmailError
from saumgm.enums import ArticleStatus, ArticleVisibility
from saumgm.models import (
    KbArticle,
    KbArticleVersion,
    KbAttachment,
    KbCategory,
    Organization,
    Party,
    User,
)
from saumgm.schemas.email import DraftOut, MessageOut, SendIn
from saumgm.schemas.knowledge import (
    ArticleIn,
    ArticleOut,
    ArticlePatch,
    ArticleSummary,
    ArticleVersionOut,
    ArticleVersionSummary,
    KbAttachmentOut,
    KbCategoryIn,
    KbCategoryOut,
    KbCategoryPatch,
    TagCount,
)
from saumgm.services import emailing
from saumgm.services import knowledge as service
from saumgm.storage import MAX_UPLOAD_BYTES, store_file

router = APIRouter(prefix="/kb", tags=["knowledge base"])


def _unprocessable(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


def _org(db: Session, auth: Auth) -> Organization:
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    return org


def _article(db: Session, auth: Auth, article_id: int) -> KbArticle:
    article = db.get(KbArticle, article_id)
    if article is None or article.organization_id != auth.organization_id:
        raise not_found("Article")
    return article


def _user_names(db: Session, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(db.execute(select(User.id, User.display_name).where(User.id.in_(wanted))).all())


# -- categories -----------------------------------------------------------------------------------


@router.get("/categories")
def list_categories(auth: Reader, db: DbSession) -> list[KbCategoryOut]:
    """Every category, parents before their children, with the number of articles in each."""
    rows = service.categories(db, auth.organization_id)
    paths = service.category_paths(rows)
    counts = dict(
        db.execute(
            select(KbArticle.category_id, func.count())
            .where(KbArticle.organization_id == auth.organization_id)
            .group_by(KbArticle.category_id)
        ).all()
    )
    out = [
        KbCategoryOut(
            id=c.id,
            name=c.name,
            parent_id=c.parent_id,
            sort_order=c.sort_order,
            path=paths[c.id],
            articles=counts.get(c.id, 0),
        )
        for c in rows
    ]
    order = {c.id: (c.sort_order, c.name.lower()) for c in rows}
    parents = {c.id: c.parent_id for c in rows}

    def key(c: KbCategoryOut) -> list[tuple[int, str]]:
        chain: list[tuple[int, str]] = []
        current: int | None = c.id
        depth = 0
        while current is not None and depth < 50:
            chain.append(order[current])
            current, depth = parents.get(current), depth + 1
        return list(reversed(chain))

    return sorted(out, key=key)


def _category_out(db: Session, auth: Auth, category_id: int) -> KbCategoryOut:
    return next(c for c in list_categories(auth, db) if c.id == category_id)


@router.post("/categories", status_code=status.HTTP_201_CREATED)
def create_category(body: KbCategoryIn, auth: Editor, db: DbSession) -> KbCategoryOut:
    try:
        service.check_parent(service.categories(db, auth.organization_id), None, body.parent_id)
    except LookupError:
        raise not_found("Parent category") from None
    category = KbCategory(
        organization_id=auth.organization_id,
        name=body.name.strip(),
        parent_id=body.parent_id,
        sort_order=body.sort_order,
    )
    db.add(category)
    db.commit()
    return _category_out(db, auth, category.id)


@router.patch("/categories/{category_id}")
def update_category(
    category_id: int, body: KbCategoryPatch, auth: Editor, db: DbSession
) -> KbCategoryOut:
    """`parent_id: null` moves the category to the top."""
    category = get_owned(db, KbCategory, category_id, auth.organization_id)
    changes = body.model_dump(exclude_unset=True)
    if "parent_id" in changes:
        try:
            service.check_parent(
                service.categories(db, auth.organization_id), category.id, changes["parent_id"]
            )
        except LookupError:
            raise not_found("Parent category") from None
        except service.KnowledgeError as exc:
            raise _unprocessable(exc) from None
    for key in ("name", "sort_order"):
        if key in changes and changes[key] is None:
            del changes[key]
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    for key, value in changes.items():
        setattr(category, key, value)
    db.commit()
    return _category_out(db, auth, category.id)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, auth: Editor, db: DbSession) -> None:
    category = get_owned(db, KbCategory, category_id, auth.organization_id)
    if db.scalar(select(KbCategory.id).where(KbCategory.parent_id == category.id).limit(1)):
        raise conflict("The category has subcategories; move or delete them first")
    if db.scalar(select(KbArticle.id).where(KbArticle.category_id == category.id).limit(1)):
        raise conflict("Articles are in this category; move them first")
    db.delete(category)
    db.commit()


# -- articles -------------------------------------------------------------------------------------


def _summaries(
    db: Session, auth: Auth, articles: list[KbArticle], terms: list[str] | None = None
) -> list[ArticleSummary]:
    paths = service.category_paths(service.categories(db, auth.organization_id))
    party_ids = {a.party_id for a in articles if a.party_id}
    parties = dict(db.execute(select(Party.id, Party.name).where(Party.id.in_(party_ids))).all())
    users = _user_names(db, {a.updated_by_user_id for a in articles})
    return [
        ArticleSummary(
            id=a.id,
            title=a.title,
            category_id=a.category_id,
            category_path=paths.get(a.category_id) if a.category_id else None,
            tags=service.tag_list(a.tags),
            status=a.status,
            visibility=a.visibility,
            party_id=a.party_id,
            party_name=parties.get(a.party_id) if a.party_id else None,
            version=a.version,
            updated_at=a.updated_at,
            updated_by=users.get(a.updated_by_user_id) if a.updated_by_user_id else None,
            snippet=markup.snippet(a.body, terms or []) if terms is not None else None,
        )
        for a in articles
    ]


def _article_out(db: Session, auth: Auth, article: KbArticle) -> ArticleOut:
    summary = _summaries(db, auth, [article])[0]
    files = service.own_files(db, article)
    users = _user_names(db, {article.created_by_user_id})
    return ArticleOut(
        **summary.model_dump(),
        body=article.body,
        created_at=article.created_at,
        created_by=users.get(article.created_by_user_id) if article.created_by_user_id else None,
        attachments=[
            KbAttachmentOut(
                id=att.id,
                file_id=att.file_id,
                name=files[att.file_id].original_name,
                content_type=files[att.file_id].content_type,
                size=files[att.file_id].size_bytes,
                uploaded_at=files[att.file_id].created_at,
                url=f"/api/files/{att.file_id}",
            )
            for att in article.attachments
        ],
    )


def _check_refs(db: Session, auth: Auth, category_id: int | None, party_id: int | None) -> None:
    if category_id is not None:
        get_owned(db, KbCategory, category_id, auth.organization_id)
    if party_id is not None:
        get_owned(db, Party, party_id, auth.organization_id)


@router.get("/articles")
def list_articles(
    auth: Reader,
    db: DbSession,
    q: str | None = Query(None, description="Words in the title, tags or text; best first"),
    category_id: int | None = Query(None, description="This category and those below it"),
    tag: str | None = None,
    status_filter: ArticleStatus | None = Query(None, alias="status"),
    visibility: ArticleVisibility | None = None,
    party_id: int | None = None,
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[ArticleSummary]:
    """Without `q`, the most recently changed first; with it, ranked, with the matching part."""
    stmt: Any = select(KbArticle).where(KbArticle.organization_id == auth.organization_id)
    if category_id is not None:
        rows = service.categories(db, auth.organization_id)
        stmt = stmt.where(KbArticle.category_id.in_(service.descendants(rows, category_id)))
    if tag:
        stmt = service.with_tag(stmt, tag)
    if status_filter:
        stmt = stmt.where(KbArticle.status == status_filter)
    if visibility:
        stmt = stmt.where(KbArticle.visibility == visibility)
    if party_id is not None:
        stmt = stmt.where(KbArticle.party_id == party_id)
    stmt = stmt.order_by(KbArticle.updated_at.desc(), KbArticle.id.desc())
    terms = service.search_terms(q) if q else None
    if terms:
        stmt = service.search(stmt, q or "")
    items, total = paginate(db, stmt, limit, offset)
    return Page(
        items=_summaries(db, auth, list(items), terms),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tags")
def list_tags(auth: Reader, db: DbSession) -> list[TagCount]:
    return [TagCount(tag=t, articles=n) for t, n in service.tag_counts(db, auth.organization_id)]


@router.post("/articles", status_code=status.HTTP_201_CREATED)
def create_article(body: ArticleIn, auth: Editor, db: DbSession) -> ArticleOut:
    _check_refs(db, auth, body.category_id, body.party_id)
    try:
        tags = service.clean_tags(body.tags)
    except service.KnowledgeError as exc:
        raise _unprocessable(exc) from None
    article = KbArticle(
        organization_id=auth.organization_id,
        title=body.title.strip(),
        category_id=body.category_id,
        tags=tags,
        body=body.body,
        status=body.status,
        visibility=body.visibility,
        party_id=body.party_id,
        version=1,
        created_by_user_id=auth.user.id,
        updated_by_user_id=auth.user.id,
    )
    db.add(article)
    db.flush()
    service.add_version(db, article, auth.user.id)
    db.commit()
    db.refresh(article)
    return _article_out(db, auth, article)


@router.get("/articles/{article_id}")
def get_article(article_id: int, auth: Reader, db: DbSession) -> ArticleOut:
    return _article_out(db, auth, _article(db, auth, article_id))


@router.patch("/articles/{article_id}")
def update_article(article_id: int, body: ArticlePatch, auth: Editor, db: DbSession) -> ArticleOut:
    """A change to the title, tags or text is kept as a new version. Pass `base_version` (the
    version the change was made on) so that a newer save by someone else is not overwritten."""
    article = _article(db, auth, article_id)
    changes = body.model_dump(exclude_unset=True)
    for key in ("title", "body", "status", "visibility"):
        if key in changes and changes[key] is None:
            del changes[key]
    if "title" in changes:
        changes["title"] = changes["title"].strip()
    _check_refs(db, auth, changes.get("category_id"), changes.get("party_id"))
    try:
        service.apply(db, article, changes, auth.user.id)
    except service.StaleVersion as exc:
        raise conflict(str(exc)) from None
    except service.KnowledgeError as exc:
        raise _unprocessable(exc) from None
    db.commit()
    db.refresh(article)
    return _article_out(db, auth, article)


@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(article_id: int, auth: Owner, db: DbSession) -> None:
    """The article with all its versions and files."""
    db.delete(_article(db, auth, article_id))
    db.commit()


# -- versions -------------------------------------------------------------------------------------


@router.get("/articles/{article_id}/versions")
def list_versions(article_id: int, auth: Reader, db: DbSession) -> list[ArticleVersionSummary]:
    """Every saved version, the newest first."""
    rows = service.versions(db, _article(db, auth, article_id).id)
    users = _user_names(db, {v.saved_by_user_id for v in rows})
    return [
        ArticleVersionSummary(
            version=v.version,
            title=v.title,
            saved_at=v.saved_at,
            saved_by=users.get(v.saved_by_user_id) if v.saved_by_user_id else None,
        )
        for v in rows
    ]


@router.get("/articles/{article_id}/versions/{version}")
def get_version(article_id: int, version: int, auth: Reader, db: DbSession) -> ArticleVersionOut:
    article = _article(db, auth, article_id)
    row = db.scalars(
        select(KbArticleVersion).where(
            KbArticleVersion.article_id == article.id, KbArticleVersion.version == version
        )
    ).one_or_none()
    if row is None:
        raise not_found("Version")
    users = _user_names(db, {row.saved_by_user_id})
    return ArticleVersionOut(
        version=row.version,
        title=row.title,
        saved_at=row.saved_at,
        saved_by=users.get(row.saved_by_user_id) if row.saved_by_user_id else None,
        tags=service.tag_list(row.tags),
        body=row.body,
    )


# -- files ----------------------------------------------------------------------------------------


@router.post("/articles/{article_id}/attachments", status_code=status.HTTP_201_CREATED)
async def add_attachment(
    article_id: int, file: Annotated[UploadFile, File()], auth: Editor, db: DbSession
) -> ArticleOut:
    """An image or file (at most 20 MB); the text shows it with ![name](url) or links it with
    [name](url), using the attachment's `url`."""
    article = _article(db, auth, article_id)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The file is larger than 20 MB")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty")
    stored = store_file(
        db, auth.organization_id, data, file.filename or "file",
        file.content_type or "application/octet-stream", auth.user.id,
    )  # fmt: skip
    article.attachments.append(KbAttachment(file_id=stored.id))
    db.commit()
    db.refresh(article)
    return _article_out(db, auth, article)


@router.delete(
    "/articles/{article_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_attachment(article_id: int, attachment_id: int, auth: Editor, db: DbSession) -> None:
    article = _article(db, auth, article_id)
    attachment = db.get(KbAttachment, attachment_id)
    if attachment is None or attachment.article_id != article.id:
        raise not_found("Attachment")
    db.delete(attachment)
    db.commit()


# -- PDF and email --------------------------------------------------------------------------------


@router.get("/articles/{article_id}/pdf")
def article_document(article_id: int, auth: Reader, db: DbSession) -> Response:
    article = _article(db, auth, article_id)
    return Response(
        article_pdf(db, _org(db, auth), article),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{service.file_name(article)}.pdf"'},
    )


def _email_draft(db: Session, auth: Auth, article_id: int, pdf: bool) -> emailing.Draft:
    article = _article(db, auth, article_id)
    try:
        return emailing.article_draft(db, _org(db, auth), article, pdf)
    except EmailError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None


@router.get("/articles/{article_id}/email")
def compose_article_email(
    article_id: int, auth: Editor, db: DbSession, pdf: bool = False
) -> DraftOut:
    """A published, shareable article by email: your message, then the article (its images
    inline), to the contact it is about. `pdf` attaches a PDF copy. Internal articles cannot
    be sent."""
    return draft_out(_email_draft(db, auth, article_id, pdf))


@router.post("/articles/{article_id}/email")
def send_article_email(
    article_id: int, body: SendIn, auth: Editor, db: DbSession, pdf: bool = False
) -> MessageOut:
    draft = _email_draft(db, auth, article_id, pdf)
    return send_draft(db, _org(db, auth), draft, body, auth.user.id)
