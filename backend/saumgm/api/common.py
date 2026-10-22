"""Helpers shared by the API routers: lists with paging, archive filters, org-scoped lookups."""

from collections.abc import Sequence
from enum import StrEnum
from typing import Any, TypeVar

from fastapi import HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from saumgm.timeutil import utcnow

T = TypeVar("T")
M = TypeVar("M")


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ArchiveFilter(StrEnum):
    CURRENT = "current"
    ARCHIVED = "archived"
    ALL = "all"


LimitParam = Query(50, ge=1, le=500)
OffsetParam = Query(0, ge=0)


def apply_archive_filter(stmt: Select[Any], model: Any, archived: ArchiveFilter) -> Select[Any]:
    if archived == ArchiveFilter.CURRENT:
        return stmt.where(model.archived_at.is_(None))
    if archived == ArchiveFilter.ARCHIVED:
        return stmt.where(model.archived_at.is_not(None))
    return stmt


def paginate(db: Session, stmt: Select[Any], limit: int, offset: int) -> tuple[Sequence[Any], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.limit(limit).offset(offset)).all()
    return items, total


def not_found(what: str = "Record") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


def get_owned[M](db: Session, model: type[M], record_id: int, organization_id: int) -> M:
    """Load a record of the caller's organization, or 404 (other organizations' records are
    indistinguishable from missing ones)."""
    obj = db.get(model, record_id)
    if obj is None or getattr(obj, "organization_id", None) != organization_id:
        raise not_found(model.__name__)
    return obj


def ensure_current(obj: Any) -> None:
    if getattr(obj, "archived_at", None) is not None:
        raise conflict("This record is archived; unarchive it before changing it.")


def apply_changes(obj: Any, changes: BaseModel, exclude: set[str] | None = None) -> None:
    """Copy the fields the client actually sent onto the ORM object."""
    for key, value in changes.model_dump(exclude_unset=True, exclude=exclude).items():
        setattr(obj, key, value)


def set_archived(obj: Any, archived: bool) -> None:
    obj.archived_at = utcnow() if archived else None
