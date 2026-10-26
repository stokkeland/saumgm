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
from tests.api_helpers import contact, ok


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)


@pytest.fixture
def hosting(owner_client: TestClient) -> dict[str, Any]:
    return ok(
        owner_client.post(
            "/api/catalog",
            json={"name": "Web Hosting", "item_type": "subscription", "price": "120",
                  "billing_interval_months": 12, "unit": "Year"},
        ),
        201,
    )  # fmt: skip


def subscribe(client: TestClient, party_id: int, item_id: int, **extra: Any) -> dict[str, Any]:
    return ok(
        client.post(
            "/api/subscriptions",
            json={"party_id": party_id, "catalog_item_id": item_id, "start_date": "2026-01-01"}
            | extra,
        ),
        201,
    )


def test_subscription_defaults_from_the_catalog(
    owner_client: TestClient, hosting: dict[str, Any]
) -> None:
    acme = contact(owner_client, "ACME")
    sub = subscribe(owner_client, acme["id"], hosting["id"], service_identifier="acme.example")
    assert sub["billing_interval_months"] == 12
    assert sub["next_bill_date"] == "2026-01-01"
    assert sub["unit_price"] == "120.0000"

    due = ok(owner_client.get("/api/subscriptions", params={"due_through": "2026-01-31"}))
    assert [s["service_identifier"] for s in due["items"]] == ["acme.example"]


def test_billing_run(owner_client: TestClient, hosting: dict[str, Any]) -> None:
    acme = contact(owner_client, "ACME")
    bob = contact(owner_client, "BOB")
    subscribe(owner_client, acme["id"], hosting["id"], service_identifier="acme.example")
    subscribe(owner_client, acme["id"], hosting["id"], service_identifier="acme.shop",
              price_override="90")  # fmt: skip
    monthly = subscribe(owner_client, bob["id"], hosting["id"], service_identifier="bob.example",
                        billing_interval_months=1, start_date="2026-01-15")  # fmt: skip

    preview = ok(
        owner_client.post(
            "/api/subscriptions/billing-run", json={"through": "2026-03-31", "dry_run": True}
        )
    )
    assert preview["dry_run"] and preview["lines_created"] == 5  # 2 annual + 3 monthly (catch-up)
    assert ok(owner_client.get("/api/invoices"))["total"] == 0  # nothing saved
    assert (
        ok(owner_client.get(f"/api/subscriptions/{monthly['id']}"))["next_bill_date"]
        == "2026-01-15"
    )

    run = ok(owner_client.post("/api/subscriptions/billing-run", json={"through": "2026-03-31"}))
    assert run["subscriptions_billed"] == 3
    totals = {i["party_name"]: i["total"] for i in run["invoices"]}
    assert totals == {"ACME Inc": "210.0000", "BOB Inc": "360.0000"}

    drafts = ok(owner_client.get("/api/invoices", params={"status": "draft"}))["items"]
    acme_draft = ok(
        owner_client.get(
            f"/api/invoices/{next(d['id'] for d in drafts if d['party_id'] == acme['id'])}"
        )
    )
    assert [line["description"] for line in acme_draft["lines"]] == [
        "Web Hosting - acme.example (2026-01-01 to 2026-12-31)",
        "Web Hosting - acme.shop (2026-01-01 to 2026-12-31)",
    ]
    assert (
        ok(owner_client.get(f"/api/subscriptions/{monthly['id']}"))["next_bill_date"]
        == "2026-04-15"
    )

    again = ok(owner_client.post("/api/subscriptions/billing-run", json={"through": "2026-03-31"}))
    assert again["lines_created"] == 0  # nothing due twice

    billed = owner_client.delete(f"/api/subscriptions/{monthly['id']}")
    assert billed.status_code == 409


def test_ending_subscription_is_cancelled_after_its_last_period(
    owner_client: TestClient, hosting: dict[str, Any]
) -> None:
    acme = contact(owner_client, "ACME")
    sub = subscribe(owner_client, acme["id"], hosting["id"], billing_interval_months=1,
                    end_date="2026-02-28", auto_renew=False)  # fmt: skip
    run = ok(owner_client.post("/api/subscriptions/billing-run", json={"through": "2026-12-31"}))
    assert run["lines_created"] == 2  # January and February only
    assert ok(owner_client.get(f"/api/subscriptions/{sub['id']}"))["status"] == "cancelled"
