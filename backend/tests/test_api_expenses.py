from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from saumgm.models import Organization
from tests.api_helpers import contact, ok


@pytest.fixture
def accounts(owner_client: TestClient) -> dict[str, dict[str, Any]]:
    def account(code: str, name: str) -> dict[str, Any]:
        return ok(owner_client.post("/api/accounts", json={"code": code, "name": name}), 201)

    return {"internet": account("4130", "Internet"), "supplies": account("4260", "Office")}


def test_expense_defaults_to_the_business(
    owner_client: TestClient,
    accounts: dict[str, dict[str, Any]],
    db_session: Session,
    org: Organization,
) -> None:
    me = contact(owner_client, "ME", roles=["resource"])
    org.self_party_id = me["id"]
    db_session.flush()
    vendor = contact(owner_client, "HOST", roles=["vendor"])

    expense = ok(
        owner_client.post(
            "/api/expenses",
            json={"expense_date": "2026-03-01", "vendor_party_id": vendor["id"],
                  "reference": "INV-9", "description": "Hosting and paper",
                  "lines": [{"account_id": accounts["internet"]["id"], "amount": "120"},
                            {"account_id": accounts["supplies"]["id"], "amount": "15.50"}]},
        ),
        201,
    )  # fmt: skip
    assert expense["for_party_id"] == me["id"]  # defaults to the business itself
    assert expense["vendor_name"] == "HOST Inc"
    assert expense["total"] == "135.5000"
    assert [line["account_code"] for line in expense["lines"]] == ["4130", "4260"]
    assert expense["entered_date"] is not None


def test_expense_filters_and_updates(
    owner_client: TestClient, accounts: dict[str, dict[str, Any]]
) -> None:
    def add(day: str, account: str, amount: str) -> dict[str, Any]:
        return ok(
            owner_client.post(
                "/api/expenses",
                json={"expense_date": day, "lines": [{"account_id": accounts[account]["id"],
                      "amount": amount}]},
            ),
            201,
        )  # fmt: skip

    first = add("2026-01-05", "internet", "10")
    add("2026-02-05", "supplies", "20")

    def count(**params: Any) -> int:
        result: int = ok(owner_client.get("/api/expenses", params=params))["total"]
        return result

    assert count() == 2
    assert count(account_id=accounts["supplies"]["id"]) == 1
    assert count(date_from="2026-02-01") == 1

    updated = ok(
        owner_client.patch(
            f"/api/expenses/{first['id']}",
            json={"lines": [{"account_id": accounts["supplies"]["id"], "amount": "12"}]},
        )
    )
    assert (updated["total"], updated["lines"][0]["account_code"]) == ("12.0000", "4260")

    ok(owner_client.post(f"/api/expenses/{first['id']}/archive"))
    assert count() == 1
    assert (
        owner_client.patch(f"/api/expenses/{first['id']}", json={"reference": "x"}).status_code
        == 409
    )


def test_inactive_accounts_cannot_be_used(
    owner_client: TestClient, accounts: dict[str, dict[str, Any]]
) -> None:
    owner_client.patch(f"/api/accounts/{accounts['internet']['id']}", json={"is_active": False})
    response = owner_client.post(
        "/api/expenses",
        json={"expense_date": "2026-03-01", "lines": [{"account_id": accounts["internet"]["id"],
              "amount": "5"}]},
    )  # fmt: skip
    assert response.status_code == 409
