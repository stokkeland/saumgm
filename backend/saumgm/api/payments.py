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

"""Payments received, contact balances and bank deposits."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
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
    conflict,
    ensure_current,
    get_owned,
    paginate,
    set_archived,
)
from saumgm.api.deps import Auth, DbSession, Editor, Owner, Reader
from saumgm.models import Deposit, Invoice, Organization, Party, Payment
from saumgm.schemas.money import (
    AllocationOut,
    DepositCreate,
    DepositItemOut,
    DepositOut,
    DepositPatch,
    PartyBalanceOut,
    PaymentCreate,
    PaymentOut,
    PaymentPatch,
)
from saumgm.services import payments as service

router = APIRouter(tags=["payments"])


def _org(db: Session, auth: Auth) -> Organization:
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    return org


@dataclass
class Lookups:
    """Contact names and invoice numbers loaded once for a whole list."""

    parties: dict[int, str]
    numbers: dict[int, str | None]

    @classmethod
    def load(cls, db: Session, payments: Sequence[Payment]) -> "Lookups":
        party_ids = {p.party_id for p in payments}
        invoice_ids = {a.invoice_id for p in payments for a in p.allocations}
        parties = {
            pid: name
            for pid, name in db.execute(select(Party.id, Party.name).where(Party.id.in_(party_ids)))
        }
        numbers = {
            iid: number
            for iid, number in db.execute(
                select(Invoice.id, Invoice.number).where(Invoice.id.in_(invoice_ids))
            )
        }
        return cls(parties, numbers)


def payment_out(db: Session, payment: Payment, lookups: Lookups | None = None) -> PaymentOut:
    lookups = lookups or Lookups.load(db, [payment])
    numbers = lookups.numbers
    return PaymentOut(
        id=payment.id,
        party_id=payment.party_id,
        party_name=lookups.parties.get(payment.party_id, ""),
        received_date=payment.received_date,
        amount=payment.amount,
        unapplied=service.unapplied(payment),
        method=payment.method,
        channel=payment.channel,
        reference=payment.reference,
        notes=payment.notes,
        deposit_id=payment.deposit_id,
        is_historical=payment.is_historical,
        archived_at=payment.archived_at,
        allocations=[
            AllocationOut(
                invoice_id=a.invoice_id, invoice_number=numbers.get(a.invoice_id), amount=a.amount
            )
            for a in payment.allocations
        ],
    )


def _allocations(body: PaymentCreate | PaymentPatch) -> list[service.Allocation] | None:
    if body.allocations is None:
        return None
    return [service.Allocation(a.invoice_id, a.amount) for a in body.allocations]


# -- payments -------------------------------------------------------------------------------------


@router.get("/payments")
def list_payments(
    auth: Reader,
    db: DbSession,
    party_id: int | None = None,
    undeposited: bool = Query(False, description="Only payments waiting to be deposited"),
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    archived: ArchiveFilter = ArchiveFilter.CURRENT,
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[PaymentOut]:
    stmt: Any = (
        select(Payment)
        .where(Payment.organization_id == auth.organization_id)
        .order_by(Payment.received_date.desc(), Payment.id.desc())
    )
    stmt = apply_archive_filter(stmt, Payment, archived)
    if party_id is not None:
        stmt = stmt.where(Payment.party_id == party_id)
    if undeposited:
        stmt = stmt.where(Payment.deposit_id.is_(None), Payment.is_historical.is_(False))
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Payment.reference.ilike(pattern), Payment.notes.ilike(pattern)))
    if date_from is not None:
        stmt = stmt.where(Payment.received_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Payment.received_date <= date_to)
    items, total = paginate(db, stmt.options(selectinload(Payment.allocations)), limit, offset)
    lookups = Lookups.load(db, items)
    return Page(
        items=[payment_out(db, p, lookups) for p in items], total=total, limit=limit, offset=offset
    )


@router.post("/payments", status_code=status.HTTP_201_CREATED)
def receive_payment(body: PaymentCreate, auth: Editor, db: DbSession) -> PaymentOut:
    party = get_owned(db, Party, body.party_id, auth.organization_id)
    try:
        payment = service.receive_payment(
            db,
            _org(db, auth),
            party,
            received_date=body.received_date,
            amount=body.amount,
            method=body.method,
            channel=body.channel,
            reference=body.reference,
            notes=body.notes,
            allocations=_allocations(body),
            auto_allocate=body.auto_allocate,
        )
    except service.PaymentError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    return payment_out(db, payment)


@router.get("/payments/{payment_id}")
def get_payment(payment_id: int, auth: Reader, db: DbSession) -> PaymentOut:
    return payment_out(db, get_owned(db, Payment, payment_id, auth.organization_id))


@router.patch("/payments/{payment_id}")
def update_payment(payment_id: int, body: PaymentPatch, auth: Editor, db: DbSession) -> PaymentOut:
    payment = get_owned(db, Payment, payment_id, auth.organization_id)
    ensure_current(payment)
    changes = body.model_dump(exclude_unset=True, exclude={"allocations", "reallocate"})
    try:
        service.update_payment(
            db, _org(db, auth), payment, changes, _allocations(body), body.reallocate
        )
    except service.PaymentError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    return payment_out(db, payment)


@router.delete("/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment(payment_id: int, auth: Editor, db: DbSession) -> None:
    payment = get_owned(db, Payment, payment_id, auth.organization_id)
    ensure_current(payment)
    try:
        service.delete_payment(db, payment)
    except service.PaymentError as exc:
        raise conflict(str(exc)) from None
    db.commit()


@router.post("/payments/{payment_id}/archive")
def archive_payment(payment_id: int, auth: Editor, db: DbSession) -> PaymentOut:
    payment = get_owned(db, Payment, payment_id, auth.organization_id)
    set_archived(payment, True)
    db.commit()
    return payment_out(db, payment)


@router.post("/payments/{payment_id}/unarchive")
def unarchive_payment(payment_id: int, auth: Owner, db: DbSession) -> PaymentOut:
    payment = get_owned(db, Payment, payment_id, auth.organization_id)
    set_archived(payment, False)
    db.commit()
    return payment_out(db, payment)


@router.get("/contacts/{party_id}/balance")
def contact_balance(party_id: int, auth: Reader, db: DbSession) -> PartyBalanceOut:
    party = get_owned(db, Party, party_id, auth.organization_id)
    balance = service.party_balance(db, _org(db, auth), party.id)
    return PartyBalanceOut(
        receivable=balance.receivable,
        overdue=balance.overdue,
        open_invoices=balance.open_invoices,
        unapplied_credit=balance.unapplied_credit,
        net=balance.net,
    )


# -- deposits -------------------------------------------------------------------------------------


def deposit_out(db: Session, deposit: Deposit) -> DepositOut:
    return DepositOut(
        id=deposit.id,
        deposit_date=deposit.deposit_date,
        bank_party_id=deposit.bank_party_id,
        notes=deposit.notes,
        total=service.deposit_total(db, deposit),
        payments=[payment_out(db, p) for p in deposit.payments],
        items=[
            DepositItemOut(id=i.id, amount=i.amount, description=i.description)
            for i in deposit.items
        ],
        archived_at=deposit.archived_at,
    )


def _items(body: DepositCreate | DepositPatch) -> list[service.ExtraItem] | None:
    if body.items is None:
        return None
    return [service.ExtraItem(i.amount, i.description) for i in body.items]


def _check_bank(db: Session, auth: Auth, bank_party_id: int | None) -> None:
    if bank_party_id is not None:
        get_owned(db, Party, bank_party_id, auth.organization_id)


@router.get("/deposits")
def list_deposits(
    auth: Reader,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    archived: ArchiveFilter = ArchiveFilter.CURRENT,
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[DepositOut]:
    stmt: Any = (
        select(Deposit)
        .where(Deposit.organization_id == auth.organization_id)
        .order_by(Deposit.deposit_date.desc(), Deposit.id.desc())
    )
    stmt = apply_archive_filter(stmt, Deposit, archived)
    if date_from is not None:
        stmt = stmt.where(Deposit.deposit_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Deposit.deposit_date <= date_to)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=[deposit_out(db, d) for d in items], total=total, limit=limit, offset=offset)


@router.post("/deposits", status_code=status.HTTP_201_CREATED)
def create_deposit(body: DepositCreate, auth: Editor, db: DbSession) -> DepositOut:
    _check_bank(db, auth, body.bank_party_id)
    try:
        deposit = service.create_deposit(
            db,
            _org(db, auth),
            deposit_date=body.deposit_date,
            bank_party_id=body.bank_party_id,
            notes=body.notes,
            payment_ids=body.payment_ids,
            items=_items(body) or [],
        )
    except service.PaymentError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    db.refresh(deposit)
    return deposit_out(db, deposit)


@router.get("/deposits/{deposit_id}")
def get_deposit(deposit_id: int, auth: Reader, db: DbSession) -> DepositOut:
    return deposit_out(db, get_owned(db, Deposit, deposit_id, auth.organization_id))


@router.patch("/deposits/{deposit_id}")
def update_deposit(deposit_id: int, body: DepositPatch, auth: Editor, db: DbSession) -> DepositOut:
    deposit = get_owned(db, Deposit, deposit_id, auth.organization_id)
    ensure_current(deposit)
    _check_bank(db, auth, body.bank_party_id)
    changes = body.model_dump(exclude_unset=True, exclude={"payment_ids", "items"})
    try:
        service.update_deposit(db, _org(db, auth), deposit, changes, body.payment_ids, _items(body))
    except service.PaymentError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    db.refresh(deposit)
    return deposit_out(db, deposit)


@router.delete("/deposits/{deposit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deposit(deposit_id: int, auth: Editor, db: DbSession) -> None:
    deposit = get_owned(db, Deposit, deposit_id, auth.organization_id)
    ensure_current(deposit)
    service.delete_deposit(db, deposit)
    db.commit()


@router.post("/deposits/{deposit_id}/archive")
def archive_deposit(deposit_id: int, auth: Editor, db: DbSession) -> DepositOut:
    deposit = get_owned(db, Deposit, deposit_id, auth.organization_id)
    set_archived(deposit, True)
    db.commit()
    return deposit_out(db, deposit)


@router.post("/deposits/{deposit_id}/unarchive")
def unarchive_deposit(deposit_id: int, auth: Owner, db: DbSession) -> DepositOut:
    deposit = get_owned(db, Deposit, deposit_id, auth.organization_id)
    set_archived(deposit, False)
    db.commit()
    return deposit_out(db, deposit)
