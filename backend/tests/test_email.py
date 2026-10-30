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

import base64
import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest
from fastapi.testclient import TestClient

from saumgm.config import get_settings
from saumgm.email import Attachment, EmailError, Message, ResendBackend
from tests.api_helpers import contact, issued_invoice, ok, ok_list
from tests.support import Outbox


def client_with_email(client: TestClient) -> dict[str, Any]:
    acme = contact(client, "ACME")
    ok(client.patch(f"/api/contacts/{acme['id']}", json={"email": "billing@acme.example"}))
    return acme


def set_sender(client: TestClient) -> None:
    ok(
        client.patch(
            "/api/email/settings",
            json={"from_address": "office@mybiz.example", "from_name": "My Biz"},
        )
    )


def test_invoice_by_email(owner_client: TestClient, outbox: Outbox) -> None:
    acme = client_with_email(owner_client)
    invoice = issued_invoice(owner_client, acme["id"], "120", "2026-03-01")

    draft = ok(owner_client.get(f"/api/email/compose/invoice/{invoice['id']}"))
    assert draft["to"] == ["billing@acme.example"] and draft["cc"] == []
    assert draft["subject"] == f"Invoice {invoice['number']} from Test Co"
    assert "$120.00" in draft["body"] and "{" not in draft["body"]
    assert draft["attachments"] == [f"invoice-{invoice['number']}.pdf"]

    body = {"to": draft["to"], "cc": ["boss@acme.example"], "subject": "Your invoice",
            "body": "Hello,\n\nAttached.\n\nMy Biz"}  # fmt: skip
    no_sender = owner_client.post(f"/api/email/send/invoice/{invoice['id']}", json=body)
    assert no_sender.status_code == 400 and "sender" in no_sender.json()["detail"]
    assert outbox.messages == []

    set_sender(owner_client)
    sent = ok(owner_client.post(f"/api/email/send/invoice/{invoice['id']}", json=body))
    assert sent["status"] == "sent" and sent["provider_message_id"] == "msg-1"

    [message] = outbox.messages
    assert message.sender == "My Biz <office@mybiz.example>"
    assert (message.to, message.cc, message.subject) == (
        ["billing@acme.example"],
        ["boss@acme.example"],
        "Your invoice",
    )
    assert "<p>Hello,</p><p>Attached.</p>" in message.html
    [pdf] = message.attachments
    # The document exactly as issued.
    assert pdf.content == owner_client.get(f"/api/invoices/{invoice['id']}/pdf").content

    history = ok(owner_client.get(f"/api/history/invoice/{invoice['id']}"))["items"]
    email = next(e for e in history if e["action"] == "email")
    assert email["changes"]["to"] == "billing@acme.example" and email["changes"]["status"] == "sent"

    log = ok(owner_client.get("/api/email/messages", params={"entity_type": "invoice"}))
    assert log["total"] == 1 and log["items"][0]["attachments"] == [pdf.filename]


def test_only_issued_invoices_go_out(owner_client: TestClient, outbox: Outbox) -> None:
    acme = client_with_email(owner_client)
    draft = ok(
        owner_client.post(
            "/api/invoices",
            json={"party_id": acme["id"], "lines": [{"description": "Work", "unit_price": "5"}]},
        ),
        201,
    )
    response = owner_client.get(f"/api/email/compose/invoice/{draft['id']}")
    assert response.status_code == 400
    assert owner_client.get("/api/email/compose/invoice/999999").status_code == 404


def test_redirect_keeps_real_recipients_out(
    owner_client: TestClient, outbox: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "email_redirect_to", "dev@mybiz.example")
    set_sender(owner_client)
    acme = client_with_email(owner_client)
    invoice = issued_invoice(owner_client, acme["id"], "10")
    assert ok(owner_client.get(f"/api/email/compose/invoice/{invoice['id']}"))["redirect_to"] == (
        "dev@mybiz.example"
    )

    sent = ok(
        owner_client.post(
            f"/api/email/send/invoice/{invoice['id']}",
            json={"to": ["billing@acme.example"], "cc": ["boss@acme.example"],
                  "subject": "Invoice", "body": "Hello"},
        )
    )  # fmt: skip
    [message] = outbox.messages
    assert message.to == ["dev@mybiz.example"] and message.cc == []
    assert message.text.startswith("[Sent to dev@mybiz.example by EMAIL_REDIRECT_TO. Meant for: ")
    assert "billing@acme.example; cc: boss@acme.example" in message.text
    assert sent["to_addresses"] == "billing@acme.example"
    assert sent["redirected_to"] == "dev@mybiz.example"


def test_a_refusal_is_logged(owner_client: TestClient, outbox: Outbox) -> None:
    set_sender(owner_client)
    outbox.fail_with = "Resend refused the message (403): domain not verified"
    response = owner_client.post("/api/email/test", json={})
    assert response.status_code == 502 and "domain not verified" in response.json()["detail"]

    [logged] = ok(owner_client.get("/api/email/messages"))["items"]
    assert logged["status"] == "failed" and "domain not verified" in logged["error"]
    assert logged["kind"] == "test" and logged["to_addresses"] == "owner@example.com"


def test_bad_addresses_are_refused(owner_client: TestClient, outbox: Outbox) -> None:
    set_sender(owner_client)
    response = owner_client.post("/api/email/test", json={"to": "not an address"})
    assert response.status_code == 400
    bad = owner_client.patch("/api/email/settings", json={"from_address": "nope"})
    assert bad.status_code == 422


def test_templates(owner_client: TestClient, outbox: Outbox) -> None:
    templates = ok_list(owner_client.get("/api/email/templates"))
    assert [t["kind"] for t in templates] == ["invoice", "credit_note", "receipt", "report"]
    assert not any(t["customized"] for t in templates)
    assert "due_date" in templates[0]["placeholders"]

    ok(
        owner_client.put(
            "/api/email/templates/invoice",
            json={"subject": "#{invoice_number} ({total})", "body": "Due {due_date}. {unknown}"},
        )
    )
    acme = client_with_email(owner_client)
    invoice = issued_invoice(owner_client, acme["id"], "99", "2026-03-01")
    draft = ok(owner_client.get(f"/api/email/compose/invoice/{invoice['id']}"))
    assert draft["subject"] == f"#{invoice['number']} ($99.00)"
    assert draft["body"].endswith("{unknown}")  # not a placeholder: left as written

    assert owner_client.delete("/api/email/templates/invoice").status_code == 204
    draft = ok(owner_client.get(f"/api/email/compose/invoice/{invoice['id']}"))
    assert draft["subject"].startswith("Invoice ")
    assert (
        owner_client.put(
            "/api/email/templates/test", json={"subject": "x", "body": "y"}
        ).status_code
        == 404
    )


def test_receipt_by_email(owner_client: TestClient, outbox: Outbox) -> None:
    set_sender(owner_client)
    acme = client_with_email(owner_client)
    issued_invoice(owner_client, acme["id"], "40")
    payment = ok(
        owner_client.post(
            "/api/payments",
            json={"party_id": acme["id"], "received_date": "2026-02-01", "amount": "40",
                  "method": "check", "reference": "1001"},
        ),
        201,
    )  # fmt: skip
    draft = ok(owner_client.get(f"/api/email/compose/payment/{payment['id']}"))
    assert draft["kind"] == "receipt" and draft["to"] == ["billing@acme.example"]
    assert "$40.00" in draft["body"]
    assert draft["attachments"] == [f"receipt-{payment['id']}.pdf"]

    ok(
        owner_client.post(
            f"/api/email/send/payment/{payment['id']}",
            json={k: draft[k] for k in ("to", "cc", "subject", "body")},
        )
    )
    assert outbox.messages[0].attachments[0].content.startswith(b"%PDF")
    history = ok(owner_client.get(f"/api/history/payment/{payment['id']}"))["items"]
    assert any(e["action"] == "email" for e in history)


def test_resend_request(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[urllib.request.Request] = []

    class Answer(io.BytesIO):
        def __enter__(self) -> "Answer":
            return self

        def __exit__(self, *args: object) -> None:
            pass

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Answer:
        sent.append(request)
        return Answer(b'{"id": "re_123"}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    message = Message(
        sender="My Biz <office@mybiz.example>",
        to=["a@example.com"],
        cc=["b@example.com"],
        reply_to="reply@mybiz.example",
        subject="Hi",
        text="Hello",
        html="<p>Hello</p>",
    )
    message.attachments = [Attachment("x.pdf", b"%PDF-1", "application/pdf")]
    assert ResendBackend("key-1").send(message) == "re_123"
    [request] = sent
    assert request.get_header("Authorization") == "Bearer key-1"
    payload = json.loads(request.data)  # type: ignore[arg-type]
    assert payload["from"] == "My Biz <office@mybiz.example>" and payload["cc"] == ["b@example.com"]
    assert payload["reply_to"] == "reply@mybiz.example"
    assert payload["attachments"] == [
        {"filename": "x.pdf", "content": base64.b64encode(b"%PDF-1").decode()}
    ]

    def refused(request: urllib.request.Request, timeout: float) -> Answer:
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},  # type: ignore[arg-type]
            io.BytesIO(b'{"message": "The mybiz.example domain is not verified."}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", refused)
    with pytest.raises(EmailError, match=r"403.*not verified"):
        ResendBackend("key-1").send(message)
    with pytest.raises(EmailError, match="RESEND_API_KEY"):
        ResendBackend(None).send(message)


def test_report_by_email(owner_client: TestClient, outbox: Outbox) -> None:
    query = {"date_from": "2026-01-01", "date_to": "2026-03-31", "basis": "accrual"}
    draft = ok(owner_client.get("/api/reports/profit-loss/email", params=query))
    assert draft["to"] == ["owner@example.com"]
    assert draft["subject"].startswith("Profit & loss, Jan 1, 2026")
    assert draft["attachments"] == ["profit-loss-accrual-2026-01-01-2026-03-31.pdf"]

    set_sender(owner_client)
    body = {"to": draft["to"], "subject": draft["subject"], "body": draft["body"]}
    sent = ok(owner_client.post("/api/reports/profit-loss/email", params=query, json=body))
    assert sent["entity_type"] == "report" and sent["kind"] == "report"
    [message] = outbox.messages
    [pdf] = message.attachments
    assert pdf.content.startswith(b"%PDF")

    aging = ok(owner_client.get("/api/reports/aging/email"))
    assert "as of" in aging["subject"]
