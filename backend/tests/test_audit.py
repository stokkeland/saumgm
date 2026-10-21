from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.context import RequestContext, set_context
from saumgm.enums import AddressType, AuditActor
from saumgm.models import AuditLog, Organization, Party, PartyAddress, User


def entries(session: Session, entity_type: str) -> list[AuditLog]:
    return list(
        session.scalars(
            select(AuditLog).where(AuditLog.entity_type == entity_type).order_by(AuditLog.id)
        )
    )


def test_changes_are_recorded_with_who_and_parent(
    db_session: Session, org: Organization, owner: User
) -> None:
    set_context(
        db_session,
        RequestContext(
            organization_id=org.id, user_id=owner.id, actor=AuditActor.USER, request_id="req-1"
        ),
    )
    party = Party(organization_id=org.id, party_no="00000001", short_code="ACME", name="Acme")
    party.addresses.append(PartyAddress(address_type=AddressType.BILLING, city="Buffalo"))
    db_session.add(party)
    db_session.flush()

    party.name = "Acme Corporation"
    db_session.flush()
    db_session.delete(party)
    db_session.flush()

    created, updated, deleted = entries(db_session, "party")
    assert created.action == "create"
    assert created.changes and created.changes["name"] == [None, "Acme"]
    assert created.user_id == owner.id and created.request_id == "req-1"
    assert updated.changes == {"name": ["Acme", "Acme Corporation"]}
    assert deleted.action == "delete"
    assert deleted.changes and deleted.changes["name"] == ["Acme Corporation", None]

    address_created, address_deleted = entries(db_session, "party_address")
    assert (address_created.parent_type, address_created.parent_id) == ("party", str(party.id))
    assert address_deleted.action == "delete"


def test_password_hashes_are_redacted(db_session: Session, owner: User) -> None:
    [identity] = entries(db_session, "user_identity")
    assert identity.changes and identity.changes["password_hash"] == [None, "***"]
