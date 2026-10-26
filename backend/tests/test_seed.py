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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saumgm.enums import JurisdictionLevel
from saumgm.models import NumberSequence, TaxCategory, TaxJurisdiction
from saumgm.seed import OrganizationSetup, create_organization


def test_create_organization_seeds_reference_data(db_session: Session) -> None:
    org = create_organization(
        db_session,
        OrganizationSetup(legal_name="Example LLC", display_name="Example", party_number_next=7),
    )

    jurisdictions = list(
        db_session.scalars(select(TaxJurisdiction).where(TaxJurisdiction.organization_id == org.id))
    )
    by_code = {j.code: j for j in jurisdictions}
    assert {j.code for j in jurisdictions if j.level == JurisdictionLevel.COUNTRY} == {"US", "CA"}
    assert by_code["US-NY"].parent_id == by_code["US"].id
    assert by_code["CA-ON"].parent_id == by_code["CA"].id
    assert len(jurisdictions) == 2 + 52 + 13  # countries, US states + DC + PR, CA provinces

    party_seq = db_session.scalars(
        select(NumberSequence).where(
            NumberSequence.organization_id == org.id, NumberSequence.name == "party"
        )
    ).one()
    assert party_seq.format(party_seq.next_value) == "00000007"

    categories = db_session.scalar(
        select(func.count()).select_from(TaxCategory).where(TaxCategory.organization_id == org.id)
    )
    assert categories == 5
