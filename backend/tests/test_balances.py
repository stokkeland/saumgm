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
