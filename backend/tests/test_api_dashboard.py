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

from fastapi.testclient import TestClient

from tests.api_helpers import contact, issued_invoice, ok


def test_dashboard_numbers(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    this_year = date.today().replace(month=1, day=2).isoformat()
    issued_invoice(owner_client, acme["id"], "100", this_year)  # overdue by now (net 30)
    recent = issued_invoice(owner_client, acme["id"], "50", date.today().isoformat())
    owner_client.post(
        "/api/payments",
        json={"party_id": acme["id"], "received_date": date.today().isoformat(), "amount": "20",
              "allocations": [{"invoice_id": recent["id"], "amount": "20"}]},
    )  # fmt: skip
    hosting = ok(
        owner_client.post(
            "/api/catalog",
            json={"name": "Hosting", "item_type": "subscription", "price": "10",
                  "billing_interval_months": 12},
        ),
        201,
    )  # fmt: skip
    owner_client.post(
        "/api/subscriptions",
        json={"party_id": acme["id"], "lines": [{"catalog_item_id": hosting["id"]}],
              "start_date": (date.today() + timedelta(days=10)).isoformat(),
              "service_identifier": "acme.example"},
    )  # fmt: skip

    board = ok(owner_client.get("/api/dashboard"))
    assert (board["receivable"], board["open_invoices"]) == ("130.0000", 2)
    if date.today() > date(date.today().year, 2, 1):
        assert (board["overdue"], board["overdue_invoices"]) == ("100.0000", 1)
    assert (board["undeposited"], board["undeposited_payments"]) == ("20.0000", 1)
    assert board["sales_this_year"] == "150.0000"
    assert [(r["service_identifier"], r["summary"]) for r in board["renewals"]] == [
        ("acme.example", "Hosting")
    ]
