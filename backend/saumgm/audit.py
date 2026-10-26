"""Automatic audit trail: every insert, update and delete made through the ORM is written to
`audit_log` in the same transaction, so no feature can forget to log (docs/design.md 4.9)."""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, insert, inspect
from sqlalchemy.orm import InstanceState, Session, UOWTransaction

from saumgm.context import AUDIT_ROWS_KEY, get_context

NOT_AUDITED = {"audit_log", "auth_session"}
REDACTED = {"password_hash", "totp_secret"}
NOISE = {"created_at", "updated_at"}

# Child table -> (parent table, column holding the parent id)
PARENTS = {
    "invoice_line": ("invoice", "invoice_id"),
    "invoice_tax": ("invoice", "invoice_id"),
    "invoice_revision": ("invoice", "invoice_id"),
    "payment_allocation": ("payment", "payment_id"),
    "deposit_item": ("deposit", "deposit_id"),
    "expense_line": ("expense", "expense_id"),
    "expense_attachment": ("expense", "expense_id"),
    "party_role": ("party", "party_id"),
    "party_address": ("party", "party_id"),
    "party_contact": ("party", "party_id"),
    "tax_exemption": ("party", "party_id"),
    "party_document": ("party", "party_id"),
    "tax_rate": ("tax_jurisdiction", "jurisdiction_id"),
    "taxability_rule": ("tax_jurisdiction", "jurisdiction_id"),
    "organization_address": ("organization", "organization_id"),
    "number_sequence": ("organization", "organization_id"),
    "user_identity": ("app_user", "user_id"),
    "user_role": ("app_user", "user_id"),
}


def jsonable(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _value(key: str, value: Any) -> Any:
    return "***" if key in REDACTED and value is not None else jsonable(value)


def _changes(obj: object, action: str) -> dict[str, list[Any]]:
    state: InstanceState[Any] = inspect(obj)  # type: ignore[assignment]  # mapped objects only
    changes: dict[str, list[Any]] = {}
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in NOISE:
            continue
        if action == "create":
            value = getattr(obj, key)
            if value is not None:
                changes[key] = [None, _value(key, value)]
        elif action == "delete":
            value = state.dict.get(key)  # values already loaded; never triggers a query
            if value is not None:
                changes[key] = [_value(key, value), None]
        else:
            history = state.attrs[key].history
            if history.has_changes():
                old = history.deleted[0] if history.deleted else None
                new = history.added[0] if history.added else None
                if old != new:
                    changes[key] = [_value(key, old), _value(key, new)]
    return changes


def _after_flush(session: Session, flush_context: UOWTransaction) -> None:
    if not session.info.get(AUDIT_ROWS_KEY, True):
        return
    ctx = get_context(session)
    rows: list[dict[str, Any]] = []
    for action, objects in (
        ("create", session.new),
        ("update", session.dirty),
        ("delete", session.deleted),
    ):
        for obj in objects:
            table = getattr(obj, "__tablename__", None)
            if table is None or table in NOT_AUDITED:
                continue
            changes = _changes(obj, action)
            if action == "update" and not changes:
                continue
            identity = inspect(obj).identity
            parent_type, parent_column = PARENTS.get(table, (None, None))
            parent_id = getattr(obj, parent_column) if parent_column else None
            rows.append(
                {
                    "organization_id": getattr(obj, "organization_id", None) or ctx.organization_id,
                    "actor": ctx.actor,
                    "user_id": ctx.user_id,
                    "batch_id": ctx.batch_id,
                    "action": action,
                    "entity_type": table,
                    "entity_id": "-".join(str(i) for i in identity) if identity else None,
                    "parent_type": parent_type,
                    "parent_id": str(parent_id) if parent_id is not None else None,
                    "changes": changes,
                    "reason": ctx.reason,
                    "request_id": ctx.request_id,
                    "ip_address": ctx.ip_address,
                    "user_agent": ctx.user_agent,
                }
            )
    if rows:
        from saumgm.models.audit import AuditLog

        session.connection().execute(insert(AuditLog), rows)


def install() -> None:
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)


def record(session: Session, action: str, **fields: Any) -> None:
    """An explicit audit entry for events that are not row changes (login, issue, export...)."""
    from saumgm.models.audit import AuditLog

    ctx = get_context(session)
    session.add(
        AuditLog(
            organization_id=fields.pop("organization_id", ctx.organization_id),
            actor=fields.pop("actor", ctx.actor),
            user_id=fields.pop("user_id", ctx.user_id),
            batch_id=fields.pop("batch_id", ctx.batch_id),
            action=action,
            request_id=ctx.request_id,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            reason=fields.pop("reason", ctx.reason),
            **fields,
        )
    )
