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
from saumgm.models import Organization, User
from saumgm.services.auth import create_user
from tests.support import PASSWORD, login


def test_catalog_items(owner_client: TestClient) -> None:
    bad = owner_client.post(
        "/api/catalog", json={"name": "Hosting", "item_type": "subscription", "price": "10"}
    )
    assert bad.status_code == 422  # subscriptions need a billing interval

    hosting = owner_client.post(
        "/api/catalog",
        json={"name": "Web Hosting", "sku": "WH-1", "item_type": "subscription", "price": "9.5",
              "billing_interval_months": 12, "unit": "Month"},
    ).json()  # fmt: skip
    assert hosting["price"] == "9.5000"

    owner_client.post("/api/catalog", json={"name": "Consulting", "item_type": "service_hourly"})
    page = owner_client.get("/api/catalog", params={"item_type": "subscription"}).json()
    assert [i["name"] for i in page["items"]] == ["Web Hosting"]

    patched = owner_client.patch(f"/api/catalog/{hosting['id']}", json={"is_active": False})
    assert patched.json()["is_active"] is False
    assert owner_client.delete(f"/api/catalog/{hosting['id']}").status_code == 204


def test_categories_and_accounts(owner_client: TestClient) -> None:
    category = owner_client.post("/api/revenue-categories", json={"name": "Hosting"}).json()
    assert owner_client.get("/api/revenue-categories").json() == [category]

    codes = [c["code"] for c in owner_client.get("/api/tax/categories").json()]
    assert "digital" in codes  # seeded

    account = owner_client.post(
        "/api/accounts", json={"code": "4130", "name": "Internet", "account_type": "expense"}
    ).json()
    renamed = owner_client.patch(f"/api/accounts/{account['id']}", json={"name": "Internet svc"})
    assert renamed.json()["name"] == "Internet svc"
    assert owner_client.delete(f"/api/accounts/{account['id']}").status_code == 204


def test_organization_settings(owner_client: TestClient) -> None:
    org = owner_client.get("/api/settings/organization").json()
    assert org["currency_code"] == "USD"
    updated = owner_client.patch(
        "/api/settings/organization", json={"payable_to": "J. Owner", "default_terms_days": 20}
    ).json()
    assert (updated["payable_to"], updated["default_terms_days"]) == ("J. Owner", 20)

    address = owner_client.post(
        "/api/settings/addresses",
        json={"address_type": "remit", "line1": "1 Main St", "city": "Fillmore", "region": "NY"},
    ).json()
    assert owner_client.get("/api/settings/addresses").json() == [address]

    seq = owner_client.patch("/api/settings/numbering/invoice", json={"next_value": 2000})
    assert seq.json()["next_value"] == 2000


def test_only_owners_change_settings(
    client: TestClient, db_session: Session, org: Organization
) -> None:
    create_user(db_session, org.id, "books@example.com", "Bea", UserRoleType.BOOKKEEPER, PASSWORD)
    login(client, "books@example.com")
    assert client.get("/api/settings/organization").status_code == 200
    assert client.patch("/api/settings/organization", json={"tagline": "x"}).status_code == 403
    assert client.get("/api/users").status_code == 403


def test_user_management(owner_client: TestClient, owner: User) -> None:
    created = owner_client.post(
        "/api/users",
        json={"email": "Bea@Example.com", "display_name": "Bea", "role": "bookkeeper",
              "password": "a long enough password"},
    ).json()  # fmt: skip
    assert created["email"] == "bea@example.com"
    assert len(owner_client.get("/api/users").json()) == 2

    viewer = owner_client.patch(f"/api/users/{created['id']}", json={"role": "viewer"}).json()
    assert viewer["role"] == "viewer"

    reset = owner_client.post(
        f"/api/users/{created['id']}/password", json={"new_password": "another long password"}
    )
    assert reset.status_code == 204

    demote_self = owner_client.patch(f"/api/users/{owner.id}", json={"role": "viewer"})
    assert demote_self.status_code == 409


def test_tax_setup(owner_client: TestClient) -> None:
    states = owner_client.get("/api/tax/jurisdictions").json()
    ny = next(j for j in states if j["code"] == "US-NY")

    county = owner_client.post(
        "/api/tax/jurisdictions",
        json={"parent_id": ny["id"], "level": "county", "code": "US-NY-CATTARAUGUS",
              "name": "Cattaraugus County"},
    ).json()  # fmt: skip
    rate = owner_client.post(
        f"/api/tax/jurisdictions/{county['id']}/rates",
        json={"name": "Cattaraugus County", "rate": "0.04", "effective_from": "2020-01-01"},
    ).json()
    assert rate["rate"] == "0.040000"

    registration = owner_client.post(
        "/api/tax/registrations",
        json={"jurisdiction_id": ny["id"], "registration_number": "123", "effective_from":
              "2004-01-01", "filing_frequency": "quarterly"},
    )  # fmt: skip
    assert registration.status_code == 201
    again = owner_client.post(
        "/api/tax/registrations",
        json={"jurisdiction_id": ny["id"], "effective_from": "2020-01-01"},
    )
    assert again.status_code == 409  # overlaps the first one

    category = owner_client.get("/api/tax/categories").json()[0]
    rule = {"jurisdiction_id": ny["id"], "tax_category_id": category["id"], "is_taxable": False}
    first = owner_client.put("/api/tax/rules", json=rule).json()
    second = owner_client.put("/api/tax/rules", json=rule | {"is_taxable": True}).json()
    assert first["id"] == second["id"] and second["is_taxable"] is True
