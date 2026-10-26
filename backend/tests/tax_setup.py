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

"""A New York sales-tax configuration used by the invoice and tax tests (rates are examples)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.enums import JurisdictionLevel
from saumgm.models import (
    Organization,
    TaxabilityRule,
    TaxCategory,
    TaxJurisdiction,
    TaxRate,
    TaxRegistration,
)


@dataclass
class NewYork:
    state: TaxJurisdiction
    county: TaxJurisdiction
    city: TaxJurisdiction
    texas: TaxJurisdiction
    goods: TaxCategory
    digital: TaxCategory
    exempt: TaxCategory


def setup_new_york(session: Session, org: Organization) -> NewYork:
    def jurisdiction(code: str) -> TaxJurisdiction:
        return session.scalars(
            select(TaxJurisdiction).where(
                TaxJurisdiction.organization_id == org.id, TaxJurisdiction.code == code
            )
        ).one()

    def category(code: str) -> TaxCategory:
        return session.scalars(
            select(TaxCategory).where(
                TaxCategory.organization_id == org.id, TaxCategory.code == code
            )
        ).one()

    state = jurisdiction("US-NY")
    county = TaxJurisdiction(
        organization_id=org.id,
        parent_id=state.id,
        level=JurisdictionLevel.COUNTY,
        code="US-NY-CATTARAUGUS",
        name="Cattaraugus County",
    )
    session.add(county)
    session.flush()
    city = TaxJurisdiction(
        organization_id=org.id,
        parent_id=county.id,
        level=JurisdictionLevel.CITY,
        code="US-NY-SALAMANCA",
        name="Salamanca",
    )
    session.add(city)
    session.add_all(
        [
            TaxRate(
                jurisdiction_id=state.id,
                name="New York State",
                rate=Decimal("0.04"),
                effective_from=date(2000, 1, 1),
            ),
            TaxRate(
                jurisdiction_id=county.id,
                name="Cattaraugus County",
                rate=Decimal("0.04"),
                effective_from=date(2000, 1, 1),
            ),
            TaxRegistration(
                organization_id=org.id, jurisdiction_id=state.id, effective_from=date(2004, 1, 1)
            ),
        ]
    )
    digital = category("digital")
    session.add(
        TaxabilityRule(jurisdiction_id=state.id, tax_category_id=digital.id, is_taxable=False)
    )
    session.flush()
    return NewYork(
        state=state,
        county=county,
        city=city,
        texas=jurisdiction("US-TX"),
        goods=category("goods"),
        digital=digital,
        exempt=category("exempt"),
    )
