from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from saumgm.models import Organization, Party, TaxExemption, TaxRate
from saumgm.services.tax_engine import TableTaxEngine, TaxableLine
from tests.tax_setup import NewYork, setup_new_york

D = Decimal
ON = date(2026, 6, 1)


@pytest.fixture
def ny(db_session: Session, org: Organization) -> NewYork:
    return setup_new_york(db_session, org)


@pytest.fixture
def client_party(db_session: Session, org: Organization) -> Party:
    party = Party(organization_id=org.id, party_no="1", short_code="C", name="Client")
    db_session.add(party)
    db_session.flush()
    return party


def calc(
    session: Session,
    org: Organization,
    jurisdiction_id: int,
    lines: list[TaxableLine],
    party_id: int | None = None,
    on_date: date = ON,
) -> list[tuple[str, Decimal, Decimal]]:
    results = TableTaxEngine().calculate(
        session,
        organization_id=org.id,
        currency="USD",
        jurisdiction_id=jurisdiction_id,
        on_date=on_date,
        party_id=party_id,
        lines=lines,
    )
    return [(r.name, r.taxable_base, r.amount) for r in results]


def test_state_and_county_rates_apply_below_a_registration(
    db_session: Session, org: Organization, ny: NewYork
) -> None:
    lines = [TaxableLine(D("100.00"), ny.goods.id)]
    assert calc(db_session, org, ny.city.id, lines) == [
        ("New York State", D("100.00"), D("4.00")),
        ("Cattaraugus County", D("100.00"), D("4.00")),
    ]


def test_no_registration_no_tax(db_session: Session, org: Organization, ny: NewYork) -> None:
    assert calc(db_session, org, ny.texas.id, [TaxableLine(D("100"), None)]) == []


def test_taxability_rules_by_category(db_session: Session, org: Organization, ny: NewYork) -> None:
    lines = [
        TaxableLine(D("60.00"), ny.goods.id),
        TaxableLine(D("40.00"), ny.digital.id),  # not taxable in NY (rule on the state)
        TaxableLine(D("25.00"), ny.exempt.id),  # never taxable (seeded rule on the country)
        TaxableLine(D("10.00"), None),  # no category: taxable
    ]
    assert calc(db_session, org, ny.county.id, lines) == [
        ("New York State", D("70.00"), D("2.80")),
        ("Cattaraugus County", D("70.00"), D("2.80")),
    ]


def test_exemptions(
    db_session: Session, org: Organization, ny: NewYork, client_party: Party
) -> None:
    lines = [TaxableLine(D("100"), ny.goods.id)]
    county_only = TaxExemption(
        party_id=client_party.id, jurisdiction_id=ny.county.id, certificate_type="Local"
    )
    db_session.add(county_only)
    db_session.flush()
    assert calc(db_session, org, ny.city.id, lines, client_party.id) == [
        ("New York State", D("100"), D("4.00"))
    ]

    db_session.add(TaxExemption(party_id=client_party.id, certificate_type="Native American"))
    db_session.flush()
    assert calc(db_session, org, ny.city.id, lines, client_party.id) == []


def test_expired_exemption_does_not_apply(
    db_session: Session, org: Organization, ny: NewYork, client_party: Party
) -> None:
    db_session.add(
        TaxExemption(party_id=client_party.id, certificate_type="Resale", valid_to=date(2020, 1, 1))
    )
    db_session.flush()
    taxes = calc(db_session, org, ny.state.id, [TaxableLine(D("10"), None)], client_party.id)
    assert taxes == [("New York State", D("10"), D("0.40"))]


def test_rates_follow_their_effective_dates(
    db_session: Session, org: Organization, ny: NewYork
) -> None:
    [old] = ny.state.rates
    old.effective_to = date(2025, 12, 31)
    db_session.add(
        TaxRate(
            jurisdiction_id=ny.state.id,
            name="New York State",
            rate=D("0.045"),
            effective_from=date(2026, 1, 1),
        )
    )
    db_session.flush()
    line = [TaxableLine(D("100"), None)]
    assert calc(db_session, org, ny.state.id, line, on_date=date(2025, 6, 1))[0][2] == D("4.00")
    assert calc(db_session, org, ny.state.id, line, on_date=date(2026, 6, 1))[0][2] == D("4.50")


def test_rounded_once_per_rate(db_session: Session, org: Organization, ny: NewYork) -> None:
    lines = [TaxableLine(D("33.33"), None), TaxableLine(D("33.33"), None)]
    [(_, base, amount)] = calc(db_session, org, ny.state.id, lines)
    assert (base, amount) == (D("66.66"), D("2.67"))  # 2.6664, not 1.33 + 1.33
