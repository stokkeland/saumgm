"""Payments (money received), how they are applied to invoices, and bank deposits."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saumgm.enums import InvoiceKind, InvoiceStatus, PaymentChannel, PaymentMethod
from saumgm.models import (
    Deposit,
    DepositItem,
    Invoice,
    Organization,
    Party,
    Payment,
    PaymentAllocation,
)
from saumgm.services import invoices as invoice_service
from saumgm.services.money import ZERO
from saumgm.timeutil import today_in


class PaymentError(Exception):
    pass


@dataclass(frozen=True)
class Allocation:
    invoice_id: int
    amount: Decimal


@dataclass(frozen=True)
class PartyBalance:
    receivable: Decimal
    overdue: Decimal
    open_invoices: int
    unapplied_credit: Decimal

    @property
    def net(self) -> Decimal:
        return self.receivable - self.unapplied_credit


def unapplied(payment: Payment) -> Decimal:
    return payment.amount - sum((a.amount for a in payment.allocations), ZERO)


def open_invoices(session: Session, org: Organization, party_id: int) -> list[Invoice]:
    """Issued invoices of a contact with money still due, oldest due first."""
    candidates = session.scalars(
        select(Invoice)
        .where(
            Invoice.organization_id == org.id,
            Invoice.party_id == party_id,
            Invoice.kind == InvoiceKind.INVOICE,
            Invoice.status == InvoiceStatus.ISSUED,
        )
        .order_by(Invoice.due_date, Invoice.issue_date, Invoice.id)
    ).all()
    infos = invoice_service.balances(session, candidates, today_in(org.timezone))
    return [i for i in candidates if infos[i.id].balance_due > invoice_service.PAID_TOLERANCE]


def _balance_due(session: Session, org: Organization, invoice: Invoice) -> Decimal:
    return invoice_service.balances(session, [invoice], today_in(org.timezone))[
        invoice.id
    ].balance_due


def _set_allocations(
    session: Session,
    org: Organization,
    payment: Payment,
    allocations: Sequence[Allocation] | None,
    auto_allocate: bool,
) -> None:
    # Detach the current allocations first so balances are computed without them.
    payment.allocations = []
    session.flush()
    if allocations is None and auto_allocate:
        remaining = payment.amount
        for invoice in open_invoices(session, org, payment.party_id):
            if remaining <= 0:
                break
            amount = min(remaining, _balance_due(session, org, invoice))
            payment.allocations.append(PaymentAllocation(invoice_id=invoice.id, amount=amount))
            remaining -= amount
        return

    total = ZERO
    for allocation in allocations or []:
        target = session.get(Invoice, allocation.invoice_id)
        if target is None or target.organization_id != org.id:
            raise PaymentError(f"Invoice {allocation.invoice_id} not found")
        invoice = target
        if invoice.party_id != payment.party_id:
            raise PaymentError(f"Invoice {invoice.number} belongs to another contact")
        if invoice.kind != InvoiceKind.INVOICE or invoice.status != InvoiceStatus.ISSUED:
            raise PaymentError(f"Invoice {invoice.number or invoice.id} is not an issued invoice")
        if allocation.amount <= 0:
            raise PaymentError("Applied amounts must be positive")
        due = _balance_due(session, org, invoice)
        if allocation.amount > due + invoice_service.PAID_TOLERANCE:
            raise PaymentError(f"Invoice {invoice.number} has only {due} due")
        total += allocation.amount
        payment.allocations.append(
            PaymentAllocation(invoice_id=invoice.id, amount=allocation.amount)
        )
    if total > payment.amount:
        raise PaymentError("The applied amounts exceed the payment")


def receive_payment(
    session: Session,
    org: Organization,
    party: Party,
    *,
    received_date: date,
    amount: Decimal,
    method: PaymentMethod | None,
    channel: PaymentChannel | None,
    reference: str | None,
    notes: str | None,
    allocations: Sequence[Allocation] | None,
    auto_allocate: bool,
) -> Payment:
    if party.organization_id != org.id:
        raise PaymentError("Contact not found")
    if amount <= 0:
        raise PaymentError("The amount must be positive")
    payment = Payment(
        organization_id=org.id,
        party_id=party.id,
        received_date=received_date,
        amount=amount,
        method=method,
        channel=channel,
        reference=reference,
        notes=notes,
    )
    session.add(payment)
    session.flush()
    _set_allocations(session, org, payment, allocations, auto_allocate)
    session.flush()
    return payment


def _ensure_editable(payment: Payment) -> None:
    if payment.is_historical:
        raise PaymentError("Imported payments cannot be changed")
    if payment.deposit_id is not None:
        raise PaymentError("The payment is on a deposit; remove it from the deposit first")


def update_payment(
    session: Session,
    org: Organization,
    payment: Payment,
    changes: dict[str, object],
    allocations: Sequence[Allocation] | None,
    reallocate: bool,
) -> None:
    _ensure_editable(payment)
    for key, value in changes.items():
        setattr(payment, key, value)
    if payment.amount <= 0:
        raise PaymentError("The amount must be positive")
    if allocations is not None or reallocate:
        _set_allocations(session, org, payment, allocations, auto_allocate=reallocate)
    elif unapplied(payment) < 0:
        raise PaymentError("The applied amounts exceed the payment")
    session.flush()


def delete_payment(session: Session, payment: Payment) -> None:
    _ensure_editable(payment)
    session.delete(payment)
    session.flush()


def party_balance(session: Session, org: Organization, party_id: int) -> PartyBalance:
    today = today_in(org.timezone)
    invoices = session.scalars(
        select(Invoice).where(
            Invoice.organization_id == org.id,
            Invoice.party_id == party_id,
            Invoice.kind == InvoiceKind.INVOICE,
            Invoice.status == InvoiceStatus.ISSUED,
        )
    ).all()
    infos = invoice_service.balances(session, invoices, today)
    due = [info for info in infos.values() if info.balance_due > invoice_service.PAID_TOLERANCE]
    payments = session.scalars(
        select(Payment).where(Payment.organization_id == org.id, Payment.party_id == party_id)
    ).all()
    return PartyBalance(
        receivable=sum((i.balance_due for i in due), ZERO),
        overdue=sum((i.balance_due for i in due if i.overdue), ZERO),
        open_invoices=len(due),
        unapplied_credit=sum((unapplied(p) for p in payments if unapplied(p) > 0), ZERO),
    )


# -- deposits -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtraItem:
    amount: Decimal
    description: str | None


def _attach_payments(
    session: Session, org: Organization, deposit: Deposit, payment_ids: Sequence[int]
) -> None:
    for payment_id in payment_ids:
        payment = session.get(Payment, payment_id)
        if payment is None or payment.organization_id != org.id:
            raise PaymentError(f"Payment {payment_id} not found")
        if payment.deposit_id is not None and payment.deposit_id != deposit.id:
            raise PaymentError(f"Payment {payment_id} is already on another deposit")
        if payment.is_historical:
            raise PaymentError(f"Payment {payment_id} was imported and cannot be deposited")
        payment.deposit_id = deposit.id


def create_deposit(
    session: Session,
    org: Organization,
    *,
    deposit_date: date,
    bank_party_id: int | None,
    notes: str | None,
    payment_ids: Sequence[int],
    items: Sequence[ExtraItem],
) -> Deposit:
    deposit = Deposit(
        organization_id=org.id, deposit_date=deposit_date, bank_party_id=bank_party_id, notes=notes
    )
    deposit.items = [DepositItem(amount=i.amount, description=i.description) for i in items]
    session.add(deposit)
    session.flush()
    _attach_payments(session, org, deposit, payment_ids)
    if not payment_ids and not items:
        raise PaymentError("A deposit needs at least one payment or item")
    session.flush()
    return deposit


def update_deposit(
    session: Session,
    org: Organization,
    deposit: Deposit,
    changes: dict[str, object],
    payment_ids: Sequence[int] | None,
    items: Sequence[ExtraItem] | None,
) -> None:
    for key, value in changes.items():
        setattr(deposit, key, value)
    if payment_ids is not None:
        for payment in list(deposit.payments):
            if payment.id not in payment_ids:
                payment.deposit_id = None
        _attach_payments(session, org, deposit, payment_ids)
    if items is not None:
        deposit.items = [DepositItem(amount=i.amount, description=i.description) for i in items]
    session.flush()


def delete_deposit(session: Session, deposit: Deposit) -> None:
    for payment in deposit.payments:
        payment.deposit_id = None
    session.delete(deposit)
    session.flush()


def deposit_total(session: Session, deposit: Deposit) -> Decimal:
    payments = session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.deposit_id == deposit.id)
    )
    return Decimal(payments or 0) + sum((i.amount for i in deposit.items), ZERO)
