"""Expenses: purchases and costs split over expense accounts."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, status
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
    paginate,
    set_archived,
)
from saumgm.api.deps import Auth, DbSession, Editor, Owner, Reader
from saumgm.models import Account, Expense, ExpenseLine, Organization, Party
from saumgm.schemas.money import (
    ExpenseCreate,
    ExpenseLineIn,
    ExpenseLineOut,
    ExpenseOut,
    ExpensePatch,
)
from saumgm.services.money import ZERO
from saumgm.timeutil import today_in

router = APIRouter(prefix="/expenses", tags=["expenses"])


@dataclass
class Lookups:
    """Names and accounts loaded once for a whole list instead of once per expense."""

    parties: dict[int, str]
    accounts: dict[int, Account]

    @classmethod
    def load(cls, db: Session, expenses: Sequence[Expense]) -> "Lookups":
        party_ids = {pid for e in expenses for pid in (e.vendor_party_id, e.for_party_id) if pid}
        account_ids = {line.account_id for e in expenses for line in e.lines}
        parties = {
            pid: name
            for pid, name in db.execute(select(Party.id, Party.name).where(Party.id.in_(party_ids)))
        }
        accounts = {a.id: a for a in db.scalars(select(Account).where(Account.id.in_(account_ids)))}
        return cls(parties, accounts)


def expense_out(db: Session, expense: Expense, lookups: Lookups | None = None) -> ExpenseOut:
    lookups = lookups or Lookups.load(db, [expense])
    accounts = lookups.accounts

    def name(party_id: int | None) -> str | None:
        return lookups.parties.get(party_id) if party_id else None

    return ExpenseOut(
        id=expense.id,
        expense_date=expense.expense_date,
        entered_date=expense.entered_date,
        vendor_party_id=expense.vendor_party_id,
        vendor_name=name(expense.vendor_party_id),
        for_party_id=expense.for_party_id,
        for_name=name(expense.for_party_id),
        reference=expense.reference,
        description=expense.description,
        total=sum((line.amount for line in expense.lines), ZERO),
        lines=[
            ExpenseLineOut(
                id=line.id,
                account_id=line.account_id,
                account_code=accounts[line.account_id].code,
                account_name=accounts[line.account_id].name,
                amount=line.amount,
                description=line.description,
            )
            for line in expense.lines
        ],
        archived_at=expense.archived_at,
        legacy_data=expense.legacy_data,
    )


def _lines(db: Session, auth: Auth, lines: list[ExpenseLineIn]) -> list[ExpenseLine]:
    result = []
    for order, line in enumerate(lines):
        account = get_owned(db, Account, line.account_id, auth.organization_id)
        if not account.is_active:
            raise conflict(f"Account {account.code} is inactive")
        result.append(
            ExpenseLine(
                account_id=account.id,
                amount=line.amount,
                description=line.description,
                sort_order=order,
            )
        )
    return result


def _check_parties(db: Session, auth: Auth, *party_ids: int | None) -> None:
    for party_id in party_ids:
        if party_id is not None:
            get_owned(db, Party, party_id, auth.organization_id)


@router.get("")
def list_expenses(
    auth: Reader,
    db: DbSession,
    q: str | None = None,
    vendor_party_id: int | None = None,
    for_party_id: int | None = None,
    account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    archived: ArchiveFilter = ArchiveFilter.CURRENT,
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[ExpenseOut]:
    stmt: Any = (
        select(Expense)
        .where(Expense.organization_id == auth.organization_id)
        .order_by(Expense.expense_date.desc(), Expense.id.desc())
    )
    stmt = apply_archive_filter(stmt, Expense, archived)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Expense.description.ilike(pattern), Expense.reference.ilike(pattern)))
    if vendor_party_id is not None:
        stmt = stmt.where(Expense.vendor_party_id == vendor_party_id)
    if for_party_id is not None:
        stmt = stmt.where(Expense.for_party_id == for_party_id)
    if account_id is not None:
        stmt = stmt.where(Expense.lines.any(ExpenseLine.account_id == account_id))
    if date_from is not None:
        stmt = stmt.where(Expense.expense_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Expense.expense_date <= date_to)
    items, total = paginate(db, stmt.options(selectinload(Expense.lines)), limit, offset)
    lookups = Lookups.load(db, items)
    return Page(
        items=[expense_out(db, e, lookups) for e in items], total=total, limit=limit, offset=offset
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_expense(body: ExpenseCreate, auth: Editor, db: DbSession) -> ExpenseOut:
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    _check_parties(db, auth, body.vendor_party_id, body.for_party_id)
    expense = Expense(
        organization_id=auth.organization_id,
        expense_date=body.expense_date,
        entered_date=body.entered_date or today_in(org.timezone),
        vendor_party_id=body.vendor_party_id,
        for_party_id=body.for_party_id if body.for_party_id is not None else org.self_party_id,
        reference=body.reference,
        description=body.description,
    )
    expense.lines = _lines(db, auth, body.lines)
    db.add(expense)
    db.flush()
    db.commit()
    return expense_out(db, expense)


@router.get("/{expense_id}")
def get_expense(expense_id: int, auth: Reader, db: DbSession) -> ExpenseOut:
    return expense_out(db, get_owned(db, Expense, expense_id, auth.organization_id))


@router.patch("/{expense_id}")
def update_expense(expense_id: int, body: ExpensePatch, auth: Editor, db: DbSession) -> ExpenseOut:
    expense = get_owned(db, Expense, expense_id, auth.organization_id)
    ensure_current(expense)
    _check_parties(db, auth, body.vendor_party_id, body.for_party_id)
    apply_changes(expense, body, exclude={"lines"})
    if body.lines is not None:
        expense.lines = _lines(db, auth, body.lines)
    db.flush()
    db.commit()
    return expense_out(db, expense)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: int, auth: Editor, db: DbSession) -> None:
    expense = get_owned(db, Expense, expense_id, auth.organization_id)
    ensure_current(expense)
    db.delete(expense)
    db.commit()


@router.post("/{expense_id}/archive")
def archive_expense(expense_id: int, auth: Editor, db: DbSession) -> ExpenseOut:
    expense = get_owned(db, Expense, expense_id, auth.organization_id)
    set_archived(expense, True)
    db.commit()
    return expense_out(db, expense)


@router.post("/{expense_id}/unarchive")
def unarchive_expense(expense_id: int, auth: Owner, db: DbSession) -> ExpenseOut:
    expense = get_owned(db, Expense, expense_id, auth.organization_id)
    set_archived(expense, False)
    db.commit()
    return expense_out(db, expense)
