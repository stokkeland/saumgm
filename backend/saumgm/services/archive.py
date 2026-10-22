"""Archiving: old records stay in their tables but are flagged, so everyday lists can hide them."""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from saumgm.enums import AuditActor, InvoiceStatus
from saumgm.models import AuditLog, Deposit, Expense, Invoice, Payment, PaymentAllocation


def archive_through(
    session: Session,
    organization_id: int,
    cutoff: date,
    *,
    actor: AuditActor = AuditActor.SYSTEM,
    user_id: int | None = None,
    batch_id: str | None = None,
) -> dict[str, int]:
    """Archive invoices, payments, deposits and expenses dated on or before `cutoff`.

    Draft invoices are never archived. A payment without a date is archived once every invoice
    it was applied to is archived. Returns the number of records archived per type.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    counts: dict[str, int] = {}

    # (name, model, document date column, extra conditions)
    targets: list[tuple[str, Any, Any, list[Any]]] = [
        ("invoice", Invoice, Invoice.issue_date, [Invoice.status != InvoiceStatus.DRAFT]),
        ("payment", Payment, Payment.received_date, []),
        ("deposit", Deposit, Deposit.deposit_date, []),
        ("expense", Expense, Expense.expense_date, []),
    ]
    for name, model, date_column, extra in targets:
        result = session.execute(
            update(model)
            .where(
                model.organization_id == organization_id,
                model.archived_at.is_(None),
                date_column <= cutoff,
                *extra,
            )
            .values(archived_at=now)
            .execution_options(synchronize_session=False)
        )
        counts[name] = result.rowcount  # type: ignore[attr-defined]  # UPDATE gives a CursorResult

    undated = session.scalars(
        select(Payment).where(
            Payment.organization_id == organization_id,
            Payment.archived_at.is_(None),
            Payment.received_date.is_(None),
        )
    )
    for payment in undated:
        invoices = session.scalars(
            select(Invoice)
            .join(PaymentAllocation, PaymentAllocation.invoice_id == Invoice.id)
            .where(PaymentAllocation.payment_id == payment.id)
        ).all()
        if invoices and all(inv.archived_at is not None for inv in invoices):
            payment.archived_at = now
            counts["payment"] += 1

    session.add(
        AuditLog(
            organization_id=organization_id,
            actor=actor,
            user_id=user_id,
            batch_id=batch_id,
            action="archive",
            changes={"through": cutoff.isoformat(), "archived": counts},
        )
    )
    session.flush()
    return counts
