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

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from saumgm.enums import UserRoleType
from saumgm.models import Organization
from saumgm.services.auth import create_user
from tests.api_helpers import contact, ok, ok_list
from tests.support import PASSWORD, login


@pytest.fixture
def categories(owner_client: TestClient, db_session: Session, org: Organization) -> dict[str, Any]:
    me = contact(owner_client, "ME", roles=["resource"])
    org.self_party_id = me["id"]
    db_session.flush()
    return {c["name"]: c for c in ok_list(owner_client.get("/api/asset-categories"))}


def asset(client: TestClient, **body: Any) -> dict[str, Any]:
    return ok(client.post("/api/assets", json={"name": "Thing"} | body), 201)


def test_default_categories(categories: dict[str, Any]) -> None:
    assert len(categories) == 11
    assert [f["key"] for f in categories["Laptop"]["fields"]] == ["cpu", "ram", "os"]
    assert {f["key"]: f["type"] for f in categories["Software license"]["fields"]} == {
        "license_key": "text", "seats": "number", "renewal_date": "date",
    }  # fmt: skip


def test_tags_owner_and_extra_fields(owner_client: TestClient, categories: dict[str, Any]) -> None:
    laptop = categories["Laptop"]["id"]
    first = asset(owner_client, name="Jane's laptop", category_id=laptop, serial_number="SN-1",
                  attributes={"ram": "16 GB", "cpu": "i7", "os": ""})  # fmt: skip
    assert (first["tag"], first["owner_name"], first["status"]) == ("A-0001", "ME Inc", "in_use")
    assert first["attributes"] == {"ram": "16 GB", "cpu": "i7"}  # empty values are left out
    assert asset(owner_client)["tag"] == "A-0002"
    ok(owner_client.post("/api/assets", json={"name": "Own tag", "tag": "A-0003"}), 201)
    assert asset(owner_client)["tag"] == "A-0004"  # skips the number used by hand
    taken = owner_client.post("/api/assets", json={"name": "Again", "tag": "A-0001"})
    assert taken.status_code == 409

    unknown = owner_client.post(
        "/api/assets", json={"name": "X", "category_id": laptop, "attributes": {"seats": 3}}
    )
    assert unknown.status_code == 422 and "seats" in unknown.text
    license_id = categories["Software license"]["id"]
    bad = owner_client.post("/api/assets", json={"name": "Office", "category_id": license_id,
                                                  "attributes": {"seats": "many"}})  # fmt: skip
    assert bad.status_code == 422 and "Seats: a number" in bad.text
    office = asset(
        owner_client,
        name="Office",
        category_id=license_id,
        attributes={"seats": "5", "renewal_date": "2027-01-31", "license_key": "AB-12"},
    )
    assert office["attributes"] == {
        "seats": 5,
        "renewal_date": "2027-01-31",
        "license_key": "AB-12",
    }

    # A new category keeps only the fields it also has.
    moved = ok(owner_client.patch(f"/api/assets/{first['id']}",
                                  json={"category_id": categories["Server"]["id"]}))  # fmt: skip
    assert moved["attributes"] == {"ram": "16 GB", "cpu": "i7"}
    moved = ok(owner_client.patch(f"/api/assets/{first['id']}",
                                  json={"category_id": categories["Monitor"]["id"]}))  # fmt: skip
    assert moved["attributes"] == {}


def test_search_and_filters(owner_client: TestClient, categories: dict[str, Any]) -> None:
    client_party = contact(owner_client, "ACME")
    asset(owner_client, name="NAS", category_id=categories["Storage"]["id"],
          attributes={"ip_address": "10.0.0.20"})  # fmt: skip
    theirs = asset(owner_client, name="Firewall", owner_party_id=client_party["id"],
                   manufacturer="Netgate", serial_number="NG-77")  # fmt: skip

    def tags(**params: Any) -> list[str]:
        return [a["tag"] for a in ok(owner_client.get("/api/assets", params=params))["items"]]

    assert tags(q="10.0.0.20") == ["A-0001"]  # an extra field
    assert tags(q="ng-77") == [theirs["tag"]]
    assert tags(owner_party_id=client_party["id"]) == [theirs["tag"]]
    assert tags(category_id=categories["Storage"]["id"]) == ["A-0001"]
    ok(owner_client.patch(f"/api/assets/{theirs['id']}", json={"status": "disposed"}))
    assert tags(status=["in_use", "in_stock"]) == ["A-0001"]


def test_attachments_and_viewers(
    owner_client: TestClient, categories: dict[str, Any], db_session: Session, org: Organization
) -> None:
    nas = asset(owner_client, name="NAS")
    with_file = ok(
        owner_client.post(
            f"/api/assets/{nas['id']}/attachments",
            files={"file": ("config.txt", b"admin password: hunter2", "text/plain")},
        ),
        201,
    )
    [att] = with_file["attachments"]
    assert (att["name"], att["size"]) == ("config.txt", 23)
    assert owner_client.get(f"/api/files/{att['file_id']}").content.startswith(b"admin")

    create_user(db_session, org.id, "viewer@example.com", "Vic", UserRoleType.VIEWER, PASSWORD)
    login(owner_client, "viewer@example.com")
    assert owner_client.get(f"/api/assets/{nas['id']}").status_code == 200
    assert owner_client.get(f"/api/files/{att['file_id']}").status_code == 403
    assert owner_client.post("/api/assets", json={"name": "No"}).status_code == 403

    login(owner_client, "owner@example.com")
    url = f"/api/assets/{nas['id']}/attachments/{att['id']}"
    assert owner_client.delete(url).status_code == 204
    assert ok(owner_client.get(f"/api/assets/{nas['id']}"))["attachments"] == []


def test_categories_are_the_owners(
    owner_client: TestClient, categories: dict[str, Any], db_session: Session, org: Organization
) -> None:
    twice = [{"key": "lens", "label": "Lens"}, {"key": "lens", "label": "L"}]
    dupe = owner_client.post("/api/asset-categories", json={"name": "Camera", "fields": twice})
    assert dupe.status_code == 422
    camera = ok(owner_client.post("/api/asset-categories", json={
        "name": "Camera", "fields": [{"key": "lens", "label": "Lens"}],
    }), 201)  # fmt: skip
    asset(owner_client, name="Door camera", category_id=camera["id"], attributes={"lens": "4mm"})
    assert owner_client.delete(f"/api/asset-categories/{camera['id']}").status_code == 409
    ok(owner_client.patch(f"/api/asset-categories/{camera['id']}", json={"is_active": False}))
    assert (
        owner_client.delete(f"/api/asset-categories/{categories['Other']['id']}").status_code == 204
    )

    create_user(db_session, org.id, "bk@example.com", "Bo", UserRoleType.BOOKKEEPER, PASSWORD)
    login(owner_client, "bk@example.com")
    assert owner_client.post("/api/asset-categories", json={"name": "Drone"}).status_code == 403
    asset(owner_client, name="Bookkeepers add assets")
    assert owner_client.delete("/api/assets/1").status_code == 403


def test_warranties_on_the_to_do_list(owner_client: TestClient, categories: dict[str, Any]) -> None:
    today = date.fromisoformat(ok(owner_client.get("/api/reminders"))["today"])
    acme = contact(owner_client, "ACME")
    in_10 = (today + timedelta(days=10)).isoformat()
    soon = asset(owner_client, name="Server", warranty_expires=in_10, owner_party_id=acme["id"])
    asset(owner_client, name="Switch", support_ends=(today - timedelta(days=5)).isoformat())
    asset(owner_client, name="Old", warranty_expires=(today + timedelta(days=3)).isoformat(),
          status="retired")  # fmt: skip
    asset(owner_client, name="Later", warranty_expires=(today + timedelta(days=90)).isoformat())
    sections = {s["key"]: s for s in ok(owner_client.get("/api/reminders"))["sections"]}
    items = sections["assets"]["items"]
    assert [(i["title"], i["note"], i["flag"]) for i in items] == [
        ("A-0002 Switch", "support contract ended", "expired"),
        ("A-0001 Server (ACME Inc)", "warranty ends", "expiring"),
    ]
    assert items[1]["link"] == f"/assets/{soon['id']}"
    ok(owner_client.patch("/api/reminders/settings", json={"asset_days": 100}))
    sections = {s["key"]: s for s in ok(owner_client.get("/api/reminders"))["sections"]}
    assert len(sections["assets"]["items"]) == 3
