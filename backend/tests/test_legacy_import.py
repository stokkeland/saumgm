from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from saumgm.legacy_import.archive import write_archive
from saumgm.legacy_import.config import ImportConfig
from saumgm.legacy_import.mapping import ImportResult, import_access
from saumgm.legacy_import.reconcile import reconcile
from saumgm.legacy_import.report import render_report
from saumgm.models import (
    Expense,
    Invoice,
    NumberSequence,
    Organization,
    Party,
    Payment,
)
from saumgm.models.enums import (
    InvoiceStatus,
    PartyKind,
    PartyRoleType,
    PaymentChannel,
    PaymentMethod,
)
from saumgm.seed import OrganizationSetup
from tests.legacy_sample import sample_data


@pytest.fixture
def imported(db_session: Session) -> tuple[Session, ImportResult]:
    config = ImportConfig(
        organization=OrganizationSetup(legal_name="Example Co", display_name="Example"),
        self_party_no="00010000",
    )
    result = import_access(db_session, sample_data(), config)
    db_session.expire_all()
    return db_session, result


def party(session: Session, party_no: str) -> Party:
    return session.scalars(select(Party).where(Party.party_no == party_no)).one()


def invoice(session: Session, number: str) -> Invoice:
    return session.scalars(select(Invoice).where(Invoice.number == number)).one()


def test_reconciliation_passes(imported: tuple[Session, ImportResult]) -> None:
    session, result = imported
    checks = reconcile(session, sample_data(), result)
    assert [c for c in checks if not c.ok] == []
    report = render_report(result, checks, {}, "sample.mdb")
    assert "**PASSED**" in report


def test_organization_and_number_sequences(imported: tuple[Session, ImportResult]) -> None:
    session, _ = imported
    org = session.scalars(select(Organization)).one()
    assert org.self_party_id == party(session, "00010000").id
    sequences = {s.name: s for s in session.scalars(select(NumberSequence))}
    assert sequences["invoice"].next_value == 1004
    assert sequences["party"].format(sequences["party"].next_value) == "00010006"


def test_parties(imported: tuple[Session, ImportResult]) -> None:
    session, result = imported
    acme = party(session, "00010001")
    assert acme.name == "Acme Corporation"
    assert acme.created_at.date() == date(2004, 8, 8)
    assert [c.name for c in acme.contacts] == ["Ann Smith"]
    assert acme.addresses[0].country_code == "US"

    bob = party(session, "00010002")
    assert bob.kind == PartyKind.PERSON
    assert bob.is_active is False  # closed client
    assert bob.addresses[0].country_code == "CA"  # inferred from province
    assert [e.certificate_type for e in bob.tax_exemptions] == ["Native American"]
    assert acme.tax_exemptions == []
    assert bob.legacy_data == {"file_type": "C", "client": {"ClientID": 3, "Nick": "BOB"}}

    bank = party(session, "00010004")
    assert {r.role for r in bank.roles} == {PartyRoleType.FINANCIAL, PartyRoleType.VENDOR}
    assert any("00010005" in issue for issue in result.issues)


def test_invoices_keep_history(imported: tuple[Session, ImportResult]) -> None:
    session, _ = imported
    paid = invoice(session, "1001")
    assert paid.status == InvoiceStatus.ISSUED
    assert paid.is_historical
    assert paid.terms_days == 30
    assert paid.due_date == date(2019, 2, 9)
    assert [line.line_total for line in paid.lines] == [Decimal("114"), Decimal("137.5")]
    [tax] = paid.taxes
    assert (tax.name, tax.amount, tax.taxable_base) == (
        "Salamanca NY",
        Decimal(11),
        Decimal("137.5"),
    )

    cancelled = invoice(session, "1002")
    assert cancelled.status == InvoiceStatus.VOID
    assert cancelled.terms_days is None
    assert cancelled.terms_text == "50/50 Start/Completion"

    assert invoice(session, "1003").terms_days == 0  # "Cash"


def test_receipts_are_merged_into_payments(imported: tuple[Session, ImportResult]) -> None:
    session, result = imported
    by_legacy = {p.legacy_id: p for p in session.scalars(select(Payment))}
    linked, undated, matched = by_legacy[1], by_legacy[2], by_legacy[3]

    assert (linked.method, linked.channel, linked.reference) == (
        PaymentMethod.CHECK,
        PaymentChannel.MAIL,
        "1234",
    )
    assert matched.method == PaymentMethod.CASH
    assert matched.legacy_data and matched.legacy_data["receipt_id"] == 8
    assert undated.received_date is None and undated.method is None
    assert [r["trxID"] for r in result.unmatched_receipts] == [9]


def test_orphans_and_file_numbers_are_reported(imported: tuple[Session, ImportResult]) -> None:
    session, result = imported
    assert [d["depositItemId"] for d in result.orphan_deposit_items] == [3]
    assert any("Invoice line 5" in issue for issue in result.issues)
    assert any("Expense line 4" in issue for issue in result.issues)

    expenses = {e.legacy_id: e for e in session.scalars(select(Expense))}
    assert expenses[1].vendor_party_id == party(session, "00010003").id  # "10003" padded
    assert expenses[1].for_party_id == party(session, "00010000").id
    assert expenses[2].vendor_party_id is None
    assert expenses[2].legacy_data == {"vendor_file_no": "99999999"}


def test_archive_copies_every_table(migrated_engine: Engine) -> None:
    data = sample_data()
    with migrated_engine.begin() as conn:
        counts = write_archive(conn, data)
        try:
            assert counts["legacy_tblinvoicedtl"] == 5
            assert counts["legacy_tblprojecthdr"] == 1
            stored = conn.execute(
                text("SELECT itemqty FROM legacy_tblinvoicedtl WHERE invoicedtlid = 4")
            ).scalar_one()
            assert stored == 3.25
            assert set(counts) <= set(inspect(conn).get_table_names())
        finally:
            for name in counts:
                conn.execute(text(f"DROP TABLE {name}"))


def test_import_runs_in_one_transaction(db_session: Session) -> None:
    config = ImportConfig(
        organization=OrganizationSetup(legal_name="X", display_name="X"),
        self_party_no="no-such-party",
    )
    with pytest.raises(ValueError, match="self_party_no"):
        import_access(db_session, sample_data(), config)
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(Organization)) == 0
