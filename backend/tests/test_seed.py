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
