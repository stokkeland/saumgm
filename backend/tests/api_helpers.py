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


def ok_list(response: Any, status: int = 200) -> list[dict[str, Any]]:
    assert response.status_code == status, response.text
    body: list[dict[str, Any]] = response.json()
    return body
