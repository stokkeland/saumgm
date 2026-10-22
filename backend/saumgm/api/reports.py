"""Reports as JSON for the screens, and the same reports as CSV downloads (…/report.csv)."""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel

from saumgm import audit
from saumgm.api.deps import Auth, DbSession, Reader
from saumgm.enums import TaxBasis
from saumgm.models import Organization
from saumgm.schemas.types import Amount, RateValue
from saumgm.services import reports
from saumgm.timeutil import today_in

router = APIRouter(prefix="/reports", tags=["reports"])


def _org(db: DbSession, auth: Auth) -> Organization:
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    return org


def _csv(
    db: DbSession, name: str, header: Sequence[str], rows: Iterable[Sequence[Any]]
) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([str(v) if isinstance(v, Decimal) else v for v in row])
    audit.record(db, "export", entity_type="report", entity_id=name)
    db.commit()
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


# -- sales ----------------------------------------------------------------------------------------


class SalesRowOut(BaseModel):
    key: str
    label: str
    documents: int
    sales: Amount
    tax: Amount
    total: Amount


class SalesReport(BaseModel):
    date_from: date
    date_to: date
    group: reports.SalesGroup
    rows: list[SalesRowOut]
    sales: Amount
    tax: Amount
    total: Amount


def _sales(
    db: DbSession, auth: Auth, date_from: date, date_to: date, group: reports.SalesGroup
) -> SalesReport:
    rows = reports.sales(db, _org(db, auth), date_from, date_to, group)
    return SalesReport(
        date_from=date_from,
        date_to=date_to,
        group=group,
        rows=[SalesRowOut(**vars(r)) for r in rows],
        sales=sum((r.sales for r in rows), Decimal(0)),
        tax=sum((r.tax for r in rows), Decimal(0)),
        total=sum((r.total for r in rows), Decimal(0)),
    )


@router.get("/sales")
def sales_report(
    auth: Reader,
    db: DbSession,
    date_from: date,
    date_to: date,
    group: reports.SalesGroup = "month",
) -> SalesReport:
    return _sales(db, auth, date_from, date_to, group)


@router.get("/sales.csv")
def sales_csv(
    auth: Reader, db: DbSession, date_from: date, date_to: date, group: reports.SalesGroup = "month"
) -> Response:
    report = _sales(db, auth, date_from, date_to, group)
    return _csv(
        db,
        f"sales-by-{group}-{date_from}-{date_to}",
        [group, "documents", "sales", "tax", "total"],
        [[r.label, r.documents, r.sales, r.tax, r.total] for r in report.rows],
    )


# -- sales tax ------------------------------------------------------------------------------------


class TaxLineOut(BaseModel):
    jurisdiction_id: int | None
    jurisdiction: str
    name: str
    rate: RateValue | None
    taxable: Amount
    tax: Amount


class SalesTaxOut(BaseModel):
    basis: TaxBasis
    date_from: date
    date_to: date
    gross_sales: Amount
    taxable_sales: Amount
    non_taxable_sales: Amount
    tax_collected: Amount
    bad_debt_tax_credit: Amount
    net_tax: Amount
    lines: list[TaxLineOut]


def _sales_tax(
    db: DbSession, auth: Auth, date_from: date, date_to: date, basis: TaxBasis | None
) -> SalesTaxOut:
    r = reports.sales_tax(db, _org(db, auth), date_from, date_to, basis)
    return SalesTaxOut(
        basis=r.basis,
        date_from=r.date_from,
        date_to=r.date_to,
        gross_sales=r.gross_sales,
        taxable_sales=r.taxable_sales,
        non_taxable_sales=r.non_taxable_sales,
        tax_collected=r.tax_collected,
        bad_debt_tax_credit=r.bad_debt_tax_credit,
        net_tax=r.net_tax,
        lines=[TaxLineOut(**vars(line)) for line in r.lines],
    )


@router.get("/sales-tax")
def sales_tax_report(
    auth: Reader,
    db: DbSession,
    date_from: date,
    date_to: date,
    basis: TaxBasis | None = Query(None, description="Defaults to the business setting"),
) -> SalesTaxOut:
    return _sales_tax(db, auth, date_from, date_to, basis)


@router.get("/sales-tax.csv")
def sales_tax_csv(
    auth: Reader, db: DbSession, date_from: date, date_to: date, basis: TaxBasis | None = None
) -> Response:
    r = _sales_tax(db, auth, date_from, date_to, basis)
    rows: list[list[Any]] = [
        [line.jurisdiction, line.name, line.rate, line.taxable, line.tax] for line in r.lines
    ]
    rows += [
        [],
        ["Gross sales", "", "", r.gross_sales, ""],
        ["Non-taxable sales", "", "", r.non_taxable_sales, ""],
        ["Taxable sales", "", "", r.taxable_sales, ""],
        ["Tax collected", "", "", "", r.tax_collected],
        ["Bad-debt tax credit", "", "", "", r.bad_debt_tax_credit],
        ["Net tax", "", "", "", r.net_tax],
    ]
    return _csv(
        db,
        f"sales-tax-{r.basis.value}-{date_from}-{date_to}",
        ["jurisdiction", "tax", "rate", "taxable", "tax_amount"],
        rows,
    )


# -- expenses and profit & loss -------------------------------------------------------------------


class ExpenseRowOut(BaseModel):
    key: str
    label: str
    account_type: str | None
    entries: int
    total: Amount


class ExpensesReport(BaseModel):
    date_from: date
    date_to: date
    group: reports.ExpenseGroup
    rows: list[ExpenseRowOut]
    total: Amount


def _expenses(
    db: DbSession, auth: Auth, date_from: date, date_to: date, group: reports.ExpenseGroup
) -> ExpensesReport:
    rows = reports.expenses(db, _org(db, auth), date_from, date_to, group)
    return ExpensesReport(
        date_from=date_from,
        date_to=date_to,
        group=group,
        rows=[ExpenseRowOut(**vars(r)) for r in rows],
        total=sum((r.total for r in rows), Decimal(0)),
    )


@router.get("/expenses")
def expenses_report(
    auth: Reader,
    db: DbSession,
    date_from: date,
    date_to: date,
    group: reports.ExpenseGroup = "account",
) -> ExpensesReport:
    return _expenses(db, auth, date_from, date_to, group)


@router.get("/expenses.csv")
def expenses_csv(
    auth: Reader,
    db: DbSession,
    date_from: date,
    date_to: date,
    group: reports.ExpenseGroup = "account",
) -> Response:
    report = _expenses(db, auth, date_from, date_to, group)
    return _csv(
        db,
        f"expenses-by-{group}-{date_from}-{date_to}",
        [group, "type", "entries", "total"],
        [[r.label, r.account_type or "", r.entries, r.total] for r in report.rows],
    )


class ProfitLossOut(BaseModel):
    date_from: date
    date_to: date
    sales: Amount
    cost_of_goods: list[ExpenseRowOut]
    cost_of_goods_total: Amount
    gross_profit: Amount
    expenses: list[ExpenseRowOut]
    bad_debts: Amount
    expenses_total: Amount
    net_profit: Amount


def _profit_loss(db: DbSession, auth: Auth, date_from: date, date_to: date) -> ProfitLossOut:
    r = reports.profit_and_loss(db, _org(db, auth), date_from, date_to)
    return ProfitLossOut(
        date_from=date_from,
        date_to=date_to,
        sales=r.sales,
        cost_of_goods=[ExpenseRowOut(**vars(x)) for x in r.cost_of_goods],
        cost_of_goods_total=r.cost_of_goods_total,
        gross_profit=r.gross_profit,
        expenses=[ExpenseRowOut(**vars(x)) for x in r.expenses],
        bad_debts=r.bad_debts,
        expenses_total=r.expenses_total,
        net_profit=r.net_profit,
    )


@router.get("/profit-loss")
def profit_loss_report(
    auth: Reader, db: DbSession, date_from: date, date_to: date
) -> ProfitLossOut:
    return _profit_loss(db, auth, date_from, date_to)


@router.get("/profit-loss.csv")
def profit_loss_csv(auth: Reader, db: DbSession, date_from: date, date_to: date) -> Response:
    r = _profit_loss(db, auth, date_from, date_to)
    rows: list[list[Any]] = [["Sales", "", r.sales]]
    rows += [["Cost of goods", x.label, x.total] for x in r.cost_of_goods]
    rows += [["Gross profit", "", r.gross_profit]]
    rows += [["Expense", x.label, x.total] for x in r.expenses]
    if r.bad_debts:
        rows += [["Expense", "Bad debts (written off)", r.bad_debts]]
    rows += [["Net profit", "", r.net_profit]]
    return _csv(db, f"profit-loss-{date_from}-{date_to}", ["section", "account", "amount"], rows)


# -- receivables aging ----------------------------------------------------------------------------


class AgingRowOut(BaseModel):
    party_id: int
    party_name: str
    invoices: int
    current: Amount
    days_1_30: Amount
    days_31_60: Amount
    days_61_90: Amount
    days_over_90: Amount
    total: Amount


class AgingReport(BaseModel):
    as_of: date
    rows: list[AgingRowOut]
    totals: AgingRowOut


def _aging(db: DbSession, auth: Auth) -> AgingReport:
    org = _org(db, auth)
    today = today_in(org.timezone)
    rows = reports.aging(db, org, today)
    out = [AgingRowOut(**vars(r), total=r.total) for r in rows]
    totals = reports.AgingRow(0, "Total", sum(r.invoices for r in rows))
    for name in reports.BUCKETS:
        setattr(totals, name, sum((getattr(r, name) for r in rows), Decimal(0)))
    return AgingReport(
        as_of=today, rows=out, totals=AgingRowOut(**vars(totals), total=totals.total)
    )


@router.get("/aging")
def aging_report(auth: Reader, db: DbSession) -> AgingReport:
    return _aging(db, auth)


@router.get("/aging.csv")
def aging_csv(auth: Reader, db: DbSession) -> Response:
    report = _aging(db, auth)
    header = ["client", "invoices", "current", "1-30", "31-60", "61-90", "over 90", "total"]
    return _csv(
        db,
        f"receivables-aging-{report.as_of}",
        header,
        [
            [
                r.party_name,
                r.invoices,
                r.current,
                r.days_1_30,
                r.days_31_60,
                r.days_61_90,
                r.days_over_90,
                r.total,
            ]
            for r in [*report.rows, report.totals]
        ],
    )
