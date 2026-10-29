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

from decimal import Decimal

from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from saumgm.enums import AccountType, ItemType
from saumgm.models import Account, CatalogItem, Party
from saumgm.seed import OrganizationSetup, create_organization
from tests.support import alembic_config

BEFORE_SUBSCRIPTION_LINES = "384ebe93845b"


def test_migrations_upgrade_and_downgrade(test_engine: Engine, test_database_url: str) -> None:
    config = alembic_config(test_database_url)
    command.upgrade(config, "head")
    assert "alembic_version" in inspect(test_engine).get_table_names()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_models_match_migrations(test_engine: Engine, test_database_url: str) -> None:
    """Fails if a model was changed without generating a migration for it."""
    command.upgrade(alembic_config(test_database_url), "head")
    command.check(alembic_config(test_database_url))


def test_subscriptions_are_converted(test_engine: Engine, test_database_url: str) -> None:
    """1.0 subscriptions (one item each, vendor details on the row) become a header with one
    line, plus a linked vendor subscription where there was a vendor. Commits for real, so it
    ends by rebuilding the empty schema."""
    config = alembic_config(test_database_url)
    command.upgrade(config, "head")
    with Session(test_engine) as session:
        org = create_organization(
            session, OrganizationSetup(legal_name="Old Subs LLC", display_name="Old Subs")
        )
        client = Party(organization_id=org.id, party_no="1", short_code="ACME", name="ACME")
        vendor = Party(organization_id=org.id, party_no="2", short_code="HOST", name="Host")
        account = Account(organization_id=org.id, code="4010", name="Hosting costs",
                          account_type=AccountType.COGS)  # fmt: skip
        session.add_all([client, vendor, account])
        session.flush()
        item = CatalogItem(organization_id=org.id, name="Hosting", item_type=ItemType.SUBSCRIPTION,
                           price=Decimal(10), cogs_account_id=account.id)  # fmt: skip
        session.add(item)
        session.commit()
        ids = {"org": org.id, "client": client.id, "vendor": vendor.id, "item": item.id}

    command.downgrade(config, BEFORE_SUBSCRIPTION_LINES)
    insert = text(
        "INSERT INTO subscription (organization_id, party_id, catalog_item_id, quantity,"
        " price_override, service_identifier, billing_interval_months, start_date, auto_renew,"
        " status, vendor_party_id, vendor_renewal_date, unit_cost, notes)"
        " VALUES (:org, :client, :item, 2, 9, :identifier, 12, '2026-01-01', 1, 'active',"
        " :vendor, :renewal, :cost, NULL)"
    )
    with test_engine.begin() as conn:
        conn.execute(insert, ids | {"identifier": "acme.example", "renewal": "2026-12-15",
                                    "cost": 4})  # fmt: skip
        conn.execute(insert, ids | {"identifier": "acme.shop", "vendor": None, "renewal": None,
                                    "cost": 3})  # fmt: skip

    command.upgrade(config, "head")
    with test_engine.connect() as conn:
        lines = conn.execute(
            text(
                "SELECT s.service_identifier, l.description, l.quantity, l.price_override, s.notes"
                " FROM subscription s JOIN subscription_line l ON l.subscription_id = s.id"
                " ORDER BY s.id"
            )
        ).all()
        assert [tuple(row) for row in lines] == [
            ("acme.example", "Hosting", Decimal(2), Decimal(9), None),
            ("acme.shop", "Hosting", Decimal(2), Decimal(9), "Before 2.0: unit cost 3.0000"),
        ]
        vendors = conn.execute(
            text(
                "SELECT v.party_id, v.name, v.service_identifier, v.amount, v.interval_months,"
                " v.next_due_date, v.expense_account_id IS NOT NULL"
                " FROM vendor_subscription v JOIN subscription_use u"
                " ON u.vendor_subscription_id = v.id"
            )
        ).all()
        assert [tuple(row)[:5] for row in vendors] == [
            (ids["vendor"], "Hosting", "acme.example", Decimal(8), 12)
        ]
        assert str(vendors[0][5]) == "2026-12-15" and vendors[0][6]

    command.downgrade(config, BEFORE_SUBSCRIPTION_LINES)
    with test_engine.connect() as conn:
        restored = conn.execute(
            text(
                "SELECT catalog_item_id, quantity, vendor_party_id, unit_cost FROM subscription"
                " ORDER BY id"
            )
        ).all()
        assert [tuple(row) for row in restored] == [
            (ids["item"], Decimal(2), ids["vendor"], Decimal(4)),
            (ids["item"], Decimal(2), None, None),
        ]

    command.downgrade(config, "base")
    command.upgrade(config, "head")
