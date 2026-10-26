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

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.enums import UserRoleType
from saumgm.models import AuditLog, Organization, Party, User
from saumgm.seed import OrganizationSetup, create_organization
from saumgm.services.auth import create_user
from tests.support import PASSWORD, login

ACME: dict[str, Any] = {
    "short_code": "ACME",
    "name": "Acme Corporation",
    "roles": ["client"],
    "email": "billing@acme.example",
    "addresses": [
        {"address_type": "billing", "is_default": True, "city": "Buffalo", "region": "NY",
         "country_code": "US"}
    ],
    "people": [{"name": "Ann Smith", "email": "ann@acme.example", "is_primary": True}],
}  # fmt: skip


def create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/api/contacts", json=ACME | overrides)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_create_and_read_contact(
    owner_client: TestClient, db_session: Session, owner: User
) -> None:
    acme = create(owner_client)
    assert acme["party_no"] == "00000001"  # from the party number sequence
    assert acme["roles"] == ["client"]
    assert acme["city"] == "Buffalo"
    assert [p["name"] for p in acme["people"]] == ["Ann Smith"]

    second = create(owner_client, short_code="BOB", name="Bob's Hosting", roles=["vendor"])
    assert second["party_no"] == "00000002"

    detail = owner_client.get(f"/api/contacts/{acme['id']}").json()
    assert detail["addresses"][0]["region"] == "NY"

    entry = db_session.scalars(
        select(AuditLog).where(AuditLog.entity_type == "party", AuditLog.action == "create")
    ).first()
    assert entry is not None and entry.user_id == owner.id


def test_list_search_and_filters(owner_client: TestClient) -> None:
    create(owner_client)
    create(owner_client, short_code="HOST", name="Hosting Inc", roles=["vendor"], addresses=[])

    def names(**params: Any) -> list[str]:
        page = owner_client.get("/api/contacts", params=params).json()
        return [item["name"] for item in page["items"]]

    assert names() == ["Acme Corporation", "Hosting Inc"]
    assert names(q="host") == ["Hosting Inc"]
    assert names(role="client") == ["Acme Corporation"]
    assert owner_client.get("/api/contacts", params={"limit": 1}).json()["total"] == 2


def test_update_roles_and_fields(owner_client: TestClient) -> None:
    acme = create(owner_client)
    response = owner_client.patch(
        f"/api/contacts/{acme['id']}", json={"roles": ["client", "vendor"], "phone": "555-0100"}
    )
    assert response.status_code == 200
    assert response.json()["roles"] == ["client", "vendor"]
    assert response.json()["phone"] == "555-0100"
    assert response.json()["name"] == "Acme Corporation"  # untouched


def test_self_role_is_reserved(owner_client: TestClient) -> None:
    response = owner_client.post("/api/contacts", json=ACME | {"roles": ["self"]})
    assert response.status_code == 409


def test_archive_hides_and_locks(owner_client: TestClient) -> None:
    acme = create(owner_client)
    assert owner_client.post(f"/api/contacts/{acme['id']}/archive").status_code == 200

    current = owner_client.get("/api/contacts").json()["items"]
    archived = owner_client.get("/api/contacts", params={"archived": "archived"}).json()["items"]
    assert current == [] and [a["id"] for a in archived] == [acme["id"]]

    assert owner_client.patch(f"/api/contacts/{acme['id']}", json={"phone": "1"}).status_code == 409
    assert owner_client.post(f"/api/contacts/{acme['id']}/unarchive").status_code == 200
    assert owner_client.patch(f"/api/contacts/{acme['id']}", json={"phone": "1"}).status_code == 200


def test_addresses_people_and_exemptions(owner_client: TestClient) -> None:
    acme = create(owner_client)
    base = f"/api/contacts/{acme['id']}"

    service = owner_client.post(
        f"{base}/addresses", json={"address_type": "billing", "is_default": True, "city": "Olean"}
    ).json()
    addresses = owner_client.get(base).json()["addresses"]
    assert [a["is_default"] for a in addresses] == [False, True]  # only one default per type
    assert owner_client.delete(f"{base}/addresses/{service['id']}").status_code == 204

    person = owner_client.post(f"{base}/people", json={"name": "Carl"}).json()
    renamed = owner_client.patch(f"{base}/people/{person['id']}", json={"title": "CFO"}).json()
    assert renamed["title"] == "CFO"

    exemption = owner_client.post(
        f"{base}/tax-exemptions", json={"certificate_type": "Resale", "certificate_number": "R-1"}
    )
    assert exemption.status_code == 201
    assert owner_client.get(base).json()["tax_exemptions"][0]["certificate_number"] == "R-1"


def test_other_organizations_are_invisible(owner_client: TestClient, db_session: Session) -> None:
    other = create_organization(db_session, OrganizationSetup(legal_name="Other", display_name="O"))
    stranger = Party(organization_id=other.id, party_no="X1", short_code="X", name="Secret")
    db_session.add(stranger)
    db_session.flush()

    assert owner_client.get(f"/api/contacts/{stranger.id}").status_code == 404
    assert owner_client.get("/api/contacts", params={"q": "Secret"}).json()["total"] == 0


def test_viewers_can_read_but_not_write(
    client: TestClient, db_session: Session, org: Organization
) -> None:
    create_user(db_session, org.id, "viewer@example.com", "Vic", UserRoleType.VIEWER, PASSWORD)
    login(client, "viewer@example.com")
    assert client.get("/api/contacts").status_code == 200
    assert client.post("/api/contacts", json=ACME).status_code == 403


def test_duplicate_short_code_conflicts(owner_client: TestClient) -> None:
    create(owner_client)
    assert owner_client.post("/api/contacts", json=ACME).status_code == 409
