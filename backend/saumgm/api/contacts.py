"""Contacts: clients, vendors, banks and other parties (the old "files")."""

from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from saumgm.api.common import (
    ArchiveFilter,
    LimitParam,
    OffsetParam,
    Page,
    apply_archive_filter,
    apply_changes,
    conflict,
    ensure_current,
    get_owned,
    not_found,
    paginate,
    set_archived,
)
from saumgm.api.deps import DbSession, Editor, Owner, Reader
from saumgm.enums import PartyRoleType
from saumgm.models import (
    Account,
    Party,
    PartyAddress,
    PartyContact,
    PartyRole,
    TaxExemption,
    TaxJurisdiction,
)
from saumgm.schemas.contacts import (
    AddressIn,
    AddressOut,
    AddressPatch,
    ExemptionIn,
    ExemptionOut,
    ExemptionPatch,
    PartyCreate,
    PartyDetail,
    PartyPatch,
    PartySummary,
    PersonIn,
    PersonOut,
    PersonPatch,
)
from saumgm.services.numbering import next_number

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _default_address(party: Party) -> PartyAddress | None:
    defaults = [a for a in party.addresses if a.is_default]
    candidates = defaults or party.addresses
    return candidates[0] if candidates else None


def summary(party: Party) -> PartySummary:
    address = _default_address(party)
    return PartySummary(
        id=party.id,
        party_no=party.party_no,
        short_code=party.short_code,
        name=party.name,
        kind=party.kind,
        roles=sorted(r.role for r in party.roles),
        is_active=party.is_active,
        archived_at=party.archived_at,
        email=party.email,
        phone=party.phone,
        city=address.city if address else None,
        region=address.region if address else None,
        country_code=address.country_code if address else None,
    )


def detail(party: Party) -> PartyDetail:
    return PartyDetail(
        **summary(party).model_dump(),
        fax=party.fax,
        website=party.website,
        tax_id=party.tax_id,
        notes=party.notes,
        default_terms_days=party.default_terms_days,
        vendor_account_no=party.vendor_account_no,
        default_expense_account_id=party.default_expense_account_id,
        addresses=[AddressOut.model_validate(a) for a in party.addresses],
        people=[PersonOut.model_validate(c) for c in party.contacts],
        tax_exemptions=[ExemptionOut.model_validate(e) for e in party.tax_exemptions],
        legacy_data=party.legacy_data,
        created_at=party.created_at,
        updated_at=party.updated_at,
    )


def _check_refs(db: Session, org_id: int, **refs: int | None) -> None:
    """Referenced records must belong to the same organization."""
    models: dict[str, Any] = {
        "default_expense_account_id": Account,
        "tax_jurisdiction_id": TaxJurisdiction,
        "jurisdiction_id": TaxJurisdiction,
    }
    for key, value in refs.items():
        if value is not None:
            get_owned(db, models[key], value, org_id)


def _check_roles(roles: list[PartyRoleType], party: Party | None = None) -> None:
    had_self = party is not None and any(r.role == PartyRoleType.SELF for r in party.roles)
    if (PartyRoleType.SELF in roles) != had_self:
        raise conflict("The 'self' role belongs only to the business's own contact.")


def _ensure_single_default(party: Party, address: PartyAddress) -> None:
    if address.is_default:
        for other in party.addresses:
            if other is not address and other.address_type == address.address_type:
                other.is_default = False


def _load(db: Session, party_id: int, org_id: int) -> Party:
    return get_owned(db, Party, party_id, org_id)


@router.get("")
def list_contacts(
    auth: Reader,
    db: DbSession,
    q: str | None = Query(None, description="Search name, code, number or email"),
    role: PartyRoleType | None = None,
    active: bool | None = None,
    archived: ArchiveFilter = ArchiveFilter.CURRENT,
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[PartySummary]:
    stmt = (
        select(Party)
        .where(Party.organization_id == auth.organization_id)
        .options(selectinload(Party.roles), selectinload(Party.addresses))
        .order_by(Party.name)
    )
    stmt = apply_archive_filter(stmt, Party, archived)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Party.name.ilike(pattern),
                Party.short_code.ilike(pattern),
                Party.party_no.ilike(pattern),
                Party.email.ilike(pattern),
            )
        )
    if role:
        stmt = stmt.where(Party.roles.any(PartyRole.role == role))
    if active is not None:
        stmt = stmt.where(Party.is_active == active)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=[summary(p) for p in items], total=total, limit=limit, offset=offset)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_contact(body: PartyCreate, auth: Editor, db: DbSession) -> PartyDetail:
    _check_roles(body.roles)
    _check_refs(
        db, auth.organization_id, default_expense_account_id=body.default_expense_account_id
    )
    for address in body.addresses:
        _check_refs(db, auth.organization_id, tax_jurisdiction_id=address.tax_jurisdiction_id)
    party = Party(
        organization_id=auth.organization_id,
        party_no=next_number(db, auth.organization_id, "party"),
        **body.model_dump(exclude={"roles", "addresses", "people"}),
    )
    party.roles = [PartyRole(role=r) for r in sorted(set(body.roles))]
    party.addresses = [PartyAddress(**a.model_dump()) for a in body.addresses]
    party.contacts = [PartyContact(**p.model_dump()) for p in body.people]
    db.add(party)
    db.flush()
    db.commit()
    return detail(party)


@router.get("/{party_id}")
def get_contact(party_id: int, auth: Reader, db: DbSession) -> PartyDetail:
    return detail(_load(db, party_id, auth.organization_id))


@router.patch("/{party_id}")
def update_contact(party_id: int, body: PartyPatch, auth: Editor, db: DbSession) -> PartyDetail:
    party = _load(db, party_id, auth.organization_id)
    ensure_current(party)
    _check_refs(
        db, auth.organization_id, default_expense_account_id=body.default_expense_account_id
    )
    if body.roles is not None:
        _check_roles(body.roles, party)
        wanted = set(body.roles)
        party.roles = [r for r in party.roles if r.role in wanted] + [
            PartyRole(role=r) for r in sorted(wanted - {r.role for r in party.roles})
        ]
    apply_changes(party, body, exclude={"roles"})
    db.flush()
    db.commit()
    return detail(party)


@router.post("/{party_id}/archive")
def archive_contact(party_id: int, auth: Editor, db: DbSession) -> PartyDetail:
    party = _load(db, party_id, auth.organization_id)
    if any(r.role == PartyRoleType.SELF for r in party.roles):
        raise conflict("The business's own contact cannot be archived.")
    set_archived(party, True)
    db.commit()
    return detail(party)


@router.post("/{party_id}/unarchive")
def unarchive_contact(party_id: int, auth: Owner, db: DbSession) -> PartyDetail:
    party = _load(db, party_id, auth.organization_id)
    set_archived(party, False)
    db.commit()
    return detail(party)


# -- addresses ------------------------------------------------------------------------------------


@router.post("/{party_id}/addresses", status_code=status.HTTP_201_CREATED)
def add_address(party_id: int, body: AddressIn, auth: Editor, db: DbSession) -> AddressOut:
    party = _load(db, party_id, auth.organization_id)
    ensure_current(party)
    _check_refs(db, auth.organization_id, tax_jurisdiction_id=body.tax_jurisdiction_id)
    address = PartyAddress(**body.model_dump())
    party.addresses.append(address)
    _ensure_single_default(party, address)
    db.flush()
    db.commit()
    return AddressOut.model_validate(address)


def _address(party: Party, address_id: int) -> PartyAddress:
    for address in party.addresses:
        if address.id == address_id:
            return address
    raise not_found("Address")


@router.patch("/{party_id}/addresses/{address_id}")
def update_address(
    party_id: int, address_id: int, body: AddressPatch, auth: Editor, db: DbSession
) -> AddressOut:
    party = _load(db, party_id, auth.organization_id)
    ensure_current(party)
    _check_refs(db, auth.organization_id, tax_jurisdiction_id=body.tax_jurisdiction_id)
    address = _address(party, address_id)
    apply_changes(address, body)
    _ensure_single_default(party, address)
    db.commit()
    return AddressOut.model_validate(address)


@router.delete("/{party_id}/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(party_id: int, address_id: int, auth: Editor, db: DbSession) -> None:
    party = _load(db, party_id, auth.organization_id)
    ensure_current(party)
    party.addresses.remove(_address(party, address_id))
    db.commit()


# -- people ---------------------------------------------------------------------------------------


def _person(party: Party, person_id: int) -> PartyContact:
    for person in party.contacts:
        if person.id == person_id:
            return person
    raise not_found("Person")


@router.post("/{party_id}/people", status_code=status.HTTP_201_CREATED)
def add_person(party_id: int, body: PersonIn, auth: Editor, db: DbSession) -> PersonOut:
    party = _load(db, party_id, auth.organization_id)
    ensure_current(party)
    person = PartyContact(**body.model_dump())
    party.contacts.append(person)
    db.flush()
    db.commit()
    return PersonOut.model_validate(person)


@router.patch("/{party_id}/people/{person_id}")
def update_person(
    party_id: int, person_id: int, body: PersonPatch, auth: Editor, db: DbSession
) -> PersonOut:
    party = _load(db, party_id, auth.organization_id)
    ensure_current(party)
    person = _person(party, person_id)
    apply_changes(person, body)
    db.commit()
    return PersonOut.model_validate(person)


@router.delete("/{party_id}/people/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(party_id: int, person_id: int, auth: Editor, db: DbSession) -> None:
    party = _load(db, party_id, auth.organization_id)
    ensure_current(party)
    party.contacts.remove(_person(party, person_id))
    db.commit()


# -- tax exemptions -------------------------------------------------------------------------------


def _exemption(party: Party, exemption_id: int) -> TaxExemption:
    for exemption in party.tax_exemptions:
        if exemption.id == exemption_id:
            return exemption
    raise not_found("Tax exemption")


@router.post("/{party_id}/tax-exemptions", status_code=status.HTTP_201_CREATED)
def add_exemption(party_id: int, body: ExemptionIn, auth: Editor, db: DbSession) -> ExemptionOut:
    party = _load(db, party_id, auth.organization_id)
    ensure_current(party)
    _check_refs(db, auth.organization_id, jurisdiction_id=body.jurisdiction_id)
    exemption = TaxExemption(**body.model_dump())
    party.tax_exemptions.append(exemption)
    db.flush()
    db.commit()
    return ExemptionOut.model_validate(exemption)


@router.patch("/{party_id}/tax-exemptions/{exemption_id}")
def update_exemption(
    party_id: int, exemption_id: int, body: ExemptionPatch, auth: Editor, db: DbSession
) -> ExemptionOut:
    party = _load(db, party_id, auth.organization_id)
    ensure_current(party)
    _check_refs(db, auth.organization_id, jurisdiction_id=body.jurisdiction_id)
    exemption = _exemption(party, exemption_id)
    apply_changes(exemption, body)
    db.commit()
    return ExemptionOut.model_validate(exemption)


@router.delete("/{party_id}/tax-exemptions/{exemption_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exemption(party_id: int, exemption_id: int, auth: Editor, db: DbSession) -> None:
    party = _load(db, party_id, auth.organization_id)
    ensure_current(party)
    party.tax_exemptions.remove(_exemption(party, exemption_id))
    db.commit()
