from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.legacy_import.config import ImportConfig
from saumgm.legacy_import.mapping import import_access
from saumgm.models import AuditLog, Deposit, Expense, Invoice, Payment
from saumgm.seed import OrganizationSetup
from saumgm.services.archive import archive_through
from tests.legacy_sample import sample_data


def run_import(session: Session, archive: date | None = None) -> int:
    config = ImportConfig(
        organization=OrganizationSetup(legal_name="Example Co", display_name="Example"),
        self_party_no="00010000",
        archive_through=archive,
    )
    result = import_access(session, sample_data(), config)
    session.expire_all()
    return result.organization_id


def archived(
    session: Session, model: type[Invoice | Payment | Deposit | Expense]
) -> dict[int, bool]:
    rows: list[Any] = list(session.scalars(select(model)))
    return {r.legacy_id or 0: r.archived_at is not None for r in rows}


def test_import_archives_through_the_configured_date(db_session: Session) -> None:
    run_import(db_session, archive=date(2019, 12, 31))

    assert archived(db_session, Invoice) == {1001: True, 1002: False, 1003: False}
    # payment 2 has no date and its invoice (1003) is not archived
    assert archived(db_session, Payment) == {1: True, 2: False, 3: False}
    assert archived(db_session, Deposit) == {1: True, 2: False}  # deposit 2 has no date
    assert archived(db_session, Expense) == {1: True, 2: False}

    entry = db_session.scalars(select(AuditLog).where(AuditLog.action == "archive")).one()
    assert entry.changes == {
        "through": "2019-12-31",
        "archived": {"invoice": 1, "payment": 1, "deposit": 1, "expense": 1},
    }


def test_undated_payment_follows_its_invoices(db_session: Session) -> None:
    org_id = run_import(db_session)
    assert not any(archived(db_session, Invoice).values())

    counts = archive_through(db_session, org_id, date(2024, 12, 31))
    db_session.expire_all()

    assert counts == {"invoice": 3, "payment": 3, "deposit": 1, "expense": 2}
    assert archived(db_session, Payment) == {1: True, 2: True, 3: True}


def test_archiving_twice_changes_nothing(db_session: Session) -> None:
    org_id = run_import(db_session, archive=date(2019, 12, 31))
    first = {i.legacy_id: i.archived_at for i in db_session.scalars(select(Invoice))}

    counts = archive_through(db_session, org_id, date(2019, 12, 31))
    db_session.expire_all()

    assert counts == {"invoice": 0, "payment": 0, "deposit": 0, "expense": 0}
    assert {i.legacy_id: i.archived_at for i in db_session.scalars(select(Invoice))} == first
