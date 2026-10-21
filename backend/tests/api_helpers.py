"""Small builders for API tests."""

from typing import Any

from fastapi.testclient import TestClient


def ok(response: Any, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    return body


def contact(client: TestClient, code: str, roles: list[str] | None = None) -> dict[str, Any]:
    return ok(
        client.post(
            "/api/contacts",
            json={"short_code": code, "name": f"{code} Inc", "roles": roles or ["client"]},
        ),
        201,
    )


def issued_invoice(
    client: TestClient, party_id: int, amount: str, issue_date: str = "2026-01-01"
) -> dict[str, Any]:
    draft = ok(
        client.post(
            "/api/invoices",
            json={"party_id": party_id, "lines": [{"description": "Work", "unit_price": amount}]},
        ),
        201,
    )
    return ok(client.post(f"/api/invoices/{draft['id']}/issue", json={"issue_date": issue_date}))
