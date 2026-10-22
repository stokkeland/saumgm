"""Audit trail: a record's history, the full log (owner), CSV export, and bulk archiving."""

import csv
import io
import json
from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from saumgm import audit
from saumgm.api.common import LimitParam, OffsetParam, Page, paginate
from saumgm.api.deps import DbSession, Owner, Reader
from saumgm.enums import AuditActor
from saumgm.models import AuditLog, User
from saumgm.services.archive import archive_through

router = APIRouter(tags=["audit"])


class AuditEntry(BaseModel):
    id: int
    occurred_at: datetime
    actor: AuditActor
    user_id: int | None
    user_name: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    parent_type: str | None
    parent_id: str | None
    changes: dict[str, Any] | None
    reason: str | None
    request_id: str | None
    ip_address: str | None


class ArchiveRequest(BaseModel):
    through: date


class ArchiveResult(BaseModel):
    through: date
    archived: dict[str, int]


def _entries(db: Session, rows: Any) -> list[AuditEntry]:
    rows = list(rows)
    names = {
        u.id: u.display_name
        for u in db.scalars(select(User).where(User.id.in_({r.user_id for r in rows if r.user_id})))
    }
    return [
        AuditEntry(
            id=r.id,
            occurred_at=r.occurred_at,
            actor=r.actor,
            user_id=r.user_id,
            user_name=names.get(r.user_id) if r.user_id else None,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            parent_type=r.parent_type,
            parent_id=r.parent_id,
            changes=r.changes,
            reason=r.reason,
            request_id=r.request_id,
            ip_address=r.ip_address,
        )
        for r in rows
    ]


@router.get("/history/{entity_type}/{entity_id}")
def history(
    entity_type: str,
    entity_id: str,
    auth: Reader,
    db: DbSession,
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[AuditEntry]:
    """Everything that happened to a record, including its lines, addresses and other parts."""
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.organization_id == auth.organization_id,
            or_(
                and_(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id),
                and_(AuditLog.parent_type == entity_type, AuditLog.parent_id == entity_id),
            ),
        )
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
    )
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=_entries(db, items), total=total, limit=limit, offset=offset)


def _log_query(
    org_id: int,
    entity_type: str | None,
    action: str | None,
    user_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> Any:
    stmt = select(AuditLog).where(AuditLog.organization_id == org_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if date_from is not None:
        stmt = stmt.where(AuditLog.occurred_at >= datetime.combine(date_from, time()))
    if date_to is not None:
        stmt = stmt.where(
            AuditLog.occurred_at < datetime.combine(date_to + timedelta(days=1), time())
        )
    return stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())


@router.get("/audit")
def audit_log(
    auth: Owner,
    db: DbSession,
    entity_type: str | None = None,
    action: str | None = None,
    user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[AuditEntry]:
    stmt = _log_query(auth.organization_id, entity_type, action, user_id, date_from, date_to)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=_entries(db, items), total=total, limit=limit, offset=offset)


@router.get("/audit/export.csv")
def export_audit_log(
    auth: Owner,
    db: DbSession,
    entity_type: str | None = None,
    action: str | None = None,
    user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> StreamingResponse:
    stmt = _log_query(auth.organization_id, entity_type, action, user_id, date_from, date_to)
    entries = _entries(db, db.scalars(stmt))
    audit.record(db, "export", entity_type="audit_log", changes={"rows": len(entries)})
    db.commit()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["occurred_at", "user", "action", "entity_type", "entity_id", "parent_type", "parent_id",
         "reason", "changes", "ip_address", "request_id"]
    )  # fmt: skip
    for e in entries:
        writer.writerow(
            [e.occurred_at.isoformat(), e.user_name or e.actor.value, e.action, e.entity_type,
             e.entity_id, e.parent_type, e.parent_id, e.reason,
             json.dumps(e.changes) if e.changes else "", e.ip_address, e.request_id]
        )  # fmt: skip
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )


@router.post("/archive")
def archive(body: ArchiveRequest, auth: Owner, db: DbSession) -> ArchiveResult:
    """Archive invoices, payments, deposits and expenses dated on or before a day."""
    counts = archive_through(
        db, auth.organization_id, body.through, actor=AuditActor.USER, user_id=auth.user.id
    )
    db.commit()
    return ArchiveResult(through=body.through, archived=counts)
