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

"""Invoices and credit notes."""

from dataclasses import replace
from datetime import date
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from saumgm.api.common import (
    ArchiveFilter,
    LimitParam,
    OffsetParam,
    Page,
    apply_archive_filter,
    conflict,
    ensure_current,
    get_owned,
    set_archived,
)
from saumgm.api.deps import Auth, DbSession, Editor, Owner, Reader
from saumgm.context import get_context, set_context
from saumgm.enums import InvoiceKind, InvoiceStatus, UserRoleType
from saumgm.models import (
    Invoice,
    InvoiceRevision,
    Organization,
    Party,
    Payment,
    PaymentAllocation,
)
from saumgm.schemas.invoices import (
    BulkWriteOffRequest,
    BulkWriteOffResult,
    CalculateRequest,
    CalculateResult,
    CreditNoteCreate,
    InvoiceCreate,
    InvoiceListItem,
    InvoiceOut,
    InvoicePatch,
    InvoicePayment,
    InvoiceRevise,
    IssueRequest,
    LineOut,
    RevisionOut,
    RevisionSummary,
    Skipped,
    TaxOut,
    UndoWriteOffRequest,
    VoidRequest,
    WriteOffRequest,
    WrittenOff,
)
from saumgm.services import invoices as service
from saumgm.services.money import ZERO
from saumgm.timeutil import today_in

router = APIRouter(prefix="/invoices", tags=["invoices"])

DETAIL_FIELDS = (
    "terms_days", "terms_text", "tax_jurisdiction_id", "tax_location_text", "freight",
    "adjustment", "adjustment_note", "notes", "subtotal", "tax_total", "revision_no", "issued_at",
    "voided_at", "void_reason", "write_off_date", "write_off_amount", "write_off_reason",
    "legacy_data", *service.BILL_TO_FIELDS,
)  # fmt: skip


class PaymentFilter(StrEnum):
    OPEN = "open"  # issued, money still due
    OVERDUE = "overdue"
    PAID = "paid"
    WRITTEN_OFF = "written_off"


def _org(db: Session, auth: Auth) -> Organization:
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    return org


def _invoice(db: Session, invoice_id: int, auth: Auth) -> Invoice:
    return get_owned(db, Invoice, invoice_id, auth.organization_id)


def _party(db: Session, party_id: int, auth: Auth) -> Party:
    return get_owned(db, Party, party_id, auth.organization_id)


def _service_errors(exc: service.InvoiceError) -> HTTPException:
    return conflict(str(exc))


def _header(body: Any) -> dict[str, Any]:
    header: dict[str, Any] = body.model_dump(include=set(service.HEADER_FIELDS), exclude_unset=True)
    return header


def _list_item(invoice: Invoice, party_name: str, info: service.BalanceInfo) -> InvoiceListItem:
    return InvoiceListItem(
        id=invoice.id,
        kind=invoice.kind,
        number=invoice.number,
        status=invoice.status,
        party_id=invoice.party_id,
        party_name=party_name,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        total=invoice.total,
        is_historical=invoice.is_historical,
        archived_at=invoice.archived_at,
        amount_paid=info.paid,
        amount_credited=info.credited,
        balance_due=info.balance_due,
        payment_status=info.status,
        is_overdue=info.overdue,
    )


def detail(
    db: Session, org: Organization, invoice: Invoice, warnings: list[str] | None = None
) -> InvoiceOut:
    party = db.get(Party, invoice.party_id)
    info = service.balances(db, [invoice], today_in(org.timezone))[invoice.id]
    payments = db.execute(
        select(PaymentAllocation, Payment)
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(PaymentAllocation.invoice_id == invoice.id)
        .order_by(Payment.received_date, Payment.id)
    ).all()
    credit_notes = db.scalars(
        select(Invoice.id).where(Invoice.credited_invoice_id == invoice.id).order_by(Invoice.id)
    ).all()
    revisions = db.scalars(
        select(InvoiceRevision)
        .where(InvoiceRevision.invoice_id == invoice.id)
        .order_by(InvoiceRevision.revision_no)
    ).all()
    base = _list_item(invoice, party.name if party else "", info)
    return InvoiceOut(
        **base.model_dump(),
        credited_invoice_id=invoice.credited_invoice_id,
        **{key: getattr(invoice, key) for key in DETAIL_FIELDS},
        lines=[LineOut.model_validate(line) for line in invoice.lines],
        taxes=[TaxOut.model_validate(tax) for tax in invoice.taxes],
        payments=[
            InvoicePayment(
                payment_id=payment.id,
                amount=allocation.amount,
                received_date=payment.received_date,
                method=payment.method,
                channel=payment.channel,
                reference=payment.reference,
            )
            for allocation, payment in payments
        ],
        credit_note_ids=list(credit_notes),
        revisions=[RevisionSummary.model_validate(r) for r in revisions],
        warnings=warnings or [],
    )


# -- list -----------------------------------------------------------------------------------------


@router.get("")
def list_invoices(
    auth: Reader,
    db: DbSession,
    q: str | None = Query(None, description="Search number, bill-to or contact name"),
    party_id: int | None = None,
    kind: InvoiceKind | None = None,
    status_: InvoiceStatus | None = Query(None, alias="status"),
    payment: PaymentFilter | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    archived: ArchiveFilter = ArchiveFilter.CURRENT,
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[InvoiceListItem]:
    org = _org(db, auth)
    today = today_in(org.timezone)
    credit = aliased(Invoice)
    paid = (
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .where(PaymentAllocation.invoice_id == Invoice.id)
        .scalar_subquery()
    )
    credited = (
        select(func.coalesce(func.sum(credit.total), 0))
        .where(credit.credited_invoice_id == Invoice.id, credit.status == InvoiceStatus.ISSUED)
        .scalar_subquery()
    )
    balance = Invoice.total - paid - credited - func.coalesce(Invoice.write_off_amount, 0)

    stmt: Any = (
        select(Invoice, Party.name)
        .join(Party, Party.id == Invoice.party_id)
        .where(Invoice.organization_id == auth.organization_id)
        .order_by(Invoice.issue_date.desc(), Invoice.id.desc())
    )
    stmt = apply_archive_filter(stmt, Invoice, archived)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Invoice.number.ilike(pattern),
                Invoice.bill_to_company.ilike(pattern),
                Invoice.bill_to_name.ilike(pattern),
                Party.name.ilike(pattern),
            )
        )
    if party_id is not None:
        stmt = stmt.where(Invoice.party_id == party_id)
    if kind is not None:
        stmt = stmt.where(Invoice.kind == kind)
    if status_ is not None:
        stmt = stmt.where(Invoice.status == status_)
    if date_from is not None:
        stmt = stmt.where(Invoice.issue_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Invoice.issue_date <= date_to)
    if payment is not None:
        issued = and_(Invoice.status == InvoiceStatus.ISSUED, Invoice.kind == InvoiceKind.INVOICE)
        due = balance > service.PAID_TOLERANCE
        if payment == PaymentFilter.OPEN:
            stmt = stmt.where(issued, due)
        elif payment == PaymentFilter.OVERDUE:
            stmt = stmt.where(issued, due, Invoice.due_date < today)
        elif payment == PaymentFilter.WRITTEN_OFF:
            stmt = stmt.where(issued, Invoice.write_off_date.is_not(None))
        else:
            stmt = stmt.where(issued, ~due, Invoice.write_off_date.is_(None))

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.limit(limit).offset(offset)).all()
    infos = service.balances(db, [inv for inv, _ in rows], today)
    return Page(
        items=[_list_item(inv, name, infos[inv.id]) for inv, name in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# -- drafts ---------------------------------------------------------------------------------------


@router.post("/calculate")
def calculate(body: CalculateRequest, auth: Reader, db: DbSession) -> CalculateResult:
    """Totals and tax for a draft being edited, without saving anything."""
    org = _org(db, auth)
    party = _party(db, body.party_id, auth)
    # The invoice and its lines are never added to the session, so nothing is saved.
    with db.no_autoflush:
        invoice = Invoice(
            organization_id=org.id,
            party_id=party.id,
            freight=body.freight,
            adjustment=body.adjustment,
            tax_total=ZERO,
            issue_date=body.issue_date,
            tax_jurisdiction_id=body.tax_jurisdiction_id
            or service.default_tax_jurisdiction(db, org.id, party),
        )
        try:
            invoice.lines = [
                service.build_line(db, org.id, line, i) for i, line in enumerate(body.lines)
            ]
        except service.InvoiceError as exc:
            raise _service_errors(exc) from None
        service.recalculate(db, org, invoice)
        result = CalculateResult(
            lines=[LineOut.model_validate(line) for line in invoice.lines],
            subtotal=invoice.subtotal,
            taxes=[TaxOut.model_validate(tax) for tax in invoice.taxes],
            tax_total=invoice.tax_total,
            total=invoice.total,
        )
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
def create_invoice(body: InvoiceCreate, auth: Editor, db: DbSession) -> InvoiceOut:
    org = _org(db, auth)
    party = _party(db, body.party_id, auth)
    try:
        invoice = service.create_invoice(db, org, party, _header(body), body.lines)
    except service.InvoiceError as exc:
        raise _service_errors(exc) from None
    db.commit()
    return detail(db, org, invoice)


@router.get("/{invoice_id}")
def get_invoice(invoice_id: int, auth: Reader, db: DbSession) -> InvoiceOut:
    return detail(db, _org(db, auth), _invoice(db, invoice_id, auth))


@router.patch("/{invoice_id}")
def update_invoice(invoice_id: int, body: InvoicePatch, auth: Editor, db: DbSession) -> InvoiceOut:
    org = _org(db, auth)
    invoice = _invoice(db, invoice_id, auth)
    party = _party(db, body.party_id, auth) if body.party_id is not None else None
    try:
        service.update_draft(db, org, invoice, _header(body), body.lines, party)
    except service.InvoiceError as exc:
        raise _service_errors(exc) from None
    db.commit()
    return detail(db, org, invoice)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(invoice_id: int, auth: Editor, db: DbSession) -> None:
    invoice = _invoice(db, invoice_id, auth)
    try:
        service.delete_draft(db, invoice)
    except service.InvoiceError as exc:
        raise _service_errors(exc) from None
    db.commit()


# -- lifecycle ------------------------------------------------------------------------------------


@router.post("/{invoice_id}/issue")
def issue_invoice(invoice_id: int, body: IssueRequest, auth: Editor, db: DbSession) -> InvoiceOut:
    org = _org(db, auth)
    invoice = _invoice(db, invoice_id, auth)
    try:
        service.issue(db, org, invoice, body.issue_date)
    except service.InvoiceError as exc:
        raise _service_errors(exc) from None
    db.commit()
    return detail(db, org, invoice)


@router.post("/{invoice_id}/void")
def void_invoice(invoice_id: int, body: VoidRequest, auth: Editor, db: DbSession) -> InvoiceOut:
    org = _org(db, auth)
    invoice = _invoice(db, invoice_id, auth)
    ensure_current(invoice)
    try:
        service.void(db, invoice, body.reason)
    except service.InvoiceError as exc:
        raise _service_errors(exc) from None
    db.commit()
    return detail(db, org, invoice)


@router.post("/{invoice_id}/revise")
def revise_invoice(invoice_id: int, body: InvoiceRevise, auth: Editor, db: DbSession) -> InvoiceOut:
    org = _org(db, auth)
    if org.invoice_revision_owner_only and auth.role != UserRoleType.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can revise invoices")
    invoice = _invoice(db, invoice_id, auth)
    ensure_current(invoice)
    # Every audit row written by this change carries the reason.
    set_context(db, replace(get_context(db), reason=body.reason))
    try:
        warnings = service.revise(
            db, org, invoice, _header(body), body.lines, reason=body.reason, user_id=auth.user.id
        )
    except service.InvoiceError as exc:
        raise _service_errors(exc) from None
    db.commit()
    return detail(db, org, invoice, warnings)


@router.get("/{invoice_id}/revisions/{revision_no}")
def get_revision(invoice_id: int, revision_no: int, auth: Reader, db: DbSession) -> RevisionOut:
    invoice = _invoice(db, invoice_id, auth)
    revision = db.scalars(
        select(InvoiceRevision).where(
            InvoiceRevision.invoice_id == invoice.id, InvoiceRevision.revision_no == revision_no
        )
    ).one_or_none()
    if revision is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revision not found")
    return RevisionOut.model_validate(revision)


@router.post("/write-off")
def write_off_many(body: BulkWriteOffRequest, auth: Editor, db: DbSession) -> BulkWriteOffResult:
    """Write off several uncollectible invoices at once; ones that cannot be are reported."""
    org = _org(db, auth)
    set_context(db, replace(get_context(db), reason=body.reason))
    done: list[WrittenOff] = []
    skipped: list[Skipped] = []
    for invoice_id in dict.fromkeys(body.invoice_ids):
        invoice = db.get(Invoice, invoice_id)
        if invoice is None or invoice.organization_id != auth.organization_id:
            skipped.append(Skipped(invoice_id=invoice_id, number=None, reason="not found"))
            continue
        try:
            amount = service.write_off(db, org, invoice, body.reason, body.write_off_date)
        except service.InvoiceError as exc:
            skipped.append(Skipped(invoice_id=invoice.id, number=invoice.number, reason=str(exc)))
            continue
        done.append(WrittenOff(invoice_id=invoice.id, number=invoice.number, amount=amount))
    db.commit()
    return BulkWriteOffResult(written_off=done, skipped=skipped)


@router.post("/{invoice_id}/write-off")
def write_off(invoice_id: int, body: WriteOffRequest, auth: Editor, db: DbSession) -> InvoiceOut:
    """Give up on an uncollectible balance (bad debt). The sale still counts."""
    org = _org(db, auth)
    invoice = _invoice(db, invoice_id, auth)
    set_context(db, replace(get_context(db), reason=body.reason))
    try:
        service.write_off(db, org, invoice, body.reason, body.write_off_date)
    except service.InvoiceError as exc:
        raise _service_errors(exc) from None
    db.commit()
    return detail(db, org, invoice)


@router.post("/{invoice_id}/undo-write-off")
def undo_write_off(
    invoice_id: int, body: UndoWriteOffRequest, auth: Owner, db: DbSession
) -> InvoiceOut:
    invoice = _invoice(db, invoice_id, auth)
    set_context(db, replace(get_context(db), reason=body.reason))
    try:
        service.undo_write_off(db, invoice, body.reason)
    except service.InvoiceError as exc:
        raise _service_errors(exc) from None
    db.commit()
    return detail(db, _org(db, auth), invoice)


@router.post("/{invoice_id}/credit-note", status_code=status.HTTP_201_CREATED)
def create_credit_note(
    invoice_id: int, body: CreditNoteCreate, auth: Editor, db: DbSession
) -> InvoiceOut:
    org = _org(db, auth)
    invoice = _invoice(db, invoice_id, auth)
    ensure_current(invoice)
    try:
        note = service.create_credit_note(db, org, invoice, body.lines, body.notes)
    except service.InvoiceError as exc:
        raise _service_errors(exc) from None
    db.commit()
    return detail(db, org, note)


@router.post("/{invoice_id}/archive")
def archive_invoice(invoice_id: int, auth: Editor, db: DbSession) -> InvoiceOut:
    invoice = _invoice(db, invoice_id, auth)
    if invoice.status == InvoiceStatus.DRAFT:
        raise conflict("Drafts cannot be archived; delete them instead")
    set_archived(invoice, True)
    db.commit()
    return detail(db, _org(db, auth), invoice)


@router.post("/{invoice_id}/unarchive")
def unarchive_invoice(invoice_id: int, auth: Owner, db: DbSession) -> InvoiceOut:
    invoice = _invoice(db, invoice_id, auth)
    set_archived(invoice, False)
    db.commit()
    return detail(db, _org(db, auth), invoice)
