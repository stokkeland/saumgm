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

"""The to-do list, the reminder settings (owner), and the digest email."""

from fastapi import APIRouter, HTTPException, status

from saumgm.api.deps import DbSession, Owner, Reader
from saumgm.api.email import draft_out, sent_response
from saumgm.config import get_settings
from saumgm.email import EmailError
from saumgm.models import Organization
from saumgm.schemas.email import DraftOut, MessageOut
from saumgm.schemas.reminders import ReminderSettingsOut, ReminderSettingsPatch, RemindersOut
from saumgm.services import emailing
from saumgm.services import reminders as service

router = APIRouter(tags=["reminders"])


def _org(db: DbSession, org_id: int) -> Organization:
    org = db.get(Organization, org_id)
    assert org is not None
    return org


def _settings_out(db: DbSession, org: Organization) -> ReminderSettingsOut:
    return ReminderSettingsOut(
        bill_days=org.remind_bill_days,
        pay_days=org.remind_pay_days,
        reconcile_days=org.remind_reconcile_days,
        recipients=service.split_addresses(org.remind_to),
        owners=service.owners(db, org.id),
        app_url=get_settings().app_url,
    )


@router.get("/reminders")
def reminders(auth: Reader, db: DbSession) -> RemindersOut:
    """What needs doing, by section: bill clients, pay vendors, collect, documents."""
    return service.to_out(service.build(db, _org(db, auth.organization_id)))


@router.get("/reminders/settings")
def get_reminder_settings(auth: Owner, db: DbSession) -> ReminderSettingsOut:
    return _settings_out(db, _org(db, auth.organization_id))


@router.patch("/reminders/settings")
def update_reminder_settings(
    body: ReminderSettingsPatch, auth: Owner, db: DbSession
) -> ReminderSettingsOut:
    org = _org(db, auth.organization_id)
    if body.bill_days is not None:
        org.remind_bill_days = body.bill_days
    if body.pay_days is not None:
        org.remind_pay_days = body.pay_days
    if body.reconcile_days is not None:
        org.remind_reconcile_days = body.reconcile_days
    if body.recipients is not None:
        addresses = [a.strip() for a in body.recipients if a.strip()]
        bad = service.bad_addresses(addresses)
        if bad:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Not an email address: {', '.join(bad)}"
            )
        joined = ", ".join(addresses)
        if len(joined) > 1000:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Too many addresses")
        org.remind_to = joined or None
    db.commit()
    return _settings_out(db, org)


@router.get("/reminders/digest")
def preview_digest(auth: Owner, db: DbSession) -> DraftOut:
    """The digest as `python -m saumgm notify` would send it now."""
    org = _org(db, auth.organization_id)
    return draft_out(service.digest_draft(db, org, service.build(db, org)))


@router.post("/reminders/digest")
def send_digest(auth: Owner, db: DbSession) -> MessageOut:
    """Send the digest now, to its usual recipients, even if nothing is due."""
    org = _org(db, auth.organization_id)
    draft = service.digest_draft(db, org, service.build(db, org))
    try:
        message = emailing.send(db, org, draft, auth.user.id)
    except EmailError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return sent_response(db, message)
