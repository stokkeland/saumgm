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

"""Bank registers: balances, the lines that follow deposits, expenses and transfers, and
reconciling with a statement.

Only three things write register lines on their own: a deposit into an account, an expense paid
from an account, and a transfer (both sides). Everything else is a free entry. A reconciled line
is locked: neither it nor the deposit or expense behind it can change its amount, date or
account until the reconciliation is undone.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saumgm.enums import BankEntryKind, BankEntryStatus
from saumgm.models import (
    BankAccount,
    BankEntry,
    BankReconciliation,
    Deposit,
    Expense,
    ExpenseLine,
    Organization,
    Party,
)
from saumgm.models.base import ZERO
from saumgm.services.payments import deposit_total
from saumgm.timeutil import today_in, utcnow

# Like invoices: a statement matches when the difference is under half a cent.
TOLERANCE = Decimal("0.005")
CLEARED = (BankEntryStatus.CLEARED, BankEntryStatus.RECONCILED)


def _cents(value: Decimal) -> str:
    return f"{value:,.2f}"


class BankingError(Exception):
    """Not allowed: a date before the register starts, a locked line, a statement that does
    not match."""


@dataclass(frozen=True)
class Balances:
    balance: Decimal  # everything recorded
    cleared: Decimal  # what the bank has seen (cleared and reconciled lines)
    reconciled: Decimal
    uncleared_count: int


def balances(session: Session, accounts: Sequence[BankAccount]) -> dict[int, Balances]:
    ids = [a.id for a in accounts]
    sums: dict[int, dict[BankEntryStatus, tuple[Decimal, int]]] = {i: {} for i in ids}
    if ids:
        rows = session.execute(
            select(
                BankEntry.bank_account_id,
                BankEntry.status,
                func.coalesce(func.sum(BankEntry.amount), 0),
                func.count(),
            )
            .where(BankEntry.bank_account_id.in_(ids))
            .group_by(BankEntry.bank_account_id, BankEntry.status)
        ).all()
        for account_id, status, amount, count in rows:
            sums[account_id][status] = (Decimal(amount), count)

    def added(by_status: dict[BankEntryStatus, tuple[Decimal, int]],
              *statuses: BankEntryStatus) -> Decimal:  # fmt: skip
        return sum((by_status.get(s, (ZERO, 0))[0] for s in statuses), ZERO)

    out = {}
    for account in accounts:
        by_status = sums[account.id]
        out[account.id] = Balances(
            balance=account.opening_balance + added(by_status, *BankEntryStatus),
            cleared=account.opening_balance + added(by_status, *CLEARED),
            reconciled=account.opening_balance + added(by_status, BankEntryStatus.RECONCILED),
            uncleared_count=by_status.get(BankEntryStatus.UNCLEARED, (ZERO, 0))[1],
        )
    return out


def last_reconciliations(
    session: Session, account_ids: Iterable[int]
) -> dict[int, BankReconciliation]:
    ids = list(account_ids)
    if not ids:
        return {}
    latest = {}
    for rec in session.scalars(
        select(BankReconciliation)
        .where(BankReconciliation.bank_account_id.in_(ids))
        .order_by(BankReconciliation.statement_date, BankReconciliation.id)
    ):
        latest[rec.bank_account_id] = rec
    return latest


def running_balances(session: Session, account: BankAccount) -> dict[int, Decimal]:
    """The balance after each line, in register order (date, then entry order)."""
    running = account.opening_balance
    out = {}
    for entry_id, amount in session.execute(
        select(BankEntry.id, BankEntry.amount)
        .where(BankEntry.bank_account_id == account.id)
        .order_by(BankEntry.entry_date, BankEntry.id)
    ):
        running += amount
        out[entry_id] = running
    return out


# -- checks ---------------------------------------------------------------------------------------


def check_date(account: BankAccount, day: date | None) -> None:
    if day is None:
        raise BankingError("A register line needs a date")
    if day < account.opening_date:
        raise BankingError(
            f"{account.name}: the register starts on {account.opening_date.isoformat()} "
            "(the opening balance); move the start date back to enter older lines"
        )


def check_open(account: BankAccount) -> None:
    if not account.is_active:
        raise BankingError(f"{account.name} is closed (inactive)")


def _locked(entry: BankEntry) -> bool:
    return entry.status == BankEntryStatus.RECONCILED


def _refuse_locked(entry: BankEntry, what: str) -> None:
    if _locked(entry):
        raise BankingError(
            f"The bank line of this {what} is reconciled; undo that reconciliation first"
        )


# -- lines that follow a deposit or an expense ----------------------------------------------------


def _set_line(
    session: Session,
    entry: BankEntry | None,
    account: BankAccount,
    what: str,
    *,
    entry_date: date | None,
    amount: Decimal,
    **fields: object,
) -> BankEntry:
    check_date(account, entry_date)
    assert entry_date is not None
    if entry is None:
        entry = BankEntry(organization_id=account.organization_id)
        session.add(entry)
    elif _locked(entry) and (
        entry.bank_account_id != account.id
        or entry.entry_date != entry_date
        or entry.amount != amount
    ):
        _refuse_locked(entry, what)
    entry.bank_account_id = account.id
    entry.entry_date = entry_date
    entry.amount = amount
    for key, value in fields.items():
        setattr(entry, key, value)
    return entry


def _account(session: Session, org_id: int, account_id: int) -> BankAccount:
    account = session.get(BankAccount, account_id)
    if account is None or account.organization_id != org_id:
        raise BankingError("No such bank account")
    return account


def sync_deposit(session: Session, deposit: Deposit) -> None:
    """Make the deposit's register line match it (or remove it when no account is set)."""
    entry = session.scalars(select(BankEntry).where(BankEntry.deposit_id == deposit.id)).first()
    if deposit.bank_account_id is None:
        if entry is not None:
            _refuse_locked(entry, "deposit")
            session.delete(entry)
        session.flush()
        return
    account = _account(session, deposit.organization_id, deposit.bank_account_id)
    if entry is None or entry.bank_account_id != account.id:
        check_open(account)
    if account.party_id is not None:
        deposit.bank_party_id = account.party_id
    session.flush()
    _set_line(
        session,
        entry,
        account,
        "deposit",
        entry_date=deposit.deposit_date,
        amount=deposit_total(session, deposit),
        kind=BankEntryKind.DEPOSIT,
        deposit_id=deposit.id,
        description=f"Deposit{': ' + deposit.notes if deposit.notes else ''}"[:500],
    )
    session.flush()


def sync_expense(session: Session, expense: Expense) -> None:
    """Make the expense's register line match it (or remove it when it was not paid from an
    account)."""
    entry = session.scalars(select(BankEntry).where(BankEntry.expense_id == expense.id)).first()
    if expense.paid_from_account_id is None:
        if entry is not None:
            _refuse_locked(entry, "expense")
            session.delete(entry)
        session.flush()
        return
    account = _account(session, expense.organization_id, expense.paid_from_account_id)
    if entry is None or entry.bank_account_id != account.id:
        check_open(account)
    session.flush()
    total = sum((line.amount for line in expense.lines), ZERO)
    accounts = {line.account_id for line in expense.lines}
    vendor = session.get(Party, expense.vendor_party_id) if expense.vendor_party_id else None
    _set_line(
        session,
        entry,
        account,
        "expense",
        entry_date=expense.expense_date,
        amount=-total,
        kind=BankEntryKind.EXPENSE,
        expense_id=expense.id,
        payee=vendor.name if vendor else None,
        reference=expense.reference,
        description=(expense.description or "")[:500] or None,
        account_id=accounts.pop() if len(accounts) == 1 else None,
    )
    session.flush()


def before_delete(session: Session, *, deposit: Deposit | None = None,
                  expense: Expense | None = None) -> None:  # fmt: skip
    """Remove the register line of a deposit or expense about to be deleted."""
    if deposit is not None:
        stmt = select(BankEntry).where(BankEntry.deposit_id == deposit.id)
        what = "deposit"
    else:
        assert expense is not None
        stmt = select(BankEntry).where(BankEntry.expense_id == expense.id)
        what = "expense"
    for entry in session.scalars(stmt):
        _refuse_locked(entry, what)
        session.delete(entry)
    session.flush()


# -- free entries and transfers -------------------------------------------------------------------


FREE_KINDS = (BankEntryKind.MANUAL, BankEntryKind.ADJUSTMENT)
EDITABLE = ("entry_date", "amount", "payee", "description", "reference", "account_id")


def create_entry(
    session: Session, account: BankAccount, *, kind: BankEntryKind, **fields: object
) -> BankEntry:
    if kind not in FREE_KINDS:
        raise BankingError("Deposits, expenses and transfers make their own lines")
    check_open(account)
    check_date(account, fields.get("entry_date"))  # type: ignore[arg-type]
    if not fields.get("amount"):
        raise BankingError("The amount cannot be zero")
    entry = BankEntry(organization_id=account.organization_id, bank_account_id=account.id,
                      kind=kind, **fields)  # fmt: skip
    session.add(entry)
    session.flush()
    return entry


def update_entry(session: Session, entry: BankEntry, changes: dict[str, object]) -> None:
    """Free entries change freely; a transfer changes both sides; a deposit's or expense's line
    only changes its status (edit the deposit or expense for the rest)."""
    status = changes.pop("status", None)
    if status == BankEntryStatus.RECONCILED:
        raise BankingError("Lines become reconciled by reconciling with a statement")
    if status is not None and _locked(entry):
        raise BankingError("This line is reconciled; undo that reconciliation first")
    changes = {k: v for k, v in changes.items() if getattr(entry, k) != v}
    if changes:
        if entry.kind in (BankEntryKind.DEPOSIT, BankEntryKind.EXPENSE):
            raise BankingError(
                f"This line follows its {entry.kind.value}: change the {entry.kind.value} instead"
            )
        _refuse_locked(entry, "line")
        if "amount" in changes and not changes["amount"]:
            raise BankingError("The amount cannot be zero")
        account = session.get(BankAccount, entry.bank_account_id)
        assert account is not None
        if "entry_date" in changes:
            check_date(account, changes["entry_date"])  # type: ignore[arg-type]
        other = _other_side(session, entry)
        if other is not None:
            _refuse_locked(other, "transfer")
            mirrored = {k: v for k, v in changes.items() if k != "account_id"}
            if "amount" in mirrored:
                mirrored["amount"] = -mirrored["amount"]  # type: ignore[operator]
            if "entry_date" in mirrored:
                other_account = session.get(BankAccount, other.bank_account_id)
                assert other_account is not None
                check_date(other_account, mirrored["entry_date"])  # type: ignore[arg-type]
            for key, value in mirrored.items():
                setattr(other, key, value)
        for key, value in changes.items():
            setattr(entry, key, value)
    if status is not None:
        entry.status = BankEntryStatus(status)  # type: ignore[arg-type]
    session.flush()


def delete_entry(session: Session, entry: BankEntry) -> None:
    if entry.kind in (BankEntryKind.DEPOSIT, BankEntryKind.EXPENSE):
        raise BankingError(
            f"This line follows its {entry.kind.value}: delete the {entry.kind.value}, or "
            "clear its account"
        )
    _refuse_locked(entry, "line")
    other = _other_side(session, entry)
    if other is not None:
        _refuse_locked(other, "transfer")
        other.transfer_entry_id = None
        entry.transfer_entry_id = None
        session.flush()
        session.delete(other)
    session.delete(entry)
    session.flush()


def _other_side(session: Session, entry: BankEntry) -> BankEntry | None:
    if entry.kind != BankEntryKind.TRANSFER or entry.transfer_entry_id is None:
        return None
    return session.get(BankEntry, entry.transfer_entry_id)


def transfer(
    session: Session,
    org: Organization,
    source: BankAccount,
    target: BankAccount,
    *,
    entry_date: date,
    amount: Decimal,
    description: str | None,
    reference: str | None,
) -> tuple[BankEntry, BankEntry]:
    """Money from one account to another; paying the credit card is a transfer to its account."""
    if source.id == target.id:
        raise BankingError("Choose two different accounts")
    if amount <= ZERO:
        raise BankingError("The amount must be more than zero")
    for account in (source, target):
        check_open(account)
        check_date(account, entry_date)
    common = {
        "organization_id": org.id,
        "entry_date": entry_date,
        "kind": BankEntryKind.TRANSFER,
        "reference": reference,
    }
    out = BankEntry(
        bank_account_id=source.id,
        amount=-amount,
        description=description or f"Transfer to {target.name}",
        **common,
    )
    into = BankEntry(
        bank_account_id=target.id,
        amount=amount,
        description=description or f"Transfer from {source.name}",
        **common,
    )
    session.add_all([out, into])
    session.flush()
    out.transfer_entry_id, into.transfer_entry_id = into.id, out.id
    session.flush()
    return out, into


def to_expense(
    session: Session,
    org: Organization,
    entry: BankEntry,
    *,
    account_id: int | None,
    vendor_party_id: int | None,
) -> Expense:
    """Turn a free line (money out) into an expense paid from this account; the line stays,
    linked to it."""
    if entry.kind not in FREE_KINDS:
        raise BankingError("Only a free entry can become an expense")
    if entry.amount >= ZERO:
        raise BankingError("Only money going out can become an expense")
    account_id = account_id or entry.account_id
    if account_id is None:
        raise BankingError("Choose the expense account")
    expense = Expense(
        organization_id=org.id,
        expense_date=entry.entry_date,
        entered_date=today_in(org.timezone),
        vendor_party_id=vendor_party_id,
        for_party_id=org.self_party_id,
        reference=entry.reference,
        description=entry.description or entry.payee,
        paid_from_account_id=entry.bank_account_id,
    )
    expense.lines = [
        ExpenseLine(account_id=account_id, amount=-entry.amount, description=entry.description)
    ]
    session.add(expense)
    session.flush()
    entry.kind = BankEntryKind.EXPENSE
    entry.expense_id = expense.id
    if entry.payee is None and vendor_party_id is not None:
        vendor = session.get(Party, vendor_party_id)
        entry.payee = vendor.name if vendor else None
    entry.account_id = account_id
    session.flush()
    return expense


# -- accounts -------------------------------------------------------------------------------------


def check_start(session: Session, account: BankAccount, opening_date: date) -> None:
    """The start date cannot move past lines already entered, nor past a reconciliation."""
    first = session.scalar(
        select(func.min(BankEntry.entry_date)).where(BankEntry.bank_account_id == account.id)
    )
    if first is not None and opening_date > first:
        raise BankingError(
            f"The register has lines from {first.isoformat()}; the start date cannot be later"
        )


def has_reconciliations(session: Session, account: BankAccount) -> bool:
    return (
        session.scalar(
            select(func.count())
            .select_from(BankReconciliation)
            .where(BankReconciliation.bank_account_id == account.id)
        )
        or 0
    ) > 0


def in_use(session: Session, account: BankAccount) -> bool:
    for model, column in (
        (BankEntry, BankEntry.bank_account_id),
        (Deposit, Deposit.bank_account_id),
        (Expense, Expense.paid_from_account_id),
    ):
        if session.scalar(select(func.count()).select_from(model).where(column == account.id)):
            return True
    return False


# -- reconciling ----------------------------------------------------------------------------------


def reconcile(
    session: Session,
    account: BankAccount,
    *,
    statement_date: date,
    statement_balance: Decimal,
    entry_ids: Sequence[int],
    user_id: int | None,
) -> BankReconciliation:
    """The ticked lines plus everything reconciled before must add up to the statement's
    ending balance; then they are reconciled (locked)."""
    last = last_reconciliations(session, [account.id]).get(account.id)
    if last is not None and statement_date < last.statement_date:
        raise BankingError(
            f"The last statement reconciled was of {last.statement_date.isoformat()}; "
            "this one cannot be older"
        )
    check_date(account, statement_date)
    entries = list(
        session.scalars(select(BankEntry).where(BankEntry.id.in_(set(entry_ids))))
    ) if entry_ids else []  # fmt: skip
    for entry in entries:
        if entry.bank_account_id != account.id:
            raise BankingError("A ticked line belongs to another account")
        if _locked(entry):
            raise BankingError("A ticked line is already reconciled")
        if entry.entry_date > statement_date:
            raise BankingError(
                f"A ticked line is dated {entry.entry_date.isoformat()}, after the statement"
            )
    reconciled = balances(session, [account])[account.id].reconciled
    total = reconciled + sum((e.amount for e in entries), ZERO)
    difference = statement_balance - total
    if abs(difference) >= TOLERANCE:
        raise BankingError(
            f"The ticked lines come to {_cents(total)}, the statement says "
            f"{_cents(statement_balance)}: a difference of "
            f"{_cents(difference)}"
        )
    rec = BankReconciliation(
        organization_id=account.organization_id,
        bank_account_id=account.id,
        statement_date=statement_date,
        statement_balance=statement_balance,
        created_at=utcnow(),
        created_by_user_id=user_id,
    )
    session.add(rec)
    session.flush()
    for entry in entries:
        entry.status = BankEntryStatus.RECONCILED
        entry.reconciliation_id = rec.id
    session.flush()
    return rec


def undo_reconciliation(session: Session, rec: BankReconciliation) -> None:
    """Only the latest one of an account; its lines go back to cleared."""
    last = last_reconciliations(session, [rec.bank_account_id])[rec.bank_account_id]
    if last.id != rec.id:
        raise BankingError("Only the latest reconciliation of an account can be undone")
    for entry in session.scalars(select(BankEntry).where(BankEntry.reconciliation_id == rec.id)):
        entry.status = BankEntryStatus.CLEARED
        entry.reconciliation_id = None
    session.flush()
    session.delete(rec)
    session.flush()
