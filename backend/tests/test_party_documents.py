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

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.enums import UserRoleType
from saumgm.models import AuditLog, Organization
from saumgm.services.auth import create_user
from tests.api_helpers import contact, ok, ok_list
from tests.support import PASSWORD, login

PDF = ("w9.pdf", b"%PDF-1.4 signed W-9", "application/pdf")


def add(client: TestClient, party_id: int, file: Any = None, **fields: Any) -> dict[str, Any]:
    data = {"document_type": "w9", "title": "W-9"} | {k: str(v) for k, v in fields.items()}
    response = client.post(
        f"/api/contacts/{party_id}/documents",
        data=data,
        files={"file": file} if file else None,
    )
    return ok(response, 201)


def test_upload_download_and_supersede(
    client: TestClient, owner_client: TestClient, db_session: Session, org: Organization
) -> None:
    acme = contact(owner_client, "ACME")
    first = add(owner_client, acme["id"], PDF, document_date="2023-01-15")
    assert first["file"]["original_name"] == "w9.pdf"
    assert (first["status"], first["days_to_expiry"]) == ("no_expiry", None)

    url = f"/api/contacts/{acme['id']}/documents/{first['id']}/file"
    response = owner_client.get(url)
    assert response.status_code == 200 and response.content == PDF[1]
    assert response.headers["cache-control"] == "private, no-store"
    downloads = db_session.scalars(select(AuditLog).where(AuditLog.action == "download")).all()
    assert [(a.entity_type, a.entity_id, a.parent_id) for a in downloads] == [
        ("party_document", str(first["id"]), str(acme["id"]))
    ]

    # a new W-9 replaces the old one, which stays on file as archived
    second = add(owner_client, acme["id"], PDF, replace_previous="true", title="W-9 2026")
    current = ok_list(owner_client.get(f"/api/contacts/{acme['id']}/documents"))
    assert [d["id"] for d in current] == [second["id"]]
    everything = ok_list(
        owner_client.get(f"/api/contacts/{acme['id']}/documents", params={"archived": "all"})
    )
    assert {d["id"] for d in everything} == {first["id"], second["id"]}

    # viewers see the list but not the files, not even through the generic file download
    create_user(db_session, org.id, "vic@example.com", "Vic", UserRoleType.VIEWER, PASSWORD)
    login(client, "vic@example.com")
    assert len(ok_list(client.get(f"/api/contacts/{acme['id']}/documents"))) == 1
    assert client.get(url).status_code == 403
    assert client.get(f"/api/files/{first['file']['id']}").status_code == 403
    assert client.post(f"/api/contacts/{acme['id']}/documents", data={}).status_code == 403


def test_expiry_status_and_attention_list(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    globex = contact(owner_client, "GLOBEX")
    today = date.today()
    expired = add(
        owner_client, acme["id"], document_type="insurance", title="COI 2025",
        expires_on=today - timedelta(days=10),
    )  # fmt: skip
    soon = add(
        owner_client, globex["id"], document_type="tax_exemption", title="ST-120",
        expires_on=today + timedelta(days=20),
    )  # fmt: skip
    later = add(
        owner_client, acme["id"], document_type="contract", title="Hosting agreement",
        expires_on=today + timedelta(days=200), remind_days_before=60,
    )  # fmt: skip
    add(owner_client, acme["id"], title="W-9 on paper")  # no file, no expiry

    assert (expired["status"], soon["status"], later["status"]) == ("expired", "expiring", "valid")
    assert expired["file"] is None  # a paper copy can be recorded without a file

    attention = ok_list(owner_client.get("/api/documents/attention"))
    assert [(d["title"], d["party_name"]) for d in attention] == [
        ("COI 2025", "ACME Inc"),
        ("ST-120", "GLOBEX Inc"),
    ]
    wide = ok_list(owner_client.get("/api/documents/attention", params={"within_days": 365}))
    assert [d["title"] for d in wide] == ["COI 2025", "ST-120", "Hosting agreement"]

    # superseded documents are not chased
    ok(owner_client.post(f"/api/contacts/{acme['id']}/documents/{expired['id']}/archive"))
    assert [d["title"] for d in ok_list(owner_client.get("/api/documents/attention"))] == ["ST-120"]

    # a longer reminder window makes the contract "expiring"
    updated = ok(
        owner_client.patch(
            f"/api/contacts/{acme['id']}/documents/{later['id']}",
            json={"remind_days_before": 365},
        )
    )
    assert updated["status"] == "expiring"


def test_validation_and_exemption_link(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    other = contact(owner_client, "OTHER")
    exemption = ok(
        owner_client.post(
            f"/api/contacts/{acme['id']}/tax-exemptions",
            json={"certificate_type": "Resale (ST-120)", "valid_to": "2027-12-31"},
        ),
        201,
    )
    linked = add(
        owner_client, acme["id"], ("st120.pdf", b"%PDF", "application/pdf"),
        document_type="tax_exemption", title="ST-120", tax_exemption_id=exemption["id"],
        expires_on="2027-12-31",
    )  # fmt: skip
    assert linked["tax_exemption_id"] == exemption["id"]

    base = f"/api/contacts/{other['id']}/documents"
    wrong_party = owner_client.post(
        base, data={"document_type": "tax_exemption", "title": "x",
                    "tax_exemption_id": str(exemption["id"])},
    )  # fmt: skip
    assert wrong_party.status_code == 422
    backwards = owner_client.post(
        base, data={"document_type": "w9", "title": "x", "document_date": "2026-05-01",
                    "expires_on": "2026-01-01"},
    )  # fmt: skip
    assert backwards.status_code == 422
    exe = owner_client.post(
        base,
        data={"document_type": "other", "title": "x"},
        files={"file": ("tool.exe", b"MZ", "application/x-msdownload")},
    )
    assert exe.status_code == 415

    # attach a scan later, then delete (owner only)
    paper = add(owner_client, other["id"], title="W-9 (paper)")
    scanned = owner_client.put(
        f"{base}/{paper['id']}/file", files={"file": ("scan.jpg", b"\xff\xd8jpeg", "image/jpeg")}
    )
    assert ok(scanned)["file"]["content_type"] == "image/jpeg"
    assert owner_client.delete(f"{base}/{paper['id']}").status_code == 204
    assert ok_list(owner_client.get(base)) == []

    # deleting the exemption keeps the certificate, unlinked
    owner_client.delete(f"/api/contacts/{acme['id']}/tax-exemptions/{exemption['id']}")
    docs = ok_list(owner_client.get(f"/api/contacts/{acme['id']}/documents"))
    assert docs[0]["tax_exemption_id"] is None
