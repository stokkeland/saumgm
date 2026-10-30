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

"""Bank and credit-card accounts, their registers, transfers and reconciliations."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from saumgm.api.common import LimitParam, OffsetParam, Page, conflict, get_owned, paginate
from saumgm.api.deps import Auth, DbSession, Editor, Owner, Reader
from saumgm.enums import BankEntryStatus
from saumgm.models import (
    Account,
    BankAccount,
    BankEntry,
    BankReconciliation,
    Organization,
    Party,
    User,
)
from saumgm.schemas.banking import (
    BankAccountCreate,
    BankAccountOut,
    BankAccountPatch,
    BankEntryCreate,
    BankEntryOut,
    BankEntryPatch,
    ReconcileIn,
    ReconciliationOut,
    ToExpenseIn,
    TransferIn,
    TransferOut,
)
from saumgm.services import banking as service

router = APIRouter(tags=["banking"])


def _org(db: Session, auth: Auth) -> Organization:
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    return org


def accounts_out(db: Session, accounts: list[BankAccount]) -> list[BankAccountOut]:
    sums = service.balances(db, accounts)
    last = service.last_reconciliations(db, (a.id for a in accounts))
    party_ids = {a.party_id for a in accounts if a.party_id}
    names = dict(db.execute(select(Party.id, Party.name).where(Party.id.in_(party_ids))).all())
    out = []
    for a in accounts:
        rec = last.get(a.id)
        out.append(
            BankAccountOut(
                id=a.id,
                party_id=a.party_id,
                bank_name=names.get(a.party_id) if a.party_id else None,
                name=a.name,
                kind=a.kind,
                number_last4=a.number_last4,
                opening_date=a.opening_date,
                opening_balance=a.opening_balance,
                is_active=a.is_active,
                notes=a.notes,
                balance=sums[a.id].balance,
                cleared_balance=sums[a.id].cleared,
                reconciled_balance=sums[a.id].reconciled,
                uncleared_count=sums[a.id].uncleared_count,
                last_reconciled_date=rec.statement_date if rec else None,
                last_statement_balance=rec.statement_balance if rec else None,
            )
        )
    return out


def entries_out(db: Session, entries: list[BankEntry]) -> list[BankEntryOut]:
    running: dict[int, Any] = {}
    for account_id in {e.bank_account_id for e in entries}:
        account = db.get(BankAccount, account_id)
        assert account is not None
        running |= service.running_balances(db, account)
    account_ids = {e.account_id for e in entries if e.account_id}
    categories = {
        a.id: f"{a.code} {a.name}"
        for a in db.scalars(select(Account).where(Account.id.in_(account_ids)))
    }
    other_ids = {e.transfer_entry_id for e in entries if e.transfer_entry_id}
    others = dict(
        db.execute(
            select(BankEntry.id, BankEntry.bank_account_id).where(BankEntry.id.in_(other_ids))
        ).all()
    )
    names = dict(
        db.execute(
            select(BankAccount.id, BankAccount.name).where(BankAccount.id.in_(set(others.values())))
        ).all()
    )
    return [
        BankEntryOut(
            id=e.id,
            bank_account_id=e.bank_account_id,
            entry_date=e.entry_date,
            amount=e.amount,
            payee=e.payee,
            description=e.description,
            reference=e.reference,
            account_id=e.account_id,
            account_name=categories.get(e.account_id) if e.account_id else None,
            status=e.status,
            kind=e.kind,
            deposit_id=e.deposit_id,
            expense_id=e.expense_id,
            transfer_entry_id=e.transfer_entry_id,
            transfer_account_id=others.get(e.transfer_entry_id) if e.transfer_entry_id else None,
            transfer_account_name=(
                names.get(others[e.transfer_entry_id]) if e.transfer_entry_id in others else None
            ),
            reconciliation_id=e.reconciliation_id,
            running_balance=running[e.id],
        )
        for e in entries
    ]


def _check_refs(db: Session, auth: Auth, party_id: int | None = None,
                account_id: int | None = None) -> None:  # fmt: skip
    if party_id is not None:
        get_owned(db, Party, party_id, auth.organization_id)
    if account_id is not None:
        get_owned(db, Account, account_id, auth.organization_id)


# -- accounts -------------------------------------------------------------------------------------


@router.get("/bank-accounts")
def list_bank_accounts(
    auth: Reader,
    db: DbSession,
    active: bool | None = Query(True, description="Empty: open and closed accounts"),
) -> list[BankAccountOut]:
    stmt = select(BankAccount).where(BankAccount.organization_id == auth.organization_id)
    if active is not None:
        stmt = stmt.where(BankAccount.is_active.is_(active))
    return accounts_out(db, list(db.scalars(stmt.order_by(BankAccount.name))))


@router.post("/bank-accounts", status_code=status.HTTP_201_CREATED)
def create_bank_account(body: BankAccountCreate, auth: Editor, db: DbSession) -> BankAccountOut:
    _check_refs(db, auth, party_id=body.party_id)
    account = BankAccount(organization_id=auth.organization_id, **body.model_dump())
    db.add(account)
    db.commit()
    return accounts_out(db, [account])[0]


@router.get("/bank-accounts/{account_id}")
def get_bank_account(account_id: int, auth: Reader, db: DbSession) -> BankAccountOut:
    return accounts_out(db, [get_owned(db, BankAccount, account_id, auth.organization_id)])[0]


@router.patch("/bank-accounts/{account_id}")
def update_bank_account(
    account_id: int, body: BankAccountPatch, auth: Editor, db: DbSession
) -> BankAccountOut:
    account = get_owned(db, BankAccount, account_id, auth.organization_id)
    changes = body.model_dump(exclude_unset=True)
    _check_refs(db, auth, party_id=changes.get("party_id"))
    for key in ("name", "kind", "opening_date", "opening_balance", "is_active"):
        if key in changes and changes[key] is None:
            del changes[key]  # required fields: null means "leave as it is"
    moved = {k for k in ("opening_date", "opening_balance") if k in changes
             and changes[k] != getattr(account, k)}  # fmt: skip
    try:
        if moved and service.has_reconciliations(db, account):
            raise service.BankingError(
                "The account has reconciled statements: undo them before changing where the "
                "register starts"
            )
        if "opening_date" in moved:
            service.check_start(db, account, changes["opening_date"])
    except service.BankingError as exc:
        raise conflict(str(exc)) from None
    for key, value in changes.items():
        setattr(account, key, value)
    db.commit()
    return accounts_out(db, [account])[0]


@router.delete("/bank-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank_account(account_id: int, auth: Owner, db: DbSession) -> None:
    """Only an account nothing refers to yet; otherwise mark it inactive (closed)."""
    account = get_owned(db, BankAccount, account_id, auth.organization_id)
    if service.in_use(db, account):
        raise conflict("The account has register lines, deposits or expenses; close it instead")
    db.delete(account)
    db.commit()


# -- register -------------------------------------------------------------------------------------


@router.get("/bank-accounts/{account_id}/entries")
def list_entries(
    account_id: int,
    auth: Reader,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    status_filter: BankEntryStatus | None = Query(None, alias="status"),
    q: str | None = Query(None, description="Payee, description or reference"),
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[BankEntryOut]:
    """Newest first, each line with the balance after it."""
    get_owned(db, BankAccount, account_id, auth.organization_id)
    stmt: Any = select(BankEntry).where(BankEntry.bank_account_id == account_id)
    if date_from is not None:
        stmt = stmt.where(BankEntry.entry_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(BankEntry.entry_date <= date_to)
    if status_filter is not None:
        stmt = stmt.where(BankEntry.status == status_filter)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                BankEntry.payee.ilike(pattern),
                BankEntry.description.ilike(pattern),
                BankEntry.reference.ilike(pattern),
            )
        )
    stmt = stmt.order_by(BankEntry.entry_date.desc(), BankEntry.id.desc())
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=entries_out(db, list(items)), total=total, limit=limit, offset=offset)


@router.post("/bank-accounts/{account_id}/entries", status_code=status.HTTP_201_CREATED)
def create_entry(
    account_id: int, body: BankEntryCreate, auth: Editor, db: DbSession
) -> BankEntryOut:
    """A free entry (fee, interest, owner draw...) or a balance adjustment."""
    account = get_owned(db, BankAccount, account_id, auth.organization_id)
    _check_refs(db, auth, account_id=body.account_id)
    fields = body.model_dump(exclude={"kind"})
    try:
        entry = service.create_entry(db, account, kind=body.kind, **fields)
    except service.BankingError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    return entries_out(db, [entry])[0]


@router.patch("/bank-entries/{entry_id}")
def update_entry(entry_id: int, body: BankEntryPatch, auth: Editor, db: DbSession) -> BankEntryOut:
    entry = get_owned(db, BankEntry, entry_id, auth.organization_id)
    changes = body.model_dump(exclude_unset=True)
    for key in ("entry_date", "amount", "status"):
        if key in changes and changes[key] is None:
            del changes[key]
    _check_refs(db, auth, account_id=changes.get("account_id"))
    try:
        service.update_entry(db, entry, changes)
    except service.BankingError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    return entries_out(db, [entry])[0]


@router.delete("/bank-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, auth: Editor, db: DbSession) -> None:
    """A free entry, or both sides of a transfer."""
    entry = get_owned(db, BankEntry, entry_id, auth.organization_id)
    try:
        service.delete_entry(db, entry)
    except service.BankingError as exc:
        raise conflict(str(exc)) from None
    db.commit()


@router.post("/bank-entries/{entry_id}/expense")
def entry_to_expense(entry_id: int, body: ToExpenseIn, auth: Editor, db: DbSession) -> BankEntryOut:
    """Make an expense (paid from this account) of a free line; the line stays, linked."""
    entry = get_owned(db, BankEntry, entry_id, auth.organization_id)
    _check_refs(db, auth, party_id=body.vendor_party_id, account_id=body.account_id)
    try:
        service.to_expense(
            db, _org(db, auth), entry, account_id=body.account_id,
            vendor_party_id=body.vendor_party_id,
        )  # fmt: skip
    except service.BankingError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    return entries_out(db, [entry])[0]


@router.post("/bank-transfers", status_code=status.HTTP_201_CREATED)
def create_transfer(body: TransferIn, auth: Editor, db: DbSession) -> TransferOut:
    """Money between two accounts, both sides at once. Paying a credit card is a transfer."""
    source = get_owned(db, BankAccount, body.from_account_id, auth.organization_id)
    target = get_owned(db, BankAccount, body.to_account_id, auth.organization_id)
    try:
        out, into = service.transfer(
            db, _org(db, auth), source, target, entry_date=body.entry_date, amount=body.amount,
            description=body.description, reference=body.reference,
        )  # fmt: skip
    except service.BankingError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    first, second = entries_out(db, [out, into])
    return TransferOut(out=first, into=second)


# -- reconciling ----------------------------------------------------------------------------------


def reconciliation_out(db: Session, rec: BankReconciliation) -> ReconciliationOut:
    user = db.get(User, rec.created_by_user_id) if rec.created_by_user_id else None
    count = db.scalar(
        select(func.count()).select_from(BankEntry).where(BankEntry.reconciliation_id == rec.id)
    )
    return ReconciliationOut(
        id=rec.id,
        bank_account_id=rec.bank_account_id,
        statement_date=rec.statement_date,
        statement_balance=rec.statement_balance,
        created_at=rec.created_at,
        created_by=user.display_name if user else None,
        entries=count or 0,
    )


@router.get("/bank-accounts/{account_id}/reconciliations")
def list_reconciliations(account_id: int, auth: Reader, db: DbSession) -> list[ReconciliationOut]:
    get_owned(db, BankAccount, account_id, auth.organization_id)
    recs = db.scalars(
        select(BankReconciliation)
        .where(BankReconciliation.bank_account_id == account_id)
        .order_by(BankReconciliation.statement_date.desc(), BankReconciliation.id.desc())
    )
    return [reconciliation_out(db, r) for r in recs]


@router.post("/bank-accounts/{account_id}/reconciliations", status_code=status.HTTP_201_CREATED)
def reconcile(account_id: int, body: ReconcileIn, auth: Editor, db: DbSession) -> ReconciliationOut:
    """Match the register with a statement: the ticked lines become reconciled."""
    account = get_owned(db, BankAccount, account_id, auth.organization_id)
    try:
        rec = service.reconcile(
            db, account, statement_date=body.statement_date,
            statement_balance=body.statement_balance, entry_ids=body.entry_ids,
            user_id=auth.user.id,
        )  # fmt: skip
    except service.BankingError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    return reconciliation_out(db, rec)


@router.delete("/bank-reconciliations/{rec_id}", status_code=status.HTTP_204_NO_CONTENT)
def undo_reconciliation(rec_id: int, auth: Owner, db: DbSession) -> None:
    """Undo the latest reconciliation of an account; its lines go back to cleared."""
    rec = get_owned(db, BankReconciliation, rec_id, auth.organization_id)
    try:
        service.undo_reconciliation(db, rec)
    except service.BankingError as exc:
        raise conflict(str(exc)) from None
    db.commit()
