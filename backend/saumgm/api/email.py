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

"""Email: the sender and templates (owner), sending a record by email, and the log."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from saumgm.api.common import LimitParam, OffsetParam, Page, not_found, paginate
from saumgm.api.deps import DbSession, Editor, Owner
from saumgm.config import get_settings
from saumgm.email import EmailError, get_backend
from saumgm.enums import EmailKind, EmailStatus
from saumgm.models import EmailMessage, EmailTemplate, Organization, User
from saumgm.schemas.email import (
    DraftOut,
    EmailSettingsOut,
    EmailSettingsPatch,
    MessageOut,
    SendIn,
    TemplateIn,
    TemplateOut,
    TestIn,
)
from saumgm.services import emailing

router = APIRouter(tags=["email"])

RecordType = Literal["invoice", "payment"]
# Kinds with a template the business can change (the test message is fixed).
EDITABLE = [
    EmailKind.INVOICE,
    EmailKind.CREDIT_NOTE,
    EmailKind.RECEIPT,
    EmailKind.REPORT,
    EmailKind.ARTICLE,
]


def _org(db: DbSession, org_id: int) -> Organization:
    org = db.get(Organization, org_id)
    assert org is not None
    return org


def _settings_out(org: Organization) -> EmailSettingsOut:
    settings = get_settings()
    return EmailSettingsOut(
        from_address=org.email_from_address,
        from_name=org.email_from_name,
        reply_to=org.email_reply_to,
        sender=emailing.sender(org),
        default_from=settings.email_from,
        backend=get_backend().name,
        redirect_to=settings.email_redirect_to,
    )


def _message_out(db: DbSession, message: EmailMessage) -> MessageOut:
    user = db.get(User, message.sent_by_user_id) if message.sent_by_user_id else None
    return MessageOut(
        id=message.id,
        created_at=message.created_at,
        sent_by=user.display_name if user else None,
        kind=message.kind,
        entity_type=message.entity_type,
        entity_id=message.entity_id,
        from_address=message.from_address,
        to_addresses=message.to_addresses,
        cc_addresses=message.cc_addresses,
        redirected_to=message.redirected_to,
        subject=message.subject,
        body_text=message.body_text,
        attachments=[a["filename"] for a in message.attachments or []],
        provider=message.provider,
        provider_message_id=message.provider_message_id,
        status=message.status,
        error=message.error,
    )


def sent_response(db: DbSession, message: EmailMessage) -> MessageOut:
    """Keep the log either way; a refusal by the provider is then reported as an error."""
    db.commit()
    if message.status == EmailStatus.FAILED:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, message.error or "Sending failed")
    return _message_out(db, message)


def _bad_request(exc: EmailError) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def draft_out(draft: emailing.Draft) -> DraftOut:
    return DraftOut(
        kind=draft.kind,
        to=draft.to,
        cc=draft.cc,
        subject=draft.subject,
        body=draft.body,
        attachments=[a.filename for a in draft.attachments],
        redirect_to=get_settings().email_redirect_to,
    )


def send_draft(
    db: DbSession, org: Organization, draft: emailing.Draft, body: SendIn, user_id: int
) -> MessageOut:
    """Send the draft with the recipients and text the user approved."""
    draft.to, draft.cc, draft.subject, draft.body = body.to, body.cc, body.subject, body.body
    try:
        message = emailing.send(db, org, draft, user_id)
    except EmailError as exc:
        raise _bad_request(exc) from None
    return sent_response(db, message)


# -- settings and templates (owner) ---------------------------------------------------------------


@router.get("/email/settings")
def get_email_settings(auth: Owner, db: DbSession) -> EmailSettingsOut:
    return _settings_out(_org(db, auth.organization_id))


@router.patch("/email/settings")
def update_email_settings(body: EmailSettingsPatch, auth: Owner, db: DbSession) -> EmailSettingsOut:
    org = _org(db, auth.organization_id)
    for key in body.model_fields_set:
        value = (getattr(body, key) or "").strip() or None
        if value and key != "from_name" and not emailing.ADDRESS.match(value):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Not an email address: {value}"
            )
        setattr(org, f"email_{key}", value)  # organization.email_from_address, ...
    db.commit()
    return _settings_out(org)


@router.get("/email/templates")
def list_templates(auth: Owner, db: DbSession) -> list[TemplateOut]:
    out = []
    for kind in EDITABLE:
        subject, body, customized = emailing.template(db, auth.organization_id, kind)
        out.append(
            TemplateOut(
                kind=kind,
                subject=subject,
                body=body,
                customized=customized,
                placeholders=emailing.PLACEHOLDERS[kind],
            )
        )
    return out


def _saved_template(db: DbSession, org_id: int, kind: EmailKind) -> EmailTemplate | None:
    return db.scalars(
        select(EmailTemplate).where(
            EmailTemplate.organization_id == org_id, EmailTemplate.kind == kind
        )
    ).one_or_none()


@router.put("/email/templates/{kind}")
def save_template(kind: EmailKind, body: TemplateIn, auth: Owner, db: DbSession) -> TemplateOut:
    if kind not in EDITABLE:
        raise not_found("Template")
    saved = _saved_template(db, auth.organization_id, kind)
    if saved is None:
        saved = EmailTemplate(organization_id=auth.organization_id, kind=kind)
        db.add(saved)
    saved.subject, saved.body = body.subject, body.body
    db.commit()
    return TemplateOut(
        kind=kind,
        subject=saved.subject,
        body=saved.body,
        customized=True,
        placeholders=emailing.PLACEHOLDERS[kind],
    )


@router.delete("/email/templates/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def reset_template(kind: EmailKind, auth: Owner, db: DbSession) -> None:
    """Back to the built-in text."""
    saved = _saved_template(db, auth.organization_id, kind)
    if saved is not None:
        db.delete(saved)
        db.commit()


@router.post("/email/test")
def send_test(body: TestIn, auth: Owner, db: DbSession) -> MessageOut:
    """Send a test message (to yourself unless another address is given)."""
    org = _org(db, auth.organization_id)
    draft = emailing.test_draft(db, org, auth.user)
    if body.to:
        draft.to = [body.to]
    try:
        message = emailing.send(db, org, draft, auth.user.id)
    except EmailError as exc:
        raise _bad_request(exc) from None
    return sent_response(db, message)


# -- a record by email ----------------------------------------------------------------------------


def _draft(db: DbSession, org: Organization, record_type: str, record_id: int) -> emailing.Draft:
    try:
        return emailing.compose(db, org, record_type, record_id)
    except LookupError as exc:
        raise not_found(str(exc)) from None
    except EmailError as exc:
        raise _bad_request(exc) from None


@router.get("/email/compose/{record_type}/{record_id}")
def compose(record_type: RecordType, record_id: int, auth: Editor, db: DbSession) -> DraftOut:
    """The email as it would go out: recipients, subject and message from the template."""
    return draft_out(_draft(db, _org(db, auth.organization_id), record_type, record_id))


@router.post("/email/send/{record_type}/{record_id}")
def send(
    record_type: RecordType, record_id: int, body: SendIn, auth: Editor, db: DbSession
) -> MessageOut:
    """Send the record by email, with the recipients and text the user approved."""
    org = _org(db, auth.organization_id)
    return send_draft(db, org, _draft(db, org, record_type, record_id), body, auth.user.id)


# -- the log (owner) ------------------------------------------------------------------------------


@router.get("/email/messages")
def list_messages(
    auth: Owner,
    db: DbSession,
    entity_type: str | None = None,
    entity_id: str | None = None,
    status_filter: EmailStatus | None = Query(None, alias="status"),
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[MessageOut]:
    stmt = select(EmailMessage).where(EmailMessage.organization_id == auth.organization_id)
    if entity_type:
        stmt = stmt.where(EmailMessage.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(EmailMessage.entity_id == entity_id)
    if status_filter:
        stmt = stmt.where(EmailMessage.status == status_filter)
    stmt = stmt.order_by(EmailMessage.created_at.desc(), EmailMessage.id.desc())
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=[_message_out(db, m) for m in items], total=total, limit=limit, offset=offset)
