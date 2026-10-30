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
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from saumgm.context import RequestContext, set_context
from saumgm.demo import DEMO_PASSWORD, DemoError, load_demo
from saumgm.enums import PartyRoleType
from saumgm.models import BankAccount, Base, Invoice, Party, PartyRole
from saumgm.services import banking
from saumgm.services import invoices as invoice_service
from tests.api_helpers import ok, ok_list

TODAY = date(2026, 10, 15)


@pytest.fixture
def demo(db_session: Session) -> Session:
    set_context(db_session, RequestContext(batch_id="demo"))
    load_demo(db_session, today=TODAY)
    db_session.flush()
    return db_session


def test_demo_fills_every_table(demo: Session) -> None:
    empty = [
        table
        for table in sorted(Base.metadata.tables)
        if table != "auth_session"  # created when someone signs in
        and not demo.execute(text(f"SELECT 1 FROM `{table}` LIMIT 1")).first()
    ]
    assert empty == []

    def count(role: PartyRoleType) -> int:
        return (
            demo.scalar(select(func.count()).select_from(PartyRole).where(PartyRole.role == role))
            or 0
        )

    assert (count(PartyRoleType.CLIENT), count(PartyRoleType.VENDOR)) == (10, 5)


def test_demo_tells_the_stories_it_promises(demo: Session) -> None:
    invoices = demo.scalars(select(Invoice)).all()
    statuses = {i.status.value for i in invoices}
    assert statuses == {"draft", "issued", "void"}
    assert any(i.kind.value == "credit_note" for i in invoices)
    assert any(i.revision_no > 0 for i in invoices)
    assert any(i.write_off_date for i in invoices)
    assert any(i.archived_at for i in invoices)
    infos = invoice_service.balances(
        demo, [i for i in invoices if i.status.value == "issued"], TODAY
    )
    overdue = [i for i in invoices if i.id in infos and infos[i.id].overdue]
    assert overdue, "some invoices should be overdue"
    # The church is tax exempt, so none of its invoices carry tax.
    church = demo.scalars(select(Party).where(Party.short_code == "STMARKS")).one()
    assert all(i.tax_total == Decimal(0) for i in invoices if i.party_id == church.id)
    # New York goods sales are taxed.
    assert sum(i.tax_total for i in invoices) > 0


def test_demo_users_can_sign_in_and_see_it(demo: Session, client: TestClient) -> None:
    response = client.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200, response.text
    dashboard = ok(client.get("/api/dashboard"))
    assert Decimal(dashboard["receivable"]) > 0
    assert ok_list(client.get("/api/documents/attention", params={"within_days": 60}))
    assert ok(client.get("/api/reports/aging"))["rows"]


def test_demo_needs_an_empty_database(demo: Session) -> None:
    with pytest.raises(DemoError):
        load_demo(demo, today=TODAY)


def test_demo_banking(demo: Session) -> None:
    accounts = {a.name: a for a in demo.scalars(select(BankAccount))}
    sums = banking.balances(demo, list(accounts.values()))
    card, checking = accounts["Business card"], accounts["Operating checking"]
    # The card is paid in full on the 25th: what is owed now is what was charged since.
    assert Decimal(0) > sums[card.id].balance > Decimal(-1000)
    assert sums[checking.id].balance > Decimal(0)
    last = banking.last_reconciliations(demo, [card.id, checking.id])
    assert (last[card.id].statement_date, last[checking.id].statement_date) == (
        date(2026, 9, 30),
        date(2026, 8, 31),
    )
