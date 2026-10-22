from datetime import date
from decimal import Decimal

from saumgm.enums import InvoiceKind, InvoiceStatus, PaymentStatus
from saumgm.models import Invoice
from saumgm.services.invoices import balance_info

D = Decimal
TODAY = date(2026, 10, 21)


def invoice(total: str, due: date | None = None) -> Invoice:
    return Invoice(
        kind=InvoiceKind.INVOICE, status=InvoiceStatus.ISSUED, total=D(total), due_date=due
    )


def test_fractional_cent_totals_settle_to_zero() -> None:
    info = balance_info(invoice("8088.625"), D("8088.63"), D(0), TODAY)
    assert (info.status, info.balance_due) == (PaymentStatus.PAID, D(0))


def test_statuses() -> None:
    assert balance_info(invoice("100"), D(0), D(0), TODAY).status == PaymentStatus.UNPAID
    partial = balance_info(invoice("100", date(2026, 1, 1)), D(40), D(0), TODAY)
    assert (partial.status, partial.balance_due, partial.overdue) == (
        PaymentStatus.PARTIALLY_PAID,
        D(60),
        True,
    )
    over = balance_info(invoice("100"), D("100.01"), D(0), TODAY)
    assert (over.status, over.balance_due) == (PaymentStatus.OVERPAID, D("-0.01"))
    assert balance_info(invoice("100"), D(75), D(25), TODAY).status == PaymentStatus.PAID
