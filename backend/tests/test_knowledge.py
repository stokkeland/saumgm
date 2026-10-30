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

import io
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader
from sqlalchemy.orm import Session

from saumgm import markup
from saumgm.enums import UserRoleType
from saumgm.models import Organization
from saumgm.services.auth import create_user
from tests.api_helpers import contact, ok, ok_list
from tests.support import PASSWORD, Outbox, login
from tests.test_email import client_with_email, set_sender


def article(client: TestClient, **body: Any) -> dict[str, Any]:
    return ok(client.post("/api/kb/articles", json={"title": "Note"} | body), 201)


def category(client: TestClient, name: str, parent_id: int | None = None) -> dict[str, Any]:
    return ok(client.post("/api/kb/categories", json={"name": name, "parent_id": parent_id}), 201)


def attach(
    client: TestClient, article_id: int, name: str, data: bytes, content_type: str
) -> dict[str, Any]:
    """Attach a file; returns the new attachment."""
    url = f"/api/kb/articles/{article_id}/attachments"
    saved = ok(client.post(url, files={"file": (name, data, content_type)}), 201)
    return dict(saved["attachments"][-1])


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def test_category_tree(owner_client: TestClient) -> None:
    clients = category(owner_client, "Clients")
    acme = category(owner_client, "ACME", clients["id"])
    howto = category(owner_client, "How-to")
    assert acme["path"] == "Clients / ACME"
    tree = ok_list(owner_client.get("/api/kb/categories"))
    assert [c["path"] for c in tree] == ["Clients", "Clients / ACME", "How-to"]

    loop = owner_client.patch(f"/api/kb/categories/{clients['id']}", json={"parent_id": acme["id"]})
    assert loop.status_code == 422
    moved = ok(owner_client.patch(f"/api/kb/categories/{howto['id']}",
                                  json={"parent_id": clients["id"]}))  # fmt: skip
    assert moved["path"] == "Clients / How-to"

    note = article(owner_client, category_id=acme["id"])
    assert owner_client.delete(f"/api/kb/categories/{clients['id']}").status_code == 409
    assert owner_client.delete(f"/api/kb/categories/{acme['id']}").status_code == 409
    # Articles below a category are found from it.
    found = ok(owner_client.get("/api/kb/articles", params={"category_id": clients["id"]}))
    assert [a["id"] for a in found["items"]] == [note["id"]]
    assert found["items"][0]["category_path"] == "Clients / ACME"
    assert owner_client.delete(f"/api/kb/categories/{howto['id']}").status_code == 204


def test_search_tags_and_filters(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    vpn = article(
        owner_client,
        title="VPN for the office",
        tags=["Network", "vpn", "network"],
        body="Install the client.\n\nThe server is at **10.0.0.1**; use your own IP login.",
        status="published",
        visibility="shareable",
        party_id=acme["id"],
    )
    assert vpn["tags"] == ["network", "vpn"] and vpn["party_name"] == "ACME Inc"
    printer = article(owner_client, title="Printer driver", tags=["printer"],
                      body="Download it from the vendor; it asks for the VPN.")  # fmt: skip
    article(owner_client, title="Backups", body="Nightly at 2 am.")

    def search(**params: Any) -> list[dict[str, Any]]:
        return list(ok(owner_client.get("/api/kb/articles", params=params))["items"])

    found = search(q="vpn")
    # The article with the word in its title first.
    assert [a["title"] for a in found] == ["VPN for the office", "Printer driver"]
    assert "VPN" in found[1]["snippet"]
    # Every word must be there; short words and numbers are found too.
    assert [a["id"] for a in search(q="ip 10.0.0.1")] == [vpn["id"]]
    assert search(q="vpn nightly") == []
    assert "**" not in search(q="10.0.0.1")[0]["snippet"]

    assert [a["id"] for a in search(tag="Network")] == [vpn["id"]]
    assert [a["id"] for a in search(visibility="shareable")] == [vpn["id"]]
    assert [a["id"] for a in search(status="draft", q="driver")] == [printer["id"]]
    assert [a["id"] for a in search(party_id=acme["id"])] == [vpn["id"]]
    tags = ok_list(owner_client.get("/api/kb/tags"))
    assert tags == [
        {"tag": "network", "articles": 1},
        {"tag": "printer", "articles": 1},
        {"tag": "vpn", "articles": 1},
    ]


def test_versions(owner_client: TestClient, db_session: Session, org: Organization) -> None:
    note = article(owner_client, title="Wi-Fi", body="Password on the router.")
    assert note["version"] == 1
    url = f"/api/kb/articles/{note['id']}"
    saved = ok(owner_client.patch(url, json={"body": "Password in the safe.", "base_version": 1}))
    assert saved["version"] == 2
    # Publishing is no new version; the text is the same.
    assert ok(owner_client.patch(url, json={"status": "published"}))["version"] == 2

    create_user(db_session, org.id, "bk@example.com", "Bo", UserRoleType.BOOKKEEPER, PASSWORD)
    login(owner_client, "bk@example.com")
    stale = owner_client.patch(url, json={"body": "Mine", "base_version": 1})
    assert stale.status_code == 409 and "newer version" in stale.json()["detail"]
    ok(owner_client.patch(url, json={"title": "Wi-Fi at the office", "base_version": 2}))

    versions = ok_list(owner_client.get(f"{url}/versions"))
    assert [(v["version"], v["title"], v["saved_by"]) for v in versions] == [
        (3, "Wi-Fi at the office", "Bo"),
        (2, "Wi-Fi", "Olivia Owner"),
        (1, "Wi-Fi", "Olivia Owner"),
    ]
    first = ok(owner_client.get(f"{url}/versions/1"))
    assert first["body"] == "Password on the router."
    assert owner_client.get(f"{url}/versions/9").status_code == 404
    assert ok(owner_client.get(url))["updated_by"] == "Bo"

    # The audit log notes that the text changed without copying it.
    history = ok(owner_client.get(f"/api/history/kb_article/{note['id']}"))["items"]
    change = next(e for e in history if "body" in e["changes"])
    assert change["changes"]["body"] == ["(23 characters)", "(21 characters)"]
    # Deleting is the owner's.
    assert owner_client.delete(url).status_code == 403
    login(owner_client, "owner@example.com")
    assert owner_client.delete(url).status_code == 204
    assert owner_client.get(url).status_code == 404


def test_files_viewers_and_pdf(
    owner_client: TestClient, db_session: Session, org: Organization
) -> None:
    note = article(owner_client, title="Rack layout")
    url = f"/api/kb/articles/{note['id']}"
    image = attach(owner_client, note["id"], "rack.png", png(), "image/png")
    assert image["url"] == f"/api/files/{image['file_id']}"
    body = (
        f"# Rack\n\n![the rack]({image['url']})\n\n| Port | Device |\n|---|---|\n| 1 | NAS |\n\n"
        "- top\n- bottom\n\n```\nssh admin@nas\n```\n\n[docs](https://example.com)"
    )
    ok(owner_client.patch(url, json={"body": body}))
    pdf = owner_client.get(f"{url}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(pdf.content))
    words = reader.pages[0].extract_text()
    assert "Rack layout" in words and "ssh admin@nas" in words and "NAS" in words
    assert len(reader.pages[0].images) == 1  # the article's own image

    create_user(db_session, org.id, "viewer@example.com", "Vic", UserRoleType.VIEWER, PASSWORD)
    login(owner_client, "viewer@example.com")
    assert ok(owner_client.get(url))["body"] == body
    # Articles are documentation for everyone: viewers see their images.
    assert owner_client.get(image["url"]).status_code == 200
    assert owner_client.post("/api/kb/articles", json={"title": "No"}).status_code == 403
    login(owner_client, "owner@example.com")
    assert owner_client.delete(f"{url}/attachments/{image['id']}").status_code == 204


def test_sending(owner_client: TestClient, outbox: Outbox) -> None:
    acme = client_with_email(owner_client)
    set_sender(owner_client)
    note = article(owner_client, title="Email on your phone", party_id=acme["id"],
                   body="Open **Settings**.")  # fmt: skip
    url = f"/api/kb/articles/{note['id']}"
    internal = owner_client.get(f"{url}/email")
    assert internal.status_code == 400 and "internal" in internal.json()["detail"]
    ok(owner_client.patch(url, json={"visibility": "shareable"}))
    assert "Publish" in owner_client.get(f"{url}/email").json()["detail"]
    ok(owner_client.patch(url, json={"status": "published"}))

    image = attach(owner_client, note["id"], "step1.png", png(), "image/png")
    text_file = attach(owner_client, note["id"], "guide.txt", b"steps", "text/plain")
    secret = article(owner_client, title="Other")
    foreign = attach(owner_client, secret["id"], "w9.pdf", b"%PDF", "application/pdf")["url"]
    body = (
        f"Open **Settings**.\n\n![step 1]({image['url']})\n\n[the guide]({text_file['url']}) and "
        f"[not this]({foreign}) and [the invoice](/invoices/5)\n\n<b>raw</b>"
    )
    ok(owner_client.patch(url, json={"body": body}))

    draft = ok(owner_client.get(f"{url}/email", params={"pdf": True}))
    assert draft["to"] == ["billing@acme.example"]
    assert draft["subject"] == "Email on your phone"
    assert draft["body"] == 'Hello,\n\nPlease see "Email on your phone" below.\n\nTest Co'
    assert draft["attachments"] == ["step1.png", "guide.txt", "email-on-your-phone.pdf"]

    send = {"to": draft["to"], "cc": [], "subject": draft["subject"], "body": "Hi Ann,\n\nHere."}
    ok(owner_client.post(f"{url}/email", json=send, params={"pdf": True}))
    [message] = outbox.messages
    assert message.html.startswith("<div") and "<p>Hi Ann,</p>" in message.html
    assert "<strong>Settings</strong>" in message.html
    assert f'src="cid:kb-{image["file_id"]}"' in message.html
    assert "&lt;b&gt;raw&lt;/b&gt;" in message.html  # raw HTML is shown, not used
    assert "/api/files" not in message.html and "the invoice" in message.html
    assert "/invoices/5" not in message.html  # no APP_URL to point to
    names = [(a.filename, a.inline_id) for a in message.attachments]
    assert names == [
        ("step1.png", f"kb-{image['file_id']}"),
        ("guide.txt", None),
        ("email-on-your-phone.pdf", None),
    ]  # and never another article's file
    assert message.text.startswith("Hi Ann,\n\nHere.\n\nEmail on your phone\n===")

    history = ok(owner_client.get(f"/api/history/kb_article/{note['id']}"))["items"]
    assert any(e["action"] == "email" for e in history)


def test_markdown_rendering() -> None:
    html = markup.to_html("[x](javascript:alert(1)) <script>bad()</script>")
    assert "<a" not in html and "<script" not in html
    assert markup.snippet("# Title\n\nSome long text about the **router**.", ["router"]) == (
        "Title Some long text about the router."
    )
    assert markup.referenced_files("![a](/api/files/3) [b](/api/files/4) [c](/api/files/3)") == [
        3,
        4,
    ]
