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

import argparse
import json
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from saumgm.__main__ import cmd_notify
from saumgm.config import get_settings
from saumgm.enums import UserRoleType
from saumgm.models import EmailMessage, Organization, User
from saumgm.services.auth import create_user
from saumgm.timeutil import utcnow
from tests.api_helpers import contact, issued_invoice, ok
from tests.support import PASSWORD, Outbox, login
from tests.test_api_subscriptions import catalog_item, subscribe
from tests.test_email import set_sender


def today(client: TestClient) -> date:
    return date.fromisoformat(ok(client.get("/api/reminders"))["today"])


def iso(day: date) -> str:
    return day.isoformat()


@pytest.fixture
def busy(owner_client: TestClient) -> date:
    """One of everything: a subscription to bill, a draft, an autopay vendor payment, an
    overdue invoice, and an expired and an expiring W-9."""
    now = today(owner_client)
    acme = contact(owner_client, "ACME")
    hosting = catalog_item(owner_client, "Web Hosting", "120", 12)
    subscribe(
        owner_client,
        acme["id"],
        [{"catalog_item_id": hosting["id"]}],
        start_date=iso(now + timedelta(days=5)),
        service_identifier="acme.example",
    )
    ok(
        owner_client.post(
            "/api/invoices",
            json={"party_id": acme["id"], "lines": [{"description": "Work", "unit_price": "5"}]},
        ),
        201,
    )
    host = contact(owner_client, "HOST", ["vendor"])
    ok(
        owner_client.post(
            "/api/vendor-subscriptions",
            json={"party_id": host["id"], "name": "VPS", "amount": "60", "interval_months": 1,
                  "next_due_date": iso(now + timedelta(days=3)), "autopay": True},
        ),
        201,
    )  # fmt: skip
    issued_invoice(owner_client, acme["id"], "100", iso(now - timedelta(days=60)))
    for title, expires in (
        ("W-9 2020", now - timedelta(days=1)),
        ("W-9 2026", now + timedelta(days=10)),
    ):
        ok(
            owner_client.post(
                f"/api/contacts/{host['id']}/documents",
                data={"document_type": "w9", "title": title, "expires_on": iso(expires)},
            ),
            201,
        )
    return now


def test_nothing_to_do(owner_client: TestClient) -> None:
    todo = ok(owner_client.get("/api/reminders"))
    assert todo["sections"] == [] and todo["count"] == 0
    assert todo["idle_days"] == 0  # the owner just signed in
    assert todo["summary"] == "Nothing needs doing right now."


def test_sections(owner_client: TestClient, busy: date) -> None:
    todo = ok(owner_client.get("/api/reminders"))
    sections = {s["key"]: s for s in todo["sections"]}
    assert list(sections) == ["bill", "pay", "collect", "documents"]

    bill = sections["bill"]
    assert [(i["title"], i["amount"]) for i in bill["items"]] == [
        ("ACME Inc: Web Hosting (acme.example)", "120.0000"),
        ("1 draft invoice to review and issue", None),
    ]
    through = iso(busy + timedelta(days=14))
    assert bill["items"][0]["link"] == f"/subscriptions?due={through}&q=acme.example"
    assert (bill["action_label"], bill["action_link"]) == (
        "Billing run",
        f"/subscriptions?bill={through}",
    )
    assert bill["summary"] == (
        "1 client subscription is due for billing within 14 days; "
        "1 draft invoice is waiting to be issued"
    )

    [vps] = sections["pay"]["items"]
    assert (vps["title"], vps["flag"]) == ("HOST Inc: VPS", "autopay")
    assert sections["pay"]["summary"] == "1 vendor payment is due within 10 days (1 by autopay)"

    [late] = sections["collect"]["items"]
    assert (late["amount"], late["note"], late["flag"]) == (
        "100.0000",
        "30 days overdue",
        "overdue",
    )
    assert late["link"].startswith("/invoices/")

    docs = sections["documents"]
    assert [(i["title"], i["flag"]) for i in docs["items"]] == [
        ("HOST Inc: W-9 2020", "expired"),
        ("HOST Inc: W-9 2026", "expiring"),
    ]
    assert docs["items"][0]["link"].endswith("?tab=documents")
    assert todo["summary"].startswith("1 client subscription is due for billing within 14 days;")


def test_lead_times(owner_client: TestClient, busy: date) -> None:
    settings = ok(owner_client.get("/api/reminders/settings"))
    assert settings | {"app_url": None} == {
        "bill_days": 14, "pay_days": 10, "recipients": [], "owners": ["owner@example.com"],
        "app_url": None,
    }  # fmt: skip
    ok(owner_client.patch("/api/reminders/settings", json={"bill_days": 2, "pay_days": 1}))
    sections = {s["key"]: s for s in ok(owner_client.get("/api/reminders"))["sections"]}
    # The subscription (in 5 days) and the vendor payment (in 3) are no longer listed; the
    # draft still is.
    assert [i["title"] for i in sections["bill"]["items"]] == [
        "1 draft invoice to review and issue"
    ]
    assert sections["bill"]["action_link"] is None
    assert "pay" not in sections


def test_recipients(owner_client: TestClient) -> None:
    bad = owner_client.patch(
        "/api/reminders/settings", json={"recipients": ["me@x.example", "nope"]}
    )
    assert bad.status_code == 422 and "nope" in bad.text
    saved = ok(
        owner_client.patch(
            "/api/reminders/settings", json={"recipients": ["me@x.example", " ", "you@x.example"]}
        )
    )
    assert saved["recipients"] == ["me@x.example", "you@x.example"]
    assert ok(owner_client.get("/api/reminders/digest"))["to"] == ["me@x.example", "you@x.example"]
    ok(owner_client.patch("/api/reminders/settings", json={"recipients": []}))
    assert ok(owner_client.get("/api/reminders/digest"))["to"] == ["owner@example.com"]


def test_only_owners_change_settings(
    client: TestClient, db_session: Session, org: Organization
) -> None:
    create_user(
        db_session, org.id, "bk@example.com", "Bookkeeper", UserRoleType.BOOKKEEPER, PASSWORD
    )
    login(client, "bk@example.com")
    assert client.get("/api/reminders").status_code == 200
    assert client.get("/api/reminders/settings").status_code == 403
    assert client.post("/api/reminders/digest").status_code == 403


def test_digest(
    owner_client: TestClient, busy: date, outbox: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft = ok(owner_client.get("/api/reminders/digest"))
    assert draft["subject"] == "To do at Test Co: 1 to bill, 1 to pay, 1 overdue, 2 documents"
    body = draft["body"]
    assert "BILL CLIENTS\n- " in body and "ACME Inc: Web Hosting (acme.example), $120.00" in body
    assert "HOST Inc: VPS, $60.00 (autopay: will be charged, check the account)" in body
    assert "http" not in body  # no APP_URL, no links

    monkeypatch.setattr(get_settings(), "app_url", "https://app.mybiz.example/")
    assert (
        "Open: https://app.mybiz.example/invoices?view=overdue"
        in ok(owner_client.get("/api/reminders/digest"))["body"]
    )

    assert owner_client.post("/api/reminders/digest").status_code == 400  # no sender yet
    set_sender(owner_client)
    sent = ok(owner_client.post("/api/reminders/digest"))
    assert (sent["kind"], sent["to_addresses"]) == ("digest", "owner@example.com")
    [message] = outbox.messages
    assert message.html and '<a href="https://app.mybiz.example/invoices/' in message.html


def notify(db: Session, capsys: pytest.CaptureFixture[str], **options: Any) -> str:
    args = argparse.Namespace(
        dry_run=False, json=False, always=False, if_idle=None, organization_id=None
    )
    for key, value in options.items():
        setattr(args, key, value)
    cmd_notify(db, args)
    return capsys.readouterr().out


def test_notify_command(
    owner_client: TestClient,
    db_session: Session,
    org: Organization,
    owner: User,
    outbox: Outbox,
    capsys: pytest.CaptureFixture[str],
) -> None:
    options = {"organization_id": org.id}
    assert notify(db_session, capsys, **options) == "Test Co: nothing due; nothing sent.\n"

    issued_invoice(owner_client, contact(owner_client, "ACME")["id"], "100", "2020-01-01")
    printed = notify(db_session, capsys, dry_run=True, **options)
    assert printed.startswith("To: owner@example.com\nSubject: To do at Test Co: 1 overdue\n")
    assert outbox.messages == []

    data = json.loads(notify(db_session, capsys, json=True, **options))
    assert [s["key"] for s in data[0]["sections"]] == ["collect"]

    # The owner signed in just now.
    assert "nothing sent" in notify(db_session, capsys, if_idle=20, **options)
    owner.last_login_at = utcnow() - timedelta(days=21)
    db_session.flush()

    with pytest.raises(SystemExit):  # no sender address yet
        notify(db_session, capsys, if_idle=20, **options)
    set_sender(owner_client)
    printed = notify(db_session, capsys, if_idle=20, **options)
    assert printed == "Test Co: sent 1 item to owner@example.com.\n"
    [message] = outbox.messages
    assert message.text.startswith("Nobody has signed in for 21 days. 1 invoice is overdue")
    logged = db_session.query(EmailMessage).filter_by(kind="digest").one()
    assert logged.sent_by_user_id is None
