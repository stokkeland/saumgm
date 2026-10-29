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

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from saumgm.services.subscriptions import add_months
from tests.api_helpers import contact, ok, ok_list


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)


def catalog_item(client: TestClient, name: str, price: str, months: int) -> dict[str, Any]:
    return ok(
        client.post(
            "/api/catalog",
            json={"name": name, "item_type": "subscription", "price": price,
                  "billing_interval_months": months},
        ),
        201,
    )  # fmt: skip


@pytest.fixture
def hosting(owner_client: TestClient) -> dict[str, Any]:
    return catalog_item(owner_client, "Web Hosting", "120", 12)


@pytest.fixture
def domain(owner_client: TestClient) -> dict[str, Any]:
    return catalog_item(owner_client, "Domain", "20", 12)


def subscribe(
    client: TestClient, party_id: int, lines: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    return ok(
        client.post(
            "/api/subscriptions",
            json={"party_id": party_id, "start_date": "2026-01-01", "lines": lines} | extra,
        ),
        201,
    )


def test_subscription_defaults_from_the_catalog(
    owner_client: TestClient, hosting: dict[str, Any], domain: dict[str, Any]
) -> None:
    acme = contact(owner_client, "ACME")
    sub = subscribe(
        owner_client,
        acme["id"],
        [{"catalog_item_id": hosting["id"]}, {"catalog_item_id": domain["id"], "quantity": "2"}],
        service_identifier="acme.example",
    )
    assert sub["billing_interval_months"] == 12
    assert sub["next_bill_date"] == "2026-01-01"
    assert [(line["description"], line["unit_price"], line["total"]) for line in sub["lines"]] == [
        ("Web Hosting", "120.0000", "120.0000"),
        ("Domain", "20.0000", "40.0000"),
    ]
    assert (sub["summary"], sub["total"], sub["monthly_revenue"]) == (
        "Web Hosting, Domain", "160.0000", "13.3300"
    )  # fmt: skip

    due = ok(owner_client.get("/api/subscriptions", params={"due_through": "2026-01-31"}))
    assert [s["service_identifier"] for s in due["items"]] == ["acme.example"]
    found = ok(owner_client.get("/api/subscriptions", params={"q": "domain"}))
    assert found["total"] == 1

    # Editing replaces the lines.
    edited = ok(
        owner_client.patch(
            f"/api/subscriptions/{sub['id']}",
            json={"lines": [{"catalog_item_id": hosting["id"], "description": "Hosting, gold",
                             "price_override": "150", "discount_pct": "10"}]},
        )
    )  # fmt: skip
    assert [(line["description"], line["total"]) for line in edited["lines"]] == [
        ("Hosting, gold", "135.0000")
    ]
    no_lines = owner_client.patch(f"/api/subscriptions/{sub['id']}", json={"lines": []})
    assert no_lines.status_code == 422


def test_billing_run(
    owner_client: TestClient, hosting: dict[str, Any], domain: dict[str, Any]
) -> None:
    acme = contact(owner_client, "ACME")
    bob = contact(owner_client, "BOB")
    subscribe(owner_client, acme["id"],
              [{"catalog_item_id": hosting["id"]}, {"catalog_item_id": domain["id"]}],
              service_identifier="acme.example")  # fmt: skip
    shop = [{"catalog_item_id": hosting["id"], "price_override": "90"}]
    subscribe(owner_client, acme["id"], shop, service_identifier="acme.shop")
    monthly = subscribe(owner_client, bob["id"], [{"catalog_item_id": hosting["id"]}],
                        service_identifier="bob.example", billing_interval_months=1,
                        start_date="2026-01-15")  # fmt: skip

    preview = ok(
        owner_client.post(
            "/api/subscriptions/billing-run", json={"through": "2026-03-31", "dry_run": True}
        )
    )
    assert preview["dry_run"] and preview["lines_created"] == 6  # 3 annual + 3 monthly (catch-up)
    assert len(preview["invoices"]) == 3  # one per subscription
    assert ok(owner_client.get("/api/invoices"))["total"] == 0  # nothing saved
    assert (
        ok(owner_client.get(f"/api/subscriptions/{monthly['id']}"))["next_bill_date"]
        == "2026-01-15"
    )

    combined = ok(
        owner_client.post(
            "/api/subscriptions/billing-run",
            json={"through": "2026-03-31", "dry_run": True, "combine": True},
        )
    )
    assert len(combined["invoices"]) == 2  # ACME's two are due on the same day

    run = ok(
        owner_client.post(
            "/api/subscriptions/billing-run", json={"through": "2026-03-31", "combine": True}
        )
    )
    assert run["subscriptions_billed"] == 3
    totals = {i["party_name"]: i["total"] for i in run["invoices"]}
    assert totals == {"ACME Inc": "230.0000", "BOB Inc": "360.0000"}
    acme_draft = next(i for i in run["invoices"] if i["party_id"] == acme["id"])
    assert acme_draft["lines"] == [
        "Web Hosting - acme.example (2026-01-01 to 2026-12-31)",
        "Domain - acme.example (2026-01-01 to 2026-12-31)",
        "Web Hosting - acme.shop (2026-01-01 to 2026-12-31)",
    ]
    lines = ok(owner_client.get(f"/api/invoices/{acme_draft['id']}"))["lines"]
    assert all(line["subscription_id"] for line in lines)
    assert (
        ok(owner_client.get(f"/api/subscriptions/{monthly['id']}"))["next_bill_date"]
        == "2026-04-15"
    )

    again = ok(owner_client.post("/api/subscriptions/billing-run", json={"through": "2026-03-31"}))
    assert again["lines_created"] == 0  # nothing due twice

    billed = owner_client.delete(f"/api/subscriptions/{monthly['id']}")
    assert billed.status_code == 409
    assert ok(owner_client.get(f"/api/subscriptions/{monthly['id']}"))["billed"] is True


def test_ending_subscription_is_cancelled_after_its_last_period(
    owner_client: TestClient, hosting: dict[str, Any]
) -> None:
    acme = contact(owner_client, "ACME")
    sub = subscribe(owner_client, acme["id"], [{"catalog_item_id": hosting["id"]}],
                    billing_interval_months=1, end_date="2026-02-28", auto_renew=False)  # fmt: skip
    run = ok(owner_client.post("/api/subscriptions/billing-run", json={"through": "2026-12-31"}))
    assert run["lines_created"] == 2  # January and February only
    assert ok(owner_client.get(f"/api/subscriptions/{sub['id']}"))["status"] == "cancelled"


# -- vendor subscriptions -------------------------------------------------------------------------


def expense_account(client: TestClient) -> dict[str, Any]:
    return ok(client.post("/api/accounts", json={"code": "4010", "name": "Hosting costs"}), 201)


def test_vendor_subscription_payments(owner_client: TestClient) -> None:
    host = contact(owner_client, "HOST", ["vendor"])
    account = expense_account(owner_client)
    server = ok(
        owner_client.post(
            "/api/vendor-subscriptions",
            json={"party_id": host["id"], "name": "VPS", "service_identifier": "host-01",
                  "amount": "60", "interval_months": 3, "next_due_date": "2026-01-31",
                  "expense_account_id": account["id"], "autopay": True},
        ),
        201,
    )  # fmt: skip
    assert (server["monthly_amount"], server["vendor_name"]) == ("20.0000", "HOST Inc")
    assert (server["payments"], server["last_paid_date"]) == (0, None)

    paid = ok(
        owner_client.post(
            f"/api/vendor-subscriptions/{server['id']}/payments",
            json={"paid_date": "2026-01-30", "reference": "INV-7"},
        ),
        201,
    )
    assert paid["subscription"]["next_due_date"] == "2026-04-30"
    assert (paid["subscription"]["payments"], paid["subscription"]["last_paid_date"]) == (
        1, "2026-01-30"
    )  # fmt: skip
    expense = ok(owner_client.get(f"/api/expenses/{paid['expense_id']}"))
    assert (expense["vendor_name"], expense["total"], expense["reference"]) == (
        "HOST Inc", "60.0000", "INV-7"
    )  # fmt: skip
    assert expense["lines"][0]["account_code"] == "4010"
    assert expense["vendor_subscription_id"] == server["id"]

    other = ok(
        owner_client.post(
            f"/api/vendor-subscriptions/{server['id']}/payments",
            json={"paid_date": "2026-04-29", "amount": "66.50"},
        ),
        201,
    )
    assert ok(owner_client.get(f"/api/expenses/{other['expense_id']}"))["total"] == "66.5000"

    due = ok(owner_client.get("/api/vendor-subscriptions", params={"due_through": "2026-07-31"}))
    assert [s["name"] for s in due["items"]] == ["VPS"]
    assert owner_client.delete(f"/api/vendor-subscriptions/{server['id']}").status_code == 409


def test_payment_needs_an_account(owner_client: TestClient) -> None:
    host = contact(owner_client, "HOST", ["vendor"])
    sub = ok(
        owner_client.post(
            "/api/vendor-subscriptions",
            json={"party_id": host["id"], "name": "Phone", "amount": "40", "interval_months": 1},
        ),
        201,
    )
    paid = owner_client.post(
        f"/api/vendor-subscriptions/{sub['id']}/payments", json={"paid_date": "2026-01-30"}
    )
    assert paid.status_code == 409
    assert owner_client.delete(f"/api/vendor-subscriptions/{sub['id']}").status_code == 204


def test_client_lines_use_vendor_subscriptions(
    owner_client: TestClient, hosting: dict[str, Any]
) -> None:
    host = contact(owner_client, "HOST", ["vendor"])
    server = ok(
        owner_client.post(
            "/api/vendor-subscriptions",
            json={"party_id": host["id"], "name": "Server", "amount": "100",
                  "interval_months": 1},
        ),
        201,
    )  # fmt: skip
    acme = contact(owner_client, "ACME")
    bob = contact(owner_client, "BOB")
    uses = [{"catalog_item_id": hosting["id"], "uses": [server["id"]]}]
    acme_sub = subscribe(owner_client, acme["id"], uses, service_identifier="acme.example")
    subscribe(owner_client, bob["id"], uses, service_identifier="bob.example")

    acme_sub = ok(owner_client.get(f"/api/subscriptions/{acme_sub['id']}"))
    use = acme_sub["lines"][0]["uses"][0]
    assert (use["name"], use["shared_by"], use["monthly_share"]) == ("Server", 2, "50.0000")
    assert (acme_sub["monthly_revenue"], acme_sub["monthly_cost"]) == ("10.0000", "50.0000")

    used_by = ok(owner_client.get(f"/api/vendor-subscriptions/{server['id']}"))["used_by"]
    assert [u["service_identifier"] for u in used_by] == ["acme.example", "bob.example"]

    # A cancelled client subscription no longer shares the cost.
    owner_client.patch(f"/api/subscriptions/{acme_sub['id']}", json={"status": "cancelled"})
    bob_sub = ok(owner_client.get("/api/subscriptions", params={"party_id": bob["id"]}))["items"][0]
    assert bob_sub["monthly_cost"] == "100.0000"

    # Deleting the vendor subscription removes the links, not the client subscriptions.
    assert owner_client.delete(f"/api/vendor-subscriptions/{server['id']}").status_code == 204
    assert ok(owner_client.get(f"/api/subscriptions/{acme_sub['id']}"))["lines"][0]["uses"] == []


# -- packages -------------------------------------------------------------------------------------


def test_packages(
    owner_client: TestClient, hosting: dict[str, Any], domain: dict[str, Any]
) -> None:
    package = ok(
        owner_client.post(
            "/api/packages",
            json={"name": "Hosting + domain",
                  "items": [{"catalog_item_id": hosting["id"]},
                            {"catalog_item_id": domain["id"], "price": "15"}]},
        ),
        201,
    )  # fmt: skip
    assert [(i["item_name"], i["unit_price"]) for i in package["items"]] == [
        ("Web Hosting", "120.0000"),
        ("Domain", "15.0000"),
    ]
    assert package["total"] == "135.0000"
    assert [p["name"] for p in ok_list(owner_client.get("/api/packages"))] == ["Hosting + domain"]

    renamed = ok(
        owner_client.patch(
            f"/api/packages/{package['id']}",
            json={"name": "Starter", "items": [{"catalog_item_id": hosting["id"]}]},
        )
    )
    assert (renamed["name"], len(renamed["items"])) == ("Starter", 1)
    in_use = owner_client.delete(f"/api/catalog/{hosting['id']}")
    assert in_use.status_code == 409  # the package uses it
    assert owner_client.delete(f"/api/packages/{package['id']}").status_code == 204
    assert ok_list(owner_client.get("/api/packages")) == []
