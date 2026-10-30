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

from tests.api_helpers import contact, ok, ok_list


@pytest.fixture
def category(owner_client: TestClient) -> dict[str, Any]:
    return ok(owner_client.post("/api/accounts", json={"code": "4130", "name": "Internet"}), 201)


def bank_account(client: TestClient, name: str = "Checking", **extra: Any) -> dict[str, Any]:
    body = {"name": name, "kind": "checking", "opening_date": "2026-01-01",
            "opening_balance": "1000"} | extra  # fmt: skip
    return ok(client.post("/api/bank-accounts", json=body), 201)


def entry(client: TestClient, bank_id: int, amount: str, day: str = "2026-01-10",
          **extra: Any) -> dict[str, Any]:  # fmt: skip
    return ok(
        client.post(
            f"/api/bank-accounts/{bank_id}/entries",
            json={"entry_date": day, "amount": amount} | extra,
        ),
        201,
    )


def register(client: TestClient, account_id: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = ok(client.get(f"/api/bank-accounts/{account_id}/entries"))[
        "items"
    ]
    return items


def account(client: TestClient, account_id: int) -> dict[str, Any]:
    return ok(client.get(f"/api/bank-accounts/{account_id}"))


def test_register_and_balances(owner_client: TestClient, category: dict[str, Any]) -> None:
    bank = contact(owner_client, "BANK", ["financial"])
    checking = bank_account(owner_client, party_id=bank["id"], number_last4="1234")
    assert (checking["bank_name"], checking["balance"]) == ("BANK Inc", "1000.0000")

    fee = entry(owner_client, checking["id"], "-12.50", payee="BANK", description="Monthly fee",
                account_id=category["id"])  # fmt: skip
    interest = entry(owner_client, checking["id"], "0.75", "2026-01-31", status="cleared")
    assert fee["account_name"] == "4130 Internet"
    assert [(e["id"], e["running_balance"]) for e in register(owner_client, checking["id"])] == [
        (interest["id"], "988.2500"),  # newest first
        (fee["id"], "987.5000"),
    ]
    now = account(owner_client, checking["id"])
    assert (now["balance"], now["cleared_balance"], now["uncleared_count"]) == (
        "988.2500", "1000.7500", 1,
    )  # fmt: skip

    early = owner_client.post(
        f"/api/bank-accounts/{checking['id']}/entries",
        json={"entry_date": "2025-12-31", "amount": "5"},
    )
    assert early.status_code == 409 and "starts on 2026-01-01" in early.text
    later_start = owner_client.patch(
        f"/api/bank-accounts/{checking['id']}", json={"opening_date": "2026-01-15"}
    )
    assert later_start.status_code == 409
    ok(owner_client.patch(f"/api/bank-accounts/{checking['id']}", json={"opening_balance": "900"}))
    assert account(owner_client, checking["id"])["balance"] == "888.2500"

    ok(owner_client.patch(f"/api/bank-entries/{fee['id']}", json={"status": "cleared"}))
    assert owner_client.delete(f"/api/bank-accounts/{checking['id']}").status_code == 409
    assert owner_client.delete(f"/api/bank-entries/{fee['id']}").status_code == 204


def test_deposit_and_expense_follow(owner_client: TestClient, category: dict[str, Any]) -> None:
    bank = contact(owner_client, "BANK", ["financial"])
    checking = bank_account(owner_client, party_id=bank["id"])
    deposit = ok(
        owner_client.post(
            "/api/deposits",
            json={"deposit_date": "2026-02-02", "bank_account_id": checking["id"],
                  "items": [{"amount": "20", "description": "Cash sale"}]},
        ),
        201,
    )  # fmt: skip
    assert deposit["bank_party_id"] == bank["id"]  # from the account
    [line] = register(owner_client, checking["id"])
    assert (line["kind"], line["amount"], line["deposit_id"]) == (
        "deposit",
        "20.0000",
        deposit["id"],
    )

    ok(
        owner_client.patch(
            f"/api/deposits/{deposit['id']}",
            json={"items": [{"amount": "25", "description": "Cash sale"}]},
        )
    )
    assert register(owner_client, checking["id"])[0]["amount"] == "25.0000"
    # The line cannot be changed on its own.
    assert (
        owner_client.patch(f"/api/bank-entries/{line['id']}", json={"amount": "1"}).status_code
        == 409
    )
    assert owner_client.delete(f"/api/bank-entries/{line['id']}").status_code == 409

    vendor = contact(owner_client, "ISP", ["vendor"])
    expense = ok(
        owner_client.post(
            "/api/expenses",
            json={"expense_date": "2026-02-05", "vendor_party_id": vendor["id"],
                  "reference": "4711", "paid_from_account_id": checking["id"],
                  "lines": [{"account_id": category["id"], "amount": "89.99"}]},
        ),
        201,
    )  # fmt: skip
    assert expense["paid_from_name"] == "Checking"
    paid = register(owner_client, checking["id"])[0]
    assert (paid["amount"], paid["payee"], paid["reference"], paid["account_name"]) == (
        "-89.9900", "ISP Inc", "4711", "4130 Internet",
    )  # fmt: skip
    assert paid["running_balance"] == "935.0100"

    ok(owner_client.patch(f"/api/expenses/{expense['id']}", json={"paid_from_account_id": None}))
    assert [e["kind"] for e in register(owner_client, checking["id"])] == ["deposit"]
    assert owner_client.delete(f"/api/deposits/{deposit['id']}").status_code == 204
    assert register(owner_client, checking["id"]) == []


def test_transfer_pays_the_card(owner_client: TestClient, category: dict[str, Any]) -> None:
    checking = bank_account(owner_client)
    card = bank_account(owner_client, "Amex", kind="credit_card", opening_balance="0")
    entry(owner_client, card["id"], "-300", payee="Office store", account_id=category["id"])
    assert account(owner_client, card["id"])["balance"] == "-300.0000"  # owed

    paid = ok(
        owner_client.post(
            "/api/bank-transfers",
            json={"from_account_id": checking["id"], "to_account_id": card["id"],
                  "entry_date": "2026-01-20", "amount": "300"},
        ),
        201,
    )  # fmt: skip
    assert (paid["out"]["amount"], paid["out"]["transfer_account_name"]) == ("-300.0000", "Amex")
    assert (paid["into"]["description"], paid["into"]["kind"]) == (
        "Transfer from Checking",
        "transfer",
    )
    assert account(owner_client, card["id"])["balance"] == "0.0000"

    ok(owner_client.patch(f"/api/bank-entries/{paid['into']['id']}", json={"amount": "250"}))
    assert account(owner_client, checking["id"])["balance"] == "750.0000"  # the other side follows
    same = owner_client.post(
        "/api/bank-transfers",
        json={"from_account_id": card["id"], "to_account_id": card["id"],
              "entry_date": "2026-01-20", "amount": "1"},
    )  # fmt: skip
    assert same.status_code == 409
    assert owner_client.delete(f"/api/bank-entries/{paid['out']['id']}").status_code == 204
    assert account(owner_client, checking["id"])["balance"] == "1000.0000"
    assert len(register(owner_client, card["id"])) == 1


def test_reconcile(owner_client: TestClient, category: dict[str, Any]) -> None:
    checking = bank_account(owner_client)
    fee = entry(owner_client, checking["id"], "-10", "2026-01-05")
    sale = entry(owner_client, checking["id"], "200", "2026-01-12")
    late = entry(owner_client, checking["id"], "-50", "2026-02-03")
    url = f"/api/bank-accounts/{checking['id']}/reconciliations"

    wrong = owner_client.post(url, json={"statement_date": "2026-01-31",
                                         "statement_balance": "1200",
                                         "entry_ids": [fee["id"], sale["id"]]})  # fmt: skip
    assert wrong.status_code == 409 and "difference of 10.00" in wrong.text
    after = owner_client.post(url, json={"statement_date": "2026-01-31", "statement_balance": "940",
                                         "entry_ids": [late["id"]]})  # fmt: skip
    assert after.status_code == 409 and "after the statement" in after.text

    rec = ok(owner_client.post(url, json={"statement_date": "2026-01-31",
                                          "statement_balance": "1190",
                                          "entry_ids": [fee["id"], sale["id"]]}), 201)  # fmt: skip
    assert (rec["entries"], rec["created_by"]) == (2, "Olivia Owner")
    now = account(owner_client, checking["id"])
    assert (now["last_reconciled_date"], now["reconciled_balance"]) == ("2026-01-31", "1190.0000")

    # Reconciled lines are locked, and so is where the register starts.
    assert (
        owner_client.patch(f"/api/bank-entries/{fee['id']}", json={"amount": "-11"}).status_code
        == 409
    )
    assert owner_client.delete(f"/api/bank-entries/{fee['id']}").status_code == 409
    assert owner_client.patch(f"/api/bank-accounts/{checking['id']}",
                              json={"opening_balance": "5"}).status_code == 409  # fmt: skip
    older = owner_client.post(url, json={"statement_date": "2026-01-15",
                                         "statement_balance": "1190",
                                         "entry_ids": []})  # fmt: skip
    assert older.status_code == 409

    # The next statement builds on the last one.
    ok(owner_client.post(url, json={"statement_date": "2026-02-28", "statement_balance": "1140",
                                    "entry_ids": [late["id"]]}), 201)  # fmt: skip
    [second, first] = ok_list(owner_client.get(url))
    assert owner_client.delete(f"/api/bank-reconciliations/{first['id']}").status_code == 409
    assert owner_client.delete(f"/api/bank-reconciliations/{second['id']}").status_code == 204
    assert {e["id"]: e["status"] for e in register(owner_client, checking["id"])}[
        late["id"]
    ] == "cleared"


def test_locked_deposit(owner_client: TestClient) -> None:
    checking = bank_account(owner_client)
    deposit = ok(
        owner_client.post(
            "/api/deposits",
            json={"deposit_date": "2026-02-02", "bank_account_id": checking["id"],
                  "items": [{"amount": "20"}]},
        ),
        201,
    )  # fmt: skip
    [line] = register(owner_client, checking["id"])
    ok(owner_client.post(f"/api/bank-accounts/{checking['id']}/reconciliations",
                         json={"statement_date": "2026-02-28", "statement_balance": "1020",
                               "entry_ids": [line["id"]]}), 201)  # fmt: skip
    changed = owner_client.patch(
        f"/api/deposits/{deposit['id']}", json={"items": [{"amount": "21"}]}
    )
    assert changed.status_code == 409 and "reconciled" in changed.text
    assert owner_client.delete(f"/api/deposits/{deposit['id']}").status_code == 409
    ok(owner_client.patch(f"/api/deposits/{deposit['id']}", json={"notes": "Counted twice"}))


def test_free_entry_becomes_an_expense(owner_client: TestClient, category: dict[str, Any]) -> None:
    card = bank_account(owner_client, "Visa", kind="credit_card", opening_balance="0")
    charge = entry(owner_client, card["id"], "-45", payee="Cloud host", account_id=category["id"])
    vendor = contact(owner_client, "HOST", ["vendor"])
    linked = ok(owner_client.post(f"/api/bank-entries/{charge['id']}/expense",
                                  json={"vendor_party_id": vendor["id"]}))  # fmt: skip
    assert linked["kind"] == "expense" and linked["expense_id"]
    expense = ok(owner_client.get(f"/api/expenses/{linked['expense_id']}"))
    assert (expense["total"], expense["paid_from_name"], expense["vendor_name"]) == (
        "45.0000", "Visa", "HOST Inc",
    )  # fmt: skip
    deposit_in = entry(owner_client, card["id"], "10")
    refused = owner_client.post(f"/api/bank-entries/{deposit_in['id']}/expense", json={})
    assert refused.status_code == 409


def test_vendor_subscription_paid_from(owner_client: TestClient, category: dict[str, Any]) -> None:
    card = bank_account(owner_client, "Visa", kind="credit_card", opening_balance="0")
    host = contact(owner_client, "HOST", ["vendor"])
    sub = ok(
        owner_client.post(
            "/api/vendor-subscriptions",
            json={"party_id": host["id"], "name": "VPS", "amount": "60", "interval_months": 1,
                  "next_due_date": "2026-01-31", "expense_account_id": category["id"],
                  "paid_from_account_id": card["id"], "autopay": True},
        ),
        201,
    )  # fmt: skip
    assert sub["paid_from_name"] == "Visa"
    url = f"/api/vendor-subscriptions/{sub['id']}/payments"
    ok(owner_client.post(url, json={"paid_date": "2026-01-31"}), 201)
    assert [(e["amount"], e["payee"]) for e in register(owner_client, card["id"])] == [
        ("-60.0000", "HOST Inc")
    ]
    ok(owner_client.post(url, json={"paid_date": "2026-02-28", "paid_from_account_id": None}), 201)
    assert len(register(owner_client, card["id"])) == 1  # paid some other way


def test_reminder_to_reconcile(owner_client: TestClient) -> None:
    today = date.fromisoformat(ok(owner_client.get("/api/reminders"))["today"])
    old = bank_account(owner_client, opening_date=(today - timedelta(days=60)).isoformat())
    bank_account(owner_client, "New", opening_date=today.isoformat())
    sections = {s["key"]: s for s in ok(owner_client.get("/api/reminders"))["sections"]}
    [item] = sections["banking"]["items"]
    assert (item["title"], item["note"], item["link"]) == (
        "Checking", "never reconciled", f"/banking/{old['id']}",
    )  # fmt: skip
    ok(owner_client.patch("/api/reminders/settings", json={"reconcile_days": 90}))
    assert "banking" not in {s["key"] for s in ok(owner_client.get("/api/reminders"))["sections"]}
