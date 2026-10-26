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

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from saumgm.enums import UserRoleType
from saumgm.models import Organization
from saumgm.services.auth import create_user
from tests.api_helpers import contact, issued_invoice, ok
from tests.support import PASSWORD, login


def test_record_history_includes_its_parts(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    owner_client.patch(f"/api/contacts/{acme['id']}", json={"phone": "555-0100"})
    owner_client.post(f"/api/contacts/{acme['id']}/addresses", json={"city": "Olean"})

    history = ok(owner_client.get(f"/api/history/party/{acme['id']}"))
    actions = [(e["entity_type"], e["action"]) for e in history["items"]]
    assert ("party", "update") in actions
    assert ("party_address", "create") in actions
    update = next(e for e in history["items"] if e["action"] == "update")
    assert update["changes"] == {"phone": [None, "555-0100"]}
    assert update["user_name"] == "Olivia Owner"


def test_invoice_history_shows_issue_and_revision_reason(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    invoice = issued_invoice(owner_client, acme["id"], "100")
    owner_client.post(
        f"/api/invoices/{invoice['id']}/revise",
        json={"reason": "Typo in description", "notes": "Fixed"},
    )
    entries = ok(owner_client.get(f"/api/history/invoice/{invoice['id']}"))["items"]
    actions = {e["action"] for e in entries}
    assert {"create", "issue", "revise"} <= actions
    assert any(e["reason"] == "Typo in description" and e["action"] == "update" for e in entries)


def test_audit_log_and_export_are_owner_only(
    owner_client: TestClient, client: TestClient, db_session: Session, org: Organization
) -> None:
    contact(owner_client, "ACME")
    log = ok(owner_client.get("/api/audit", params={"entity_type": "party"}))
    assert log["total"] >= 1

    export = owner_client.get("/api/audit/export.csv", params={"entity_type": "party"})
    assert export.status_code == 200
    assert export.text.splitlines()[0].startswith("occurred_at,user,action")

    create_user(db_session, org.id, "vic@example.com", "Vic", UserRoleType.VIEWER, PASSWORD)
    login(client, "vic@example.com")
    assert client.get("/api/audit").status_code == 403


def test_bulk_archive(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    old = issued_invoice(owner_client, acme["id"], "10", "2015-06-01")
    issued_invoice(owner_client, acme["id"], "20", "2026-06-01")

    result = ok(owner_client.post("/api/archive", json={"through": "2016-12-31"}))
    assert result["archived"]["invoice"] == 1
    assert ok(owner_client.get(f"/api/invoices/{old['id']}"))["archived_at"] is not None
    assert ok(owner_client.get("/api/invoices"))["total"] == 1
