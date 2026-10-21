"""Sales tax setup: jurisdictions, rates, registrations and taxability rules."""

from datetime import date

from fastapi import APIRouter, status
from sqlalchemy import select

from saumgm.api.common import apply_changes, conflict, get_owned, not_found
from saumgm.api.deps import DbSession, Owner, Reader
from saumgm.models import (
    Organization,
    TaxabilityRule,
    TaxCategory,
    TaxFiling,
    TaxJurisdiction,
    TaxRate,
    TaxRegistration,
)
from saumgm.schemas.settings import (
    FilingIn,
    FilingOut,
    JurisdictionIn,
    JurisdictionOut,
    JurisdictionPatch,
    RegistrationIn,
    RegistrationOut,
    RegistrationPatch,
    TaxabilityRuleIn,
    TaxabilityRuleOut,
    TaxPeriod,
    TaxRateIn,
    TaxRateOut,
    TaxRatePatch,
)
from saumgm.services.tax_periods import is_period_start, period_containing, periods_between
from saumgm.timeutil import today_in

router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/jurisdictions")
def list_jurisdictions(
    auth: Reader, db: DbSession, parent_id: int | None = None
) -> list[JurisdictionOut]:
    stmt = select(TaxJurisdiction).where(TaxJurisdiction.organization_id == auth.organization_id)
    if parent_id is not None:
        stmt = stmt.where(TaxJurisdiction.parent_id == parent_id)
    return [
        JurisdictionOut.model_validate(j) for j in db.scalars(stmt.order_by(TaxJurisdiction.code))
    ]


@router.post("/jurisdictions", status_code=status.HTTP_201_CREATED)
def create_jurisdiction(body: JurisdictionIn, auth: Owner, db: DbSession) -> JurisdictionOut:
    get_owned(db, TaxJurisdiction, body.parent_id, auth.organization_id)
    jurisdiction = TaxJurisdiction(organization_id=auth.organization_id, **body.model_dump())
    db.add(jurisdiction)
    db.flush()
    db.commit()
    return JurisdictionOut.model_validate(jurisdiction)


@router.patch("/jurisdictions/{jurisdiction_id}")
def update_jurisdiction(
    jurisdiction_id: int, body: JurisdictionPatch, auth: Owner, db: DbSession
) -> JurisdictionOut:
    jurisdiction = get_owned(db, TaxJurisdiction, jurisdiction_id, auth.organization_id)
    apply_changes(jurisdiction, body)
    db.commit()
    return JurisdictionOut.model_validate(jurisdiction)


# -- rates ----------------------------------------------------------------------------------------


@router.get("/jurisdictions/{jurisdiction_id}/rates")
def list_rates(jurisdiction_id: int, auth: Reader, db: DbSession) -> list[TaxRateOut]:
    jurisdiction = get_owned(db, TaxJurisdiction, jurisdiction_id, auth.organization_id)
    return [
        TaxRateOut.model_validate(r)
        for r in sorted(jurisdiction.rates, key=lambda r: (r.effective_from, r.name))
    ]


@router.post("/jurisdictions/{jurisdiction_id}/rates", status_code=status.HTTP_201_CREATED)
def add_rate(jurisdiction_id: int, body: TaxRateIn, auth: Owner, db: DbSession) -> TaxRateOut:
    jurisdiction = get_owned(db, TaxJurisdiction, jurisdiction_id, auth.organization_id)
    rate = TaxRate(**body.model_dump())
    jurisdiction.rates.append(rate)
    db.flush()
    db.commit()
    return TaxRateOut.model_validate(rate)


def _rate(db: DbSession, rate_id: int, org_id: int) -> TaxRate:
    rate = db.get(TaxRate, rate_id)
    if rate is None or rate.jurisdiction.organization_id != org_id:
        raise not_found("Tax rate")
    return rate


@router.patch("/rates/{rate_id}")
def update_rate(rate_id: int, body: TaxRatePatch, auth: Owner, db: DbSession) -> TaxRateOut:
    rate = _rate(db, rate_id, auth.organization_id)
    apply_changes(rate, body)
    db.commit()
    return TaxRateOut.model_validate(rate)


@router.delete("/rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rate(rate_id: int, auth: Owner, db: DbSession) -> None:
    db.delete(_rate(db, rate_id, auth.organization_id))
    db.commit()


# -- registrations --------------------------------------------------------------------------------


@router.get("/registrations")
def list_registrations(auth: Reader, db: DbSession) -> list[RegistrationOut]:
    rows = db.scalars(
        select(TaxRegistration).where(TaxRegistration.organization_id == auth.organization_id)
    )
    return [RegistrationOut.model_validate(r) for r in rows]


@router.post("/registrations", status_code=status.HTTP_201_CREATED)
def add_registration(body: RegistrationIn, auth: Owner, db: DbSession) -> RegistrationOut:
    get_owned(db, TaxJurisdiction, body.jurisdiction_id, auth.organization_id)
    existing = db.scalars(
        select(TaxRegistration).where(
            TaxRegistration.organization_id == auth.organization_id,
            TaxRegistration.jurisdiction_id == body.jurisdiction_id,
        )
    )
    for other in existing:
        overlaps = (other.effective_to is None or other.effective_to >= body.effective_from) and (
            body.effective_to is None or other.effective_from <= body.effective_to
        )
        if overlaps:
            raise conflict("There is already a registration for this jurisdiction in that period")
    registration = TaxRegistration(organization_id=auth.organization_id, **body.model_dump())
    db.add(registration)
    db.flush()
    db.commit()
    return RegistrationOut.model_validate(registration)


@router.patch("/registrations/{registration_id}")
def update_registration(
    registration_id: int, body: RegistrationPatch, auth: Owner, db: DbSession
) -> RegistrationOut:
    registration = get_owned(db, TaxRegistration, registration_id, auth.organization_id)
    apply_changes(registration, body)
    db.commit()
    return RegistrationOut.model_validate(registration)


@router.get("/periods")
def list_periods(
    auth: Reader, db: DbSession, registration_id: int, year: int | None = None
) -> list[TaxPeriod]:
    """The filing periods that start in a calendar year, with what was filed for each."""
    registration = get_owned(db, TaxRegistration, registration_id, auth.organization_id)
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    year = year or today_in(org.timezone).year
    filings = {
        f.period_start: f
        for f in db.scalars(select(TaxFiling).where(TaxFiling.registration_id == registration.id))
    }
    return [
        TaxPeriod(
            registration_id=registration.id,
            period_start=start,
            period_end=end,
            filing=FilingOut.model_validate(filings[start]) if start in filings else None,
        )
        for start, end in periods_between(registration, date(year, 1, 1), date(year, 12, 31))
        if start.year == year
    ]


@router.post("/filings", status_code=status.HTTP_201_CREATED)
def mark_filed(body: FilingIn, auth: Owner, db: DbSession) -> FilingOut:
    registration = get_owned(db, TaxRegistration, body.registration_id, auth.organization_id)
    if not is_period_start(registration, body.period_start):
        raise conflict("period_start is not the first day of one of this registration's periods")
    start, end = period_containing(registration, body.period_start)
    filing = TaxFiling(
        organization_id=auth.organization_id,
        period_start=start,
        period_end=end,
        **body.model_dump(exclude={"period_start"}),
    )
    db.add(filing)
    db.flush()
    db.commit()
    return FilingOut.model_validate(filing)


@router.delete("/filings/{filing_id}", status_code=status.HTTP_204_NO_CONTENT)
def unmark_filed(filing_id: int, auth: Owner, db: DbSession) -> None:
    db.delete(get_owned(db, TaxFiling, filing_id, auth.organization_id))
    db.commit()


@router.delete("/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_registration(registration_id: int, auth: Owner, db: DbSession) -> None:
    db.delete(get_owned(db, TaxRegistration, registration_id, auth.organization_id))
    db.commit()


# -- taxability rules -----------------------------------------------------------------------------


@router.get("/rules")
def list_rules(auth: Reader, db: DbSession) -> list[TaxabilityRuleOut]:
    rows = db.scalars(
        select(TaxabilityRule)
        .join(TaxJurisdiction, TaxJurisdiction.id == TaxabilityRule.jurisdiction_id)
        .where(TaxJurisdiction.organization_id == auth.organization_id)
    )
    return [TaxabilityRuleOut.model_validate(r) for r in rows]


@router.put("/rules")
def set_rule(body: TaxabilityRuleIn, auth: Owner, db: DbSession) -> TaxabilityRuleOut:
    """Create or replace the rule for a jurisdiction and tax category."""
    get_owned(db, TaxJurisdiction, body.jurisdiction_id, auth.organization_id)
    get_owned(db, TaxCategory, body.tax_category_id, auth.organization_id)
    rule = db.scalars(
        select(TaxabilityRule).where(
            TaxabilityRule.jurisdiction_id == body.jurisdiction_id,
            TaxabilityRule.tax_category_id == body.tax_category_id,
        )
    ).one_or_none()
    if rule is None:
        rule = TaxabilityRule(**body.model_dump())
        db.add(rule)
    else:
        rule.is_taxable = body.is_taxable
    db.flush()
    db.commit()
    return TaxabilityRuleOut.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, auth: Owner, db: DbSession) -> None:
    rule = db.get(TaxabilityRule, rule_id)
    if rule is None:
        raise not_found("Rule")
    get_owned(db, TaxJurisdiction, rule.jurisdiction_id, auth.organization_id)
    db.delete(rule)
    db.commit()
