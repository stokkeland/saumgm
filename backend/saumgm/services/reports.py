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

"""Report calculations. Every report works on issued documents only; void invoices never count.

Sales are amounts before tax (total - tax). Income is counted one of two ways (`TaxBasis`):

- by invoice date (accrual): an invoice counts in full on its date and credit notes subtract.
  Written-off invoices still count as sales (the bad debt shows up in the profit & loss and as a
  sales-tax credit instead).
- by payment date (cash): what was received counts on the day it was received, with its share of
  tax taken out. Unpaid and written-off amounts never count. A credit note only lowers what is
  still owed, so it would count when money goes back; refunds are not recorded yet, so credit
  notes do not appear in this basis. Payment amounts not applied to an invoice wait until they are.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from saumgm.enums import AccountType, InvoiceKind, InvoiceStatus, TaxBasis
from saumgm.models import (
    Account,
    CatalogItem,
    Expense,
    ExpenseLine,
    Invoice,
    Organization,
    Party,
    Payment,
    PaymentAllocation,
    RevenueCategory,
    TaxJurisdiction,
)
from saumgm.services import invoices as invoice_service
from saumgm.services.money import ZERO

CENT = Decimal("0.01")


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _issued(session: Session, org_id: int, date_from: date, date_to: date) -> list[Invoice]:
    return list(
        session.scalars(
            select(Invoice)
            .where(
                Invoice.organization_id == org_id,
                Invoice.status == InvoiceStatus.ISSUED,
                Invoice.issue_date >= date_from,
                Invoice.issue_date <= date_to,
            )
            .options(selectinload(Invoice.lines), selectinload(Invoice.taxes))
            .order_by(Invoice.issue_date, Invoice.id)
        )
    )


def _sign(invoice: Invoice) -> int:
    return -1 if invoice.kind == InvoiceKind.CREDIT_NOTE else 1


@dataclass
class Received:
    """The part of a payment applied to one invoice, split into sales and tax."""

    invoice: Invoice
    received_date: date
    amount: Decimal
    tax: Decimal

    @property
    def sales(self) -> Decimal:
        return self.amount - self.tax


def received(session: Session, org_id: int, date_from: date, date_to: date) -> list[Received]:
    rows = session.execute(
        select(PaymentAllocation, Payment.received_date, Invoice)
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
        .where(
            Payment.organization_id == org_id,
            Payment.received_date >= date_from,
            Payment.received_date <= date_to,
            Invoice.status == InvoiceStatus.ISSUED,
        )
        .options(selectinload(Invoice.lines))
        .order_by(Payment.received_date, PaymentAllocation.id)
    ).all()
    out = []
    for allocation, day, invoice in rows:
        assert day is not None  # the date range leaves out payments without one
        if allocation.legacy_sales_tax is not None:
            # Imported payments carry the tax the old system recorded for them.
            tax = allocation.legacy_sales_tax
        elif invoice.total:
            tax = allocation.amount * invoice.tax_total / invoice.total
        else:
            tax = ZERO
        out.append(Received(invoice, day, allocation.amount, tax))
    return out


# -- sales ----------------------------------------------------------------------------------------

SalesGroup = Literal["month", "client", "revenue_category"]


@dataclass
class SalesRow:
    key: str
    label: str
    documents: int = 0
    sales: Decimal = ZERO
    tax: Decimal = ZERO
    total: Decimal = ZERO


def sales(
    session: Session,
    org: Organization,
    date_from: date,
    date_to: date,
    group: SalesGroup,
    basis: TaxBasis = TaxBasis.ACCRUAL,
) -> list[SalesRow]:
    rows: dict[str, SalesRow] = {}
    counted: dict[str, set[int]] = defaultdict(set)

    def row(key: str, label: str) -> SalesRow:
        if key not in rows:
            rows[key] = SalesRow(key, label)
        return rows[key]

    if basis == TaxBasis.CASH:
        payments = received(session, org.id, date_from, date_to)
        _cash_sales(session, org, payments, group, row, counted)
        return _finish(rows, counted, group)

    invoices = _issued(session, org.id, date_from, date_to)
    if group == "revenue_category":
        names, item_category = _line_categories(session, org.id)
        for invoice in invoices:
            for line in invoice.lines:
                category = line.revenue_category_id or item_category.get(line.catalog_item_id or 0)
                key = str(category or 0)
                r = row(key, names.get(category or 0, "Uncategorized"))
                r.sales += _sign(invoice) * line.line_total
                r.total += _sign(invoice) * line.line_total
                counted[key].add(invoice.id)
    else:
        party_names = dict(
            session.execute(
                select(Party.id, Party.name).where(Party.organization_id == org.id)
            ).all()
        )
        for invoice in invoices:
            assert invoice.issue_date is not None
            if group == "month":
                key = label = invoice.issue_date.strftime("%Y-%m")
            else:
                key, label = str(invoice.party_id), party_names.get(invoice.party_id, "?")
            r = row(key, label)
            sign = _sign(invoice)
            r.sales += sign * (invoice.total - invoice.tax_total)
            r.tax += sign * invoice.tax_total
            r.total += sign * invoice.total
            counted[key].add(invoice.id)
    return _finish(rows, counted, group)


def _finish(
    rows: dict[str, SalesRow], counted: dict[str, set[int]], group: SalesGroup
) -> list[SalesRow]:
    for key, r in rows.items():
        r.documents = len(counted[key])
        r.sales, r.tax, r.total = cents(r.sales), cents(r.tax), cents(r.total)
    return sorted(rows.values(), key=lambda r: r.key if group == "month" else r.label.lower())


def _line_categories(session: Session, org_id: int) -> tuple[dict[int, str], dict[int, int | None]]:
    """Revenue category names, and the category of each catalog item that has one."""
    names = {
        c.id: c.name
        for c in session.scalars(
            select(RevenueCategory).where(RevenueCategory.organization_id == org_id)
        )
    }
    item_category = {
        item_id: category_id
        for item_id, category_id in session.execute(
            select(CatalogItem.id, CatalogItem.revenue_category_id).where(
                CatalogItem.organization_id == org_id,
                CatalogItem.revenue_category_id.is_not(None),
            )
        )
    }
    return names, item_category


def _cash_sales(
    session: Session,
    org: Organization,
    payments: list[Received],
    group: SalesGroup,
    row: Callable[[str, str], SalesRow],
    counted: dict[str, set[int]],
) -> None:
    if group == "revenue_category":
        names, item_category = _line_categories(session, org.id)
        for p in payments:
            lines = p.invoice.lines
            lines_total = sum((line.line_total for line in lines), ZERO)
            # The amount received is spread over the invoice's lines by their share of it.
            shares = (
                [
                    (
                        line.revenue_category_id or item_category.get(line.catalog_item_id or 0),
                        p.sales * line.line_total / lines_total,
                    )
                    for line in lines
                ]
                if lines_total
                else [(None, p.sales)]
            )
            for category, amount in shares:
                key = str(category or 0)
                r = row(key, names.get(category or 0, "Uncategorized"))
                r.sales += amount
                r.total += amount
                counted[key].add(p.invoice.id)
        return
    party_names = dict(
        session.execute(select(Party.id, Party.name).where(Party.organization_id == org.id)).all()
    )
    for p in payments:
        if group == "month":
            key = label = p.received_date.strftime("%Y-%m")
        else:
            key, label = str(p.invoice.party_id), party_names.get(p.invoice.party_id, "?")
        r = row(key, label)
        r.sales += p.sales
        r.tax += p.tax
        r.total += p.amount
        counted[key].add(p.invoice.id)


# -- sales tax ------------------------------------------------------------------------------------


@dataclass
class TaxLine:
    jurisdiction_id: int | None
    jurisdiction: str
    name: str
    rate: Decimal | None
    taxable: Decimal = ZERO
    tax: Decimal = ZERO


@dataclass
class SalesTaxReport:
    basis: TaxBasis
    date_from: date
    date_to: date
    gross_sales: Decimal = ZERO
    taxable_sales: Decimal = ZERO
    non_taxable_sales: Decimal = ZERO
    tax_collected: Decimal = ZERO
    bad_debt_tax_credit: Decimal = ZERO
    lines: list[TaxLine] = field(default_factory=list)

    @property
    def net_tax(self) -> Decimal:
        return self.tax_collected - self.bad_debt_tax_credit


def sales_tax(
    session: Session, org: Organization, date_from: date, date_to: date, basis: TaxBasis | None
) -> SalesTaxReport:
    basis = basis or org.tax_basis
    report = SalesTaxReport(basis, date_from, date_to)
    jurisdictions = {
        j.id: j.name
        for j in session.scalars(
            select(TaxJurisdiction).where(TaxJurisdiction.organization_id == org.id)
        )
    }
    lines: dict[tuple[int | None, str, Decimal | None], TaxLine] = {}

    def add(invoice: Invoice, factor: Decimal) -> None:
        for t in invoice.taxes:
            key = (t.jurisdiction_id, t.name, t.rate)
            if key not in lines:
                name = jurisdictions.get(t.jurisdiction_id or 0, t.name)
                lines[key] = TaxLine(t.jurisdiction_id, name, t.name, t.rate)
            lines[key].taxable += factor * t.taxable_base
            lines[key].tax += factor * t.amount

    def taxable_base(invoice: Invoice) -> Decimal:
        return max((t.taxable_base for t in invoice.taxes), default=ZERO)

    if basis == TaxBasis.ACCRUAL:
        for invoice in _issued(session, org.id, date_from, date_to):
            sign = Decimal(_sign(invoice))
            report.gross_sales += sign * (invoice.total - invoice.tax_total)
            report.taxable_sales += sign * taxable_base(invoice)
            report.tax_collected += sign * invoice.tax_total
            add(invoice, sign)
        written_off = session.scalars(
            select(Invoice).where(
                Invoice.organization_id == org.id,
                Invoice.write_off_date >= date_from,
                Invoice.write_off_date <= date_to,
            )
        )
        report.bad_debt_tax_credit = sum(
            (invoice_service.written_off_tax(i) for i in written_off), ZERO
        )
    else:
        allocations = session.execute(
            select(PaymentAllocation, Invoice)
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
            .where(
                Payment.organization_id == org.id,
                Payment.received_date >= date_from,
                Payment.received_date <= date_to,
            )
            .options(selectinload(Invoice.taxes))
        ).all()
        for allocation, invoice in allocations:
            if allocation.legacy_sales_tax is not None:
                # Imported payments carry the tax the old system recorded for them.
                tax = allocation.legacy_sales_tax
                report.tax_collected += tax
                report.gross_sales += allocation.amount - tax
                report.taxable_sales += allocation.legacy_taxable_amount or ZERO
                if tax:
                    key = (
                        invoice.tax_jurisdiction_id,
                        invoice.tax_location_text or "Sales tax",
                        None,
                    )
                    if key not in lines:
                        name = jurisdictions.get(invoice.tax_jurisdiction_id or 0, key[1])
                        lines[key] = TaxLine(invoice.tax_jurisdiction_id, name, key[1], None)
                    lines[key].taxable += allocation.legacy_taxable_amount or ZERO
                    lines[key].tax += tax
                continue
            if not invoice.total:
                continue
            factor = allocation.amount / invoice.total
            report.gross_sales += factor * (invoice.total - invoice.tax_total)
            report.taxable_sales += factor * taxable_base(invoice)
            report.tax_collected += factor * invoice.tax_total
            add(invoice, factor)

    report.gross_sales = cents(report.gross_sales)
    report.taxable_sales = cents(report.taxable_sales)
    report.non_taxable_sales = report.gross_sales - report.taxable_sales
    report.tax_collected = cents(report.tax_collected)
    report.bad_debt_tax_credit = cents(report.bad_debt_tax_credit)
    for line in lines.values():
        line.taxable, line.tax = cents(line.taxable), cents(line.tax)
    report.lines = sorted(lines.values(), key=lambda line: (line.jurisdiction, line.name))
    return report


# -- expenses and profit & loss -------------------------------------------------------------------

ExpenseGroup = Literal["account", "vendor", "month"]


@dataclass
class ExpenseRow:
    key: str
    label: str
    account_type: str | None = None
    entries: int = 0
    total: Decimal = ZERO


def _expense_lines(
    session: Session, org_id: int, date_from: date, date_to: date
) -> list[tuple[ExpenseLine, Expense, Account]]:
    return [
        (line, expense, account)
        for line, expense, account in session.execute(
            select(ExpenseLine, Expense, Account)
            .join(Expense, Expense.id == ExpenseLine.expense_id)
            .join(Account, Account.id == ExpenseLine.account_id)
            .where(
                Expense.organization_id == org_id,
                Expense.expense_date >= date_from,
                Expense.expense_date <= date_to,
            )
        ).all()
    ]


def expenses(
    session: Session, org: Organization, date_from: date, date_to: date, group: ExpenseGroup
) -> list[ExpenseRow]:
    party_names = dict(
        session.execute(select(Party.id, Party.name).where(Party.organization_id == org.id)).all()
    )
    rows: dict[str, ExpenseRow] = {}
    seen: dict[str, set[int]] = defaultdict(set)
    for line, expense, account in _expense_lines(session, org.id, date_from, date_to):
        if group == "account":
            key, label, kind = (
                account.code,
                f"{account.code} {account.name}",
                account.account_type.value,
            )
        elif group == "vendor":
            key = str(expense.vendor_party_id or 0)
            label, kind = party_names.get(expense.vendor_party_id or 0, "No vendor"), None
        else:
            key = label = expense.expense_date.strftime("%Y-%m")
            kind = None
        r = rows.setdefault(key, ExpenseRow(key, label, kind))
        r.total += line.amount
        seen[key].add(expense.id)
    for key, r in rows.items():
        r.entries = len(seen[key])
        r.total = cents(r.total)
    return sorted(rows.values(), key=lambda r: r.key if group != "vendor" else r.label.lower())


@dataclass
class ProfitAndLoss:
    basis: TaxBasis
    date_from: date
    date_to: date
    sales: Decimal
    cost_of_goods: list[ExpenseRow]
    expenses: list[ExpenseRow]
    bad_debts: Decimal

    @property
    def cost_of_goods_total(self) -> Decimal:
        return sum((r.total for r in self.cost_of_goods), ZERO)

    @property
    def gross_profit(self) -> Decimal:
        return self.sales - self.cost_of_goods_total

    @property
    def expenses_total(self) -> Decimal:
        return sum((r.total for r in self.expenses), ZERO) + self.bad_debts

    @property
    def net_profit(self) -> Decimal:
        return self.gross_profit - self.expenses_total


def profit_and_loss(
    session: Session,
    org: Organization,
    date_from: date,
    date_to: date,
    basis: TaxBasis = TaxBasis.ACCRUAL,
) -> ProfitAndLoss:
    by_account = expenses(session, org, date_from, date_to, "account")
    if basis == TaxBasis.CASH:
        total_sales = sum((p.sales for p in received(session, org.id, date_from, date_to)), ZERO)
        # What was never received was never counted as income, so there is no bad debt.
        bad_debts = ZERO
    else:
        issued = _issued(session, org.id, date_from, date_to)
        total_sales = sum((_sign(i) * (i.total - i.tax_total) for i in issued), ZERO)
        written_off = session.scalars(
            select(Invoice).where(
                Invoice.organization_id == org.id,
                Invoice.write_off_date >= date_from,
                Invoice.write_off_date <= date_to,
            )
        )
        # The tax part of a bad debt is a tax credit, not a business expense.
        bad_debts = sum(
            (
                (i.write_off_amount or ZERO) - invoice_service.written_off_tax(i)
                for i in written_off
            ),
            ZERO,
        )
    return ProfitAndLoss(
        basis=basis,
        date_from=date_from,
        date_to=date_to,
        sales=cents(total_sales),
        cost_of_goods=[r for r in by_account if r.account_type == AccountType.COGS.value],
        expenses=[r for r in by_account if r.account_type != AccountType.COGS.value],
        bad_debts=cents(bad_debts),
    )


# -- receivables aging ----------------------------------------------------------------------------

BUCKETS = ("current", "days_1_30", "days_31_60", "days_61_90", "days_over_90")


@dataclass
class AgingRow:
    party_id: int
    party_name: str
    invoices: int = 0
    current: Decimal = ZERO
    days_1_30: Decimal = ZERO
    days_31_60: Decimal = ZERO
    days_61_90: Decimal = ZERO
    days_over_90: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return sum((getattr(self, b) for b in BUCKETS), ZERO)


def bucket(days_past_due: int) -> str:
    if days_past_due <= 0:
        return "current"
    if days_past_due <= 30:
        return "days_1_30"
    if days_past_due <= 60:
        return "days_31_60"
    if days_past_due <= 90:
        return "days_61_90"
    return "days_over_90"


def aging(session: Session, org: Organization, today: date) -> list[AgingRow]:
    """What each client owes today, by how long it is past due (archived invoices included)."""
    invoices = list(
        session.scalars(
            select(Invoice).where(
                Invoice.organization_id == org.id,
                Invoice.kind == InvoiceKind.INVOICE,
                Invoice.status == InvoiceStatus.ISSUED,
            )
        )
    )
    infos = invoice_service.balances(session, invoices, today)
    party_names = dict(
        session.execute(select(Party.id, Party.name).where(Party.organization_id == org.id)).all()
    )
    rows: dict[int, AgingRow] = {}
    for invoice in invoices:
        due = infos[invoice.id].balance_due
        if due <= invoice_service.PAID_TOLERANCE:
            continue
        r = rows.setdefault(
            invoice.party_id, AgingRow(invoice.party_id, party_names.get(invoice.party_id, "?"))
        )
        due_date = invoice.due_date or invoice.issue_date or today
        name = bucket((today - due_date).days)
        setattr(r, name, getattr(r, name) + due)
        r.invoices += 1
    return sorted(rows.values(), key=lambda r: -r.total)
