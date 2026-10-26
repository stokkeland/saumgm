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

import csv
import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from saumgm.models import Organization
from saumgm.services.reports import bucket
from tests.api_helpers import contact, issued_invoice, ok
from tests.tax_setup import NewYork, setup_new_york

QUARTER = {"date_from": "2026-01-01", "date_to": "2026-03-31"}


@pytest.fixture
def books(owner_client: TestClient, db_session: Session, org: Organization) -> dict[str, Any]:
    """January: a taxed NY sale (200 + 8 tax) and an untaxed one (100). February: half the NY
    invoice is paid. March: the rest is written off; expenses of 50 (cost of goods) and 20."""
    ny: NewYork = setup_new_york(db_session, org)
    olean = ok(
        owner_client.post(
            "/api/contacts",
            json={"short_code": "OLEAN", "name": "Olean Shop", "roles": ["client"],
                  "addresses": [{"address_type": "billing", "is_default": True, "line1": "1 Main",
                                 "city": "Olean", "region": "NY", "country_code": "US"}]},
        ),
        201,
    )  # fmt: skip
    router = ok(
        owner_client.post(
            "/api/catalog",
            json={"name": "Router", "item_type": "goods", "price": "200",
                  "tax_category_id": ny.goods.id},
        ),
        201,
    )  # fmt: skip
    draft = ok(
        owner_client.post(
            "/api/invoices",
            json={"party_id": olean["id"], "lines": [{"catalog_item_id": router["id"]}]},
        ),
        201,
    )
    taxed = ok(
        owner_client.post(f"/api/invoices/{draft['id']}/issue", json={"issue_date": "2026-01-10"})
    )
    assert taxed["total"] == "208.0000"
    acme = contact(owner_client, "ACME")
    issued_invoice(owner_client, acme["id"], "100", "2026-01-20")

    ok(
        owner_client.post(
            "/api/payments",
            json={"party_id": olean["id"], "received_date": "2026-02-10", "amount": "104",
                  "allocations": [{"invoice_id": taxed["id"], "amount": "104"}]},
        ),
        201,
    )  # fmt: skip
    ok(
        owner_client.post(
            f"/api/invoices/{taxed['id']}/write-off",
            json={"reason": "Closed", "write_off_date": "2026-03-15"},
        )
    )

    def account(code: str, account_type: str) -> int:
        body = {"code": code, "name": f"Account {code}", "account_type": account_type}
        return int(ok(owner_client.post("/api/accounts", json=body), 201)["id"])

    cogs, office = account("5000", "cogs"), account("6000", "expense")
    ok(
        owner_client.post(
            "/api/expenses",
            json={"expense_date": "2026-03-01",
                  "lines": [{"account_id": cogs, "amount": "50"},
                            {"account_id": office, "amount": "20"}]},
        ),
        201,
    )  # fmt: skip
    return {"olean": olean, "acme": acme, "taxed": taxed}


def test_sales_by_month_and_client(owner_client: TestClient, books: dict[str, Any]) -> None:
    by_month = ok(owner_client.get("/api/reports/sales", params=QUARTER))
    assert [(r["key"], r["documents"], r["sales"], r["tax"]) for r in by_month["rows"]] == [
        ("2026-01", 2, "300.0000", "8.0000")
    ]
    assert by_month["total"] == "308.0000"  # the write-off does not undo the sale

    by_client = ok(owner_client.get("/api/reports/sales", params=QUARTER | {"group": "client"}))
    assert [(r["label"], r["total"]) for r in by_client["rows"]] == [
        ("ACME Inc", "100.0000"),
        ("Olean Shop", "208.0000"),
    ]


def test_sales_tax_accrual_and_cash(owner_client: TestClient, books: dict[str, Any]) -> None:
    accrual = ok(owner_client.get("/api/reports/sales-tax", params=QUARTER | {"basis": "accrual"}))
    assert (accrual["gross_sales"], accrual["taxable_sales"], accrual["non_taxable_sales"]) == (
        "300.0000",
        "200.0000",
        "100.0000",
    )
    assert [(t["name"], t["taxable"], t["tax"]) for t in accrual["lines"]] == [
        ("New York State", "200.0000", "8.0000")
    ]
    # the unpaid half (104) is written off: its 4.00 of tax comes back as a credit
    assert (accrual["tax_collected"], accrual["bad_debt_tax_credit"], accrual["net_tax"]) == (
        "8.0000",
        "4.0000",
        "4.0000",
    )

    cash = ok(owner_client.get("/api/reports/sales-tax", params=QUARTER | {"basis": "cash"}))
    assert (cash["gross_sales"], cash["taxable_sales"], cash["tax_collected"]) == (
        "100.0000",
        "100.0000",
        "4.0000",
    )

    response = owner_client.get("/api/reports/sales-tax.csv", params=QUARTER | {"basis": "accrual"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == ["jurisdiction", "tax", "rate", "taxable", "tax_amount"]
    assert ["Net tax", "", "", "", "4.00"] in rows


def test_expenses_and_profit_loss(owner_client: TestClient, books: dict[str, Any]) -> None:
    expenses = ok(owner_client.get("/api/reports/expenses", params=QUARTER))
    assert [(r["key"], r["account_type"], r["total"]) for r in expenses["rows"]] == [
        ("5000", "cogs", "50.0000"),
        ("6000", "expense", "20.0000"),
    ]
    assert expenses["total"] == "70.0000"

    pl = ok(owner_client.get("/api/reports/profit-loss", params=QUARTER))
    assert (pl["sales"], pl["cost_of_goods_total"], pl["gross_profit"]) == (
        "300.0000",
        "50.0000",
        "250.0000",
    )
    # bad debt is the written-off 104 less its 4 of tax
    assert (pl["bad_debts"], pl["expenses_total"], pl["net_profit"]) == (
        "100.0000",
        "120.0000",
        "130.0000",
    )
    csv_rows = owner_client.get("/api/reports/profit-loss.csv", params=QUARTER).text
    assert "Net profit,,130.00" in csv_rows


def test_aging(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    issued_invoice(owner_client, acme["id"], "40", "2020-01-01")
    issued_invoice(owner_client, acme["id"], "2", "2020-02-01")
    aging = ok(owner_client.get("/api/reports/aging"))
    assert [(r["party_name"], r["invoices"], r["days_over_90"]) for r in aging["rows"]] == [
        ("ACME Inc", 2, "42.0000")
    ]
    assert aging["totals"]["total"] == "42.0000"


def test_aging_buckets() -> None:
    assert [bucket(d) for d in (-5, 0, 1, 30, 31, 61, 91)] == [
        "current", "current", "days_1_30", "days_1_30", "days_31_60", "days_61_90",
        "days_over_90",
    ]  # fmt: skip
