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

"""Reports as JSON for the screens; the same reports as CSV (…/report.csv), as a PDF
(…/report.pdf) and by email (…/report/email). All three are made from one `ReportDocument`."""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, get_args
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel

from saumgm import audit
from saumgm.api.deps import Auth, DbSession, Editor, Reader
from saumgm.api.email import draft_out, send_draft
from saumgm.documents import Formatter, Rate, ReportDocument, ReportRow, report_pdf
from saumgm.email import Attachment
from saumgm.enums import TaxBasis
from saumgm.models import Organization
from saumgm.schemas.email import DraftOut, MessageOut, SendIn
from saumgm.schemas.types import Amount, RateValue
from saumgm.services import emailing, reports
from saumgm.timeutil import today_in

router = APIRouter(prefix="/reports", tags=["reports"])

BASIS_LABELS = {TaxBasis.ACCRUAL: "By invoice date", TaxBasis.CASH: "By payment date"}
BasisParam = Query(None, description="Defaults to the business setting")


def _org(db: DbSession, auth: Auth) -> Organization:
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    return org


def _period(f: Formatter, date_from: date, date_to: date) -> str:
    return f"{f.date(date_from)} - {f.date(date_to)}"


# -- sales ----------------------------------------------------------------------------------------


class SalesRowOut(BaseModel):
    key: str
    label: str
    documents: int
    sales: Amount
    tax: Amount
    total: Amount


class SalesReport(BaseModel):
    basis: TaxBasis
    date_from: date
    date_to: date
    group: reports.SalesGroup
    rows: list[SalesRowOut]
    sales: Amount
    tax: Amount
    total: Amount


def _sales(
    db: DbSession,
    org: Organization,
    date_from: date,
    date_to: date,
    group: reports.SalesGroup,
    basis: TaxBasis | None,
) -> SalesReport:
    basis = basis or org.income_basis
    rows = reports.sales(db, org, date_from, date_to, group, basis)
    return SalesReport(
        basis=basis,
        date_from=date_from,
        date_to=date_to,
        group=group,
        rows=[SalesRowOut(**vars(r)) for r in rows],
        sales=sum((r.sales for r in rows), Decimal(0)),
        tax=sum((r.tax for r in rows), Decimal(0)),
        total=sum((r.total for r in rows), Decimal(0)),
    )


SALES_GROUPS = {"month": "Month", "client": "Client", "revenue_category": "Category"}


def _sales_document(f: Formatter, r: SalesReport) -> ReportDocument:
    by_category = r.group == "revenue_category"
    header = [SALES_GROUPS[r.group], "Invoices", "Sales"]
    if by_category:
        widths = [4.6, 1.0, 1.6]
        rows = [ReportRow([x.label, x.documents, x.sales]) for x in r.rows]
        total = ReportRow(["Total", None, r.sales], strong=True)
    else:
        header += ["Tax", "Total"]
        widths = [3.0, 1.0, 1.1, 1.0, 1.1]
        rows = [ReportRow([x.label, x.documents, x.sales, x.tax, x.total]) for x in r.rows]
        total = ReportRow(["Total", None, r.sales, r.tax, r.total], strong=True)
    if r.basis == TaxBasis.CASH:
        note = (
            "Payments received in the period, applied to invoices, without their tax. Unpaid "
            "and written-off amounts do not count."
        )
    else:
        note = (
            "Issued invoices dated in the period, less credit notes. Sales are before tax; "
            "written-off invoices still count as sales."
        )
    return ReportDocument(
        name=f"sales-by-{r.group}-{r.basis.value}-{r.date_from}-{r.date_to}",
        title="Sales",
        facts=[
            ("Period", _period(f, r.date_from, r.date_to)),
            ("Basis", BASIS_LABELS[r.basis]),
            ("Grouped by", SALES_GROUPS[r.group]),
        ],
        header=header,
        widths=widths,
        rows=[*rows, total],
        note=note,
    )


@router.get("/sales")
def sales_report(
    auth: Reader,
    db: DbSession,
    date_from: date,
    date_to: date,
    group: reports.SalesGroup = "month",
    basis: TaxBasis | None = BasisParam,
) -> SalesReport:
    return _sales(db, _org(db, auth), date_from, date_to, group, basis)


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
    db: DbSession, org: Organization, date_from: date, date_to: date, basis: TaxBasis | None
) -> SalesTaxOut:
    r = reports.sales_tax(db, org, date_from, date_to, basis)
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


def _sales_tax_document(f: Formatter, r: SalesTaxOut) -> ReportDocument:
    return ReportDocument(
        name=f"sales-tax-{r.basis.value}-{r.date_from}-{r.date_to}",
        title="Sales tax",
        facts=[("Period", _period(f, r.date_from, r.date_to)), ("Basis", BASIS_LABELS[r.basis])],
        header=["Jurisdiction", "Tax", "Rate", "Taxable", "Tax amount"],
        widths=[2.4, 1.9, 0.8, 1.1, 1.0],
        right_from=2,
        rows=[ReportRow([x.jurisdiction, x.name, Rate(x.rate), x.taxable, x.tax]) for x in r.lines],
        summary=[
            ReportRow(["Gross sales", "", "", r.gross_sales, ""]),
            ReportRow(["Non-taxable sales", "", "", r.non_taxable_sales, ""]),
            ReportRow(["Taxable sales", "", "", r.taxable_sales, ""]),
            ReportRow(["Tax collected", "", "", "", r.tax_collected]),
            ReportRow(["Bad-debt tax credit", "", "", "", r.bad_debt_tax_credit]),
            ReportRow(["Net tax", "", "", "", r.net_tax], strong=True),
        ],
        note=(
            "The share of tax in payments received in the period (for imported payments, the "
            "tax the old system recorded)."
            if r.basis == TaxBasis.CASH
            else "Tax on invoices issued in the period, with a credit for the tax part of "
            "invoices written off in it."
        ),
    )


@router.get("/sales-tax")
def sales_tax_report(
    auth: Reader,
    db: DbSession,
    date_from: date,
    date_to: date,
    basis: TaxBasis | None = BasisParam,
) -> SalesTaxOut:
    return _sales_tax(db, _org(db, auth), date_from, date_to, basis)


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
    db: DbSession, org: Organization, date_from: date, date_to: date, group: reports.ExpenseGroup
) -> ExpensesReport:
    rows = reports.expenses(db, org, date_from, date_to, group)
    return ExpensesReport(
        date_from=date_from,
        date_to=date_to,
        group=group,
        rows=[ExpenseRowOut(**vars(r)) for r in rows],
        total=sum((r.total for r in rows), Decimal(0)),
    )


EXPENSE_GROUPS = {"account": "Account", "vendor": "Vendor", "month": "Month"}


def _expenses_document(f: Formatter, r: ExpensesReport) -> ReportDocument:
    return ReportDocument(
        name=f"expenses-by-{r.group}-{r.date_from}-{r.date_to}",
        title="Expenses",
        facts=[
            ("Period", _period(f, r.date_from, r.date_to)),
            ("Grouped by", EXPENSE_GROUPS[r.group]),
        ],
        header=[EXPENSE_GROUPS[r.group], "Entries", "Total"],
        widths=[4.8, 1.0, 1.4],
        rows=[
            *(ReportRow([x.label, x.entries, x.total]) for x in r.rows),
            ReportRow(["Total", None, r.total], strong=True),
        ],
        note="Expenses by expense date.",
    )


@router.get("/expenses")
def expenses_report(
    auth: Reader,
    db: DbSession,
    date_from: date,
    date_to: date,
    group: reports.ExpenseGroup = "account",
) -> ExpensesReport:
    return _expenses(db, _org(db, auth), date_from, date_to, group)


class ProfitLossOut(BaseModel):
    basis: TaxBasis
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


def _profit_loss(
    db: DbSession, org: Organization, date_from: date, date_to: date, basis: TaxBasis | None
) -> ProfitLossOut:
    r = reports.profit_and_loss(db, org, date_from, date_to, basis or org.income_basis)
    return ProfitLossOut(
        basis=r.basis,
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


def _profit_loss_document(f: Formatter, r: ProfitLossOut) -> ReportDocument:
    rows = [ReportRow(["Sales", "", r.sales], strong=True)]
    if r.cost_of_goods:
        rows += [ReportRow(["Cost of goods", x.label, x.total]) for x in r.cost_of_goods]
        rows += [
            ReportRow(["Cost of goods", "Total", r.cost_of_goods_total]),
            ReportRow(["Gross profit", "", r.gross_profit], strong=True),
        ]
    rows += [ReportRow(["Expenses", x.label, x.total]) for x in r.expenses]
    if r.bad_debts:
        rows.append(ReportRow(["Expenses", "Bad debts (written off)", r.bad_debts]))
    rows += [
        ReportRow(["Expenses", "Total", r.expenses_total]),
        ReportRow(["Net profit", "", r.net_profit], strong=True),
    ]
    sales = "by payment date" if r.basis == TaxBasis.CASH else "by invoice date"
    return ReportDocument(
        name=f"profit-loss-{r.basis.value}-{r.date_from}-{r.date_to}",
        title="Profit & loss",
        facts=[("Period", _period(f, r.date_from, r.date_to)), ("Basis", BASIS_LABELS[r.basis])],
        header=["Section", "Account", "Amount"],
        widths=[1.6, 4.0, 1.6],
        right_from=2,
        rows=rows,
        note=(
            f"Sales {sales}, before tax. Expenses by expense date; accounts of type "
            '"cost of goods" are subtracted first.'
        ),
    )


@router.get("/profit-loss")
def profit_loss_report(
    auth: Reader,
    db: DbSession,
    date_from: date,
    date_to: date,
    basis: TaxBasis | None = BasisParam,
) -> ProfitLossOut:
    return _profit_loss(db, _org(db, auth), date_from, date_to, basis)


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


def _aging(db: DbSession, org: Organization) -> AgingReport:
    today = today_in(org.timezone)
    rows = reports.aging(db, org, today)
    out = [AgingRowOut(**vars(r), total=r.total) for r in rows]
    totals = reports.AgingRow(0, "Total", sum(r.invoices for r in rows))
    for name in reports.BUCKETS:
        setattr(totals, name, sum((getattr(r, name) for r in rows), Decimal(0)))
    return AgingReport(
        as_of=today, rows=out, totals=AgingRowOut(**vars(totals), total=totals.total)
    )


def _aging_document(f: Formatter, r: AgingReport) -> ReportDocument:
    def cells(x: AgingRowOut) -> list[Any]:
        buckets = [x.current, x.days_1_30, x.days_31_60, x.days_61_90, x.days_over_90]
        # Empty rather than 0.00, as on the screen, so the amounts owed stand out.
        return [x.party_name, x.invoices, *(b or None for b in buckets), x.total]

    return ReportDocument(
        name=f"receivables-aging-{r.as_of}",
        title="Receivables aging",
        facts=[("As of", f.date(r.as_of))],
        header=["Client", "Invoices", "Current", "1-30", "31-60", "61-90", "Over 90", "Total"],
        widths=[1.8, 0.72, *[0.78] * 6],
        rows=[*(ReportRow(cells(x)) for x in r.rows), ReportRow(cells(r.totals), strong=True)],
        note="What clients owe, by days past the due date.",
    )


@router.get("/aging")
def aging_report(auth: Reader, db: DbSession) -> AgingReport:
    return _aging(db, _org(db, auth))


# -- any report as CSV, PDF or email --------------------------------------------------------------

ReportName = Literal["sales", "sales-tax", "expenses", "profit-loss", "aging"]


@dataclass
class ReportParams:
    """The query of a report screen; each report uses the parts it needs."""

    date_from: date | None = None
    date_to: date | None = None
    group: str | None = None
    basis: TaxBasis | None = None


Params = Annotated[ReportParams, Depends()]


def _invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def _document(
    db: DbSession, org: Organization, name: ReportName, p: ReportParams
) -> ReportDocument:
    f = Formatter(org)
    if name == "aging":
        return _aging_document(f, _aging(db, org))
    if p.date_from is None or p.date_to is None:
        raise _invalid("date_from and date_to are required")
    if name == "sales":
        group = p.group or "month"
        if group not in get_args(reports.SalesGroup):
            raise _invalid(f"Unknown grouping {group!r}")
        report = _sales(db, org, p.date_from, p.date_to, group, p.basis)  # type: ignore[arg-type]
        return _sales_document(f, report)
    if name == "sales-tax":
        return _sales_tax_document(f, _sales_tax(db, org, p.date_from, p.date_to, p.basis))
    if name == "expenses":
        group = p.group or "account"
        if group not in get_args(reports.ExpenseGroup):
            raise _invalid(f"Unknown grouping {group!r}")
        expenses = _expenses(db, org, p.date_from, p.date_to, group)  # type: ignore[arg-type]
        return _expenses_document(f, expenses)
    return _profit_loss_document(f, _profit_loss(db, org, p.date_from, p.date_to, p.basis))


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Rate):
        return "" if value.value is None else str(value.value)
    if isinstance(value, Decimal | date):
        return str(value)
    return value


def _pdf(db: DbSession, org: Organization, report: ReportDocument) -> bytes:
    return report_pdf(db, org, report, datetime.now(ZoneInfo(org.timezone)))


@router.get("/{report}.csv")
def report_csv(report: ReportName, params: Params, auth: Reader, db: DbSession) -> Response:
    doc = _document(db, _org(db, auth), report, params)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(doc.header)
    for row in doc.rows:
        writer.writerow([_csv_value(v) for v in row.cells])
    if doc.summary:
        writer.writerow([])
        for row in doc.summary:
            writer.writerow([_csv_value(v) for v in row.cells])
    audit.record(db, "export", entity_type="report", entity_id=doc.name)
    db.commit()
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{doc.name}.csv"'},
    )


@router.get("/{report}.pdf")
def report_pdf_download(
    report: ReportName, params: Params, auth: Reader, db: DbSession
) -> Response:
    """The report as a document to save or print (opens in the browser)."""
    org = _org(db, auth)
    doc = _document(db, org, report, params)
    content = _pdf(db, org, doc)
    audit.record(db, "export", entity_type="report", entity_id=doc.name)
    db.commit()
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.name}.pdf"'},
    )


def _email_draft(
    db: DbSession, org: Organization, auth: Auth, report: ReportName, params: ReportParams
) -> emailing.Draft:
    doc = _document(db, org, report, params)
    pdf = Attachment(f"{doc.name}.pdf", _pdf(db, org, doc), "application/pdf")
    period = next(value for label, value in doc.facts if label in ("Period", "As of"))
    if report == "aging":
        period = f"as of {period}"
    return emailing.report_draft(db, org, auth.user, doc.title, period, pdf)


@router.get("/{report}/email")
def compose_report_email(
    report: ReportName, params: Params, auth: Editor, db: DbSession
) -> DraftOut:
    """The report by email, addressed to yourself, with the PDF attached."""
    return draft_out(_email_draft(db, _org(db, auth), auth, report, params))


@router.post("/{report}/email")
def send_report_email(
    report: ReportName, body: SendIn, params: Params, auth: Editor, db: DbSession
) -> MessageOut:
    org = _org(db, auth)
    return send_draft(db, org, _email_draft(db, org, auth, report, params), body, auth.user.id)
