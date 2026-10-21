"""Proof that the import is complete: counts and money totals computed from the Access rows must
match what is stored in the new database, to the cent (4 decimals for stored amounts)."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.legacy_import import convert as cv
from saumgm.legacy_import.mapping import ImportResult
from saumgm.legacy_import.source import LegacyData, Row
from saumgm.models import (
    Account,
    CatalogItem,
    Deposit,
    DepositItem,
    Expense,
    ExpenseLine,
    Invoice,
    InvoiceLine,
    Party,
    Payment,
    PaymentAllocation,
    TaxExemption,
)

Bucket = str  # e.g. "2019" or "4130 / 2019"


@dataclass
class Check:
    name: str
    expected: Any
    actual: Any

    @property
    def ok(self) -> bool:
        return bool(self.expected == self.actual)


def _year(value: Any) -> str:
    day = cv.to_date(value)
    return str(day.year) if day else "no date"


def _sum_by(
    rows: Iterable[Any], key: Callable[[Any], Bucket], amount: Callable[[Any], Decimal]
) -> dict[Bucket, Decimal]:
    totals: dict[Bucket, Decimal] = defaultdict(lambda: Decimal("0.0000"))
    for row in rows:
        totals[key(row)] += amount(row)
    return dict(sorted(totals.items()))


def reconcile(session: Session, data: LegacyData, result: ImportResult) -> list[Check]:
    org_id = result.organization_id

    def rows(table: str) -> list[Row]:
        return data[table].rows

    def all_of(model: Any) -> list[Any]:
        stmt = select(model)
        if hasattr(model, "organization_id"):
            stmt = stmt.where(model.organization_id == org_id)
        return list(session.scalars(stmt))

    parties = all_of(Party)
    invoices = {i.id: i for i in all_of(Invoice)}
    payments = {p.id: p for p in all_of(Payment)}
    deposits = {d.id: d for d in all_of(Deposit)}
    expenses = {e.id: e for e in all_of(Expense)}
    accounts = {a.id: a for a in all_of(Account)}
    lines = [ln for ln in all_of(InvoiceLine) if ln.invoice_id in invoices]
    allocations = [a for a in all_of(PaymentAllocation) if a.payment_id in payments]
    deposit_items = [d for d in all_of(DepositItem) if d.deposit_id in deposits]
    expense_lines = [e for e in all_of(ExpenseLine) if e.expense_id in expenses]

    old_invoice_years = {h["InvoiceNo"]: _year(h["InvDate"]) for h in rows("tblInvoiceHdr")}
    old_deposit_years = {h["depositID"]: _year(h["depositDate"]) for h in rows("tblDepositHdr")}
    old_journal_years = {j["trxJournalID"]: _year(j["trxDate"]) for j in rows("tblExpenseJournal")}
    old_account_codes = {a["expAccountID"]: str(a["expAccount"]) for a in rows("tblExpenseAccount")}
    valid_deposit_items = [d for d in rows("tblDepositDtl") if d["depositId"] in old_deposit_years]
    # Lines/payments without a (known) invoice are reported by the mapping and not imported.
    valid_lines = [d for d in rows("tblInvoiceDtl") if d["Invoice"] in old_invoice_years]
    valid_payments = [p for p in rows("tblInvoicePayment") if p["InvoiceNo"] in old_invoice_years]

    checks = [
        Check("Parties (tblFile)", len(rows("tblFile")), len(parties)),
        Check(
            "Parties with a client record (tblClient)",
            len(rows("tblClient")),
            sum(1 for p in parties if p.legacy_data and "client" in p.legacy_data),
        ),
        Check(
            "Parties with a vendor record (tblVendor)",
            len(rows("tblVendor")),
            sum(1 for p in parties if p.legacy_data and "vendor" in p.legacy_data),
        ),
        Check(
            "Tax exemptions from the Native flag (tblClient)",
            sum(1 for c in rows("tblClient") if c["Native"]),
            sum(1 for e in all_of(TaxExemption) if e.party_id in {p.id for p in parties}),
        ),
        Check("Catalog items (tblProduct)", len(rows("tblProduct")), len(all_of(CatalogItem))),
        Check("Accounts (tblExpenseAccount)", len(rows("tblExpenseAccount")), len(accounts)),
        Check("Invoices (tblInvoiceHdr)", len(rows("tblInvoiceHdr")), len(invoices)),
        Check("Invoice lines with an invoice (tblInvoiceDtl)", len(valid_lines), len(lines)),
        Check(
            "Payments with an invoice (tblInvoicePayment)", len(valid_payments), len(allocations)
        ),
        Check(
            "Receipts merged or listed (tblPaymentReceived)",
            len(rows("tblPaymentReceived")),
            len(result.receipt_matches) + len(result.unmatched_receipts),
        ),
        Check("Deposits (tblDepositHdr)", len(rows("tblDepositHdr")), len(deposits)),
        Check(
            "Deposit lines with a deposit (tblDepositDtl)",
            len(valid_deposit_items),
            len(deposit_items),
        ),
        Check("Expenses (tblExpenseJournal)", len(rows("tblExpenseJournal")), len(expenses)),
        Check(
            "Expense lines with an expense (tblExpenseTrx)",
            sum(1 for t in rows("tblExpenseTrx") if t["ExpJorunalID"] in old_journal_years),
            len(expense_lines),
        ),
    ]

    def money_check(name: str, old: dict[Bucket, Decimal], new: dict[Bucket, Decimal]) -> None:
        for bucket in sorted(set(old) | set(new)):
            checks.append(
                Check(
                    f"{name} {bucket}",
                    old.get(bucket, Decimal("0.0000")),
                    new.get(bucket, Decimal("0.0000")),
                )
            )

    invoice_fields = [
        ("Invoice subtotal", "SubTotal", "subtotal"),
        ("Invoice sales tax", "SalesTax", "tax_total"),
        ("Invoice freight", "Freight", "freight"),
        ("Invoice adjustment", "Adjustment", "adjustment"),
        ("Invoice total", "OriginallyDue", "total"),
    ]
    for label, old_field, new_field in invoice_fields:
        money_check(
            label,
            _sum_by(rows("tblInvoiceHdr"), lambda h: _year(h["InvDate"]),
                    lambda h, f=old_field: cv.dec0(h[f])),  # type: ignore[misc]
            _sum_by(invoices.values(), lambda i: _year(i.issue_date),
                    lambda i, f=new_field: getattr(i, f)),  # type: ignore[misc]
        )  # fmt: skip

    money_check(
        "Invoice line totals",
        _sum_by(
            valid_lines,
            lambda d: old_invoice_years[d["Invoice"]],
            lambda d: cv.line_total(
                cv.dec0(d["ItemCost"]), cv.dec0(d["ItemDiscount"]), cv.dec0(d["ItemQTY"])
            ),
        ),
        _sum_by(
            lines, lambda ln: _year(invoices[ln.invoice_id].issue_date), lambda ln: ln.line_total
        ),
    )

    payment_fields = [
        ("Payments received", "Amount", lambda a: a.amount),
        ("Payment sales tax", "SalesTax", lambda a: a.legacy_sales_tax or Decimal("0.0000")),
        ("Payment taxable amount", "TaxableAmount",
         lambda a: a.legacy_taxable_amount or Decimal("0.0000")),
    ]  # fmt: skip
    for label, old_field, new_amount in payment_fields:
        money_check(
            label,
            _sum_by(valid_payments, lambda p: _year(p["POT"]),
                    lambda p, f=old_field: cv.dec0(p[f])),  # type: ignore[misc]
            _sum_by(allocations, lambda a: _year(payments[a.payment_id].received_date),
                    new_amount),
        )  # fmt: skip

    money_check(
        "Deposits",
        _sum_by(valid_deposit_items, lambda d: old_deposit_years[d["depositId"]],
                lambda d: cv.dec0(d["depAmount"])),
        _sum_by(deposit_items, lambda d: _year(deposits[d.deposit_id].deposit_date),
                lambda d: d.amount),
    )  # fmt: skip

    money_check(
        "Expenses",
        _sum_by(
            (t for t in rows("tblExpenseTrx") if t["ExpJorunalID"] in old_journal_years),
            lambda t: f"{old_account_codes.get(t['trxAccount'], '?')} / "
                      f"{old_journal_years[t['ExpJorunalID']]}",
            lambda t: cv.dec0(t["amount"]),
        ),
        _sum_by(
            expense_lines,
            lambda e: f"{accounts[e.account_id].code} / "
                      f"{_year(expenses[e.expense_id].expense_date)}",
            lambda e: e.amount,
        ),
    )  # fmt: skip
    return checks
