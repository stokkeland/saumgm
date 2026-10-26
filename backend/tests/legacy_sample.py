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

"""A small synthetic copy of the Access database with the quirks found in the real one, so the
importer can be tested in CI without Access."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from saumgm.legacy_import.source import LegacyColumn, LegacyData, LegacyTable, Row

TYPE_NAMES = {
    bool: "BIT",
    int: "INTEGER",
    float: "DOUBLE",
    Decimal: "CURRENCY",
    datetime: "DATETIME",
    str: "VARCHAR",
}


def table(name: str, rows: list[Row]) -> LegacyTable:
    columns = []
    for key in rows[0]:
        value = next((r[key] for r in rows if r[key] is not None), "")
        columns.append(LegacyColumn(key, TYPE_NAMES[type(value)], 255, True))
    return LegacyTable(name, columns, rows)


def d(text: str) -> datetime:
    return datetime.fromisoformat(text)


def m(text: str) -> Decimal:
    return Decimal(text)


def file_row(fileno: str, nick: str, name: str, type_: str, **kw: Any) -> Row:
    return {"fileno": fileno, "nick": nick, "Name": name, "Type": type_, "FSdirectory": None,
            "created": 0, "Inactive": 0} | kw  # fmt: skip


def client_row(client_id: int, file_no: str, nick: str, **kw: Any) -> Row:
    base = dict.fromkeys(
        ["Company", "Name", "Address1", "Address2", "City", "State", "Zip", "Country", "Phone",
         "Fax", "Cellular", "EMail", "url", "Notes", "BalanceDate", "AccountsBalance",
         "ActiveBilling"]
    )  # fmt: skip
    return base | {"ClientID": client_id, "Nick": nick, "FileNo": file_no, "Native": False,
                   "Created": 0, "Closed": 0} | kw  # fmt: skip


def vendor_row(vendor_id: int, file_no: str, nick: str, company: str, **kw: Any) -> Row:
    base = dict.fromkeys(
        ["Address1", "Address2", "City", "State", "Zip", "Country", "Phone", "Fax", "Email",
         "Notes", "url", "priContactName", "priContactPhone", "priContactEmail"]
    )  # fmt: skip
    return base | {"VendorID": vendor_id, "Nick": nick, "FileNo": file_no, "Company": company,
                   "Created": 0, "Closed": 0} | kw  # fmt: skip


def product_row(pid: int, sku: str, nick: str, price: str, unit: str, **kw: Any) -> Row:
    return {"productID": pid, "sku": sku, "nick": nick, "description": None,
            "create_date": d("2005-01-01"), "update_date": None, "inactive_date": None,
            "price": m(price), "discount": 1.0, "cost_purchase": None, "last_purchase": None,
            "unit": unit, "recurrable": False, "recurPeriod": 0} | kw  # fmt: skip


def invoice_row(no: int, client: int, status: str, date: str, terms: str, **kw: Any) -> Row:
    base = dict.fromkeys(
        ["BillCompany", "BillName", "BillAddress1", "BillAddress2", "BillCity", "BillZip",
         "BillState", "BillCountry", "BillPhones", "BillFax", "email", "AdjustmentNote",
         "SalesTaxLocation", "Final", "Notes"]
    )  # fmt: skip
    return base | {"InvoiceNo": no, "Client": client, "Status": status, "InvDate": d(date),
                   "Terms": terms, "SubTotal": m("0"), "Adjustment": m("0"), "Freight": m("0"),
                   "SalesTax": m("0"), "OriginallyDue": m("0")} | kw  # fmt: skip


def line_row(lid: int, invoice: int | None, product: int, descr: str, cost: str, disc: str,
             qty: float, tax: str = "0", unit: str = "ea") -> Row:  # fmt: skip
    return {"InvoiceDtlID": lid, "Invoice": invoice, "Product": product, "ItemDescr": descr,
            "ItemCost": m(cost), "ItemDiscount": m(disc), "ItemTax": m(tax), "ItemQTY": qty,
            "ItemUnit": unit}  # fmt: skip


def sample_data() -> LegacyData:
    tables = [
        table("tblFile", [
            file_row("00010000", "SAU", "Example Co", "B"),
            file_row("00000001", "CASH", "Cash Sales", "C"),
            file_row("00010001", "ACME", "Acme", "C", created=20040808),
            file_row("00010002", "BOB", "Bob Jones", "C"),
            file_row("00010003", "HOST", "Hosting Inc", "V"),
            file_row("00010004", "BANK", "First Bank", "M"),
            file_row("00010005", "GONE", "Gone Client", "C", Inactive=1),
        ]),
        table("tblClient", [
            client_row(1, "00000001", "00000001", Company="Cash Sales"),
            client_row(2, "00010001", "ACME", Company="Acme Corporation", Name="Ann Smith",
                       Address1="1 Main St", City="Salamanca", State="NY", Zip="14779",
                       Country="USA", Cellular="555-0101", EMail="ann@acme.example"),
            client_row(3, "00010002", "BOB", Name="Bob Jones", City="Toronto", State="ON",
                       Closed=1, Native=True),
        ]),
        table("tblVendor", [
            vendor_row(1, "00010003", "HOST", "Hosting Inc", priContactName="Hal Host",
                       priContactEmail="hal@host.example"),
            vendor_row(2, "00010004", "BANK", "First Bank"),
        ]),
        table("tblExpenseAccount", [
            {"expAccountID": 1, "expAccount": 4130, "nick": "Internet", "descr": "Hosting",
             "cogs": False},
            {"expAccountID": 2, "expAccount": 4210, "nick": "Resold domains", "descr": None,
             "cogs": True},
        ]),
        table("tblProduct", [
            # 0.95 as Access stores it in a SINGLE column
            product_row(1, "WH-1", "Web Hosting Annual", "10", "Month", recurrable=True,
                        recurPeriod=12, discount=0.949999988079071),
            product_row(2, "CON-1", "Consulting", "55", "Hour"),
            product_row(3, "HW-1", "Cable", "0.14", "Foot", inactive_date=d("2010-01-01")),
        ]),
        table("tblInvoiceHdr", [
            invoice_row(1001, 2, "Paid", "2019-01-10", "Net per 30 days", BillState="NY",
                        BillCompany="Acme Corporation", SubTotal=m("251.5"),
                        SalesTax=m("11"), OriginallyDue=m("262.5"),
                        SalesTaxLocation="Salamanca NY"),
            invoice_row(1002, 3, "Cancelled", "2020-02-01", "50/50 Start/Completion",
                        SubTotal=m("14"), OriginallyDue=m("14")),
            invoice_row(1003, 2, "New", "2024-05-05", "Cash", SubTotal=m("113.75"),
                        Adjustment=None, OriginallyDue=m("113.75")),
        ]),
        table("tblInvoiceDtl", [
            line_row(1, 1001, 1, "Hosting", "10", "0.5", 12.0, unit="Month"),
            line_row(2, 1001, 2, "Consulting", "55", "0", 2.5, tax="4.4", unit="Hour"),
            line_row(3, 1002, 3, "Cable", "0.14", "0", 100.0, unit="Foot"),
            line_row(4, 1003, 2, "Consulting", "55", "20", 3.25, unit="Hour"),
            line_row(5, None, 1, "Abandoned line", "69", "0", 1.0),
        ]),
        table("tblInvoicePayment", [
            {"InvoicePaymntID": 1, "InvoiceNo": 1001, "POT": d("2019-02-01"),
             "Amount": m("262.5"), "SalesTax": m("11"), "TaxableAmount": m("137.5"),
             "chargePaymentID": 7},
            {"InvoicePaymntID": 2, "InvoiceNo": 1003, "POT": None, "Amount": m("50"),
             "SalesTax": m("0"), "TaxableAmount": m("0"), "chargePaymentID": 0},
            {"InvoicePaymntID": 3, "InvoiceNo": 1003, "POT": d("2024-06-01"),
             "Amount": m("63.75"), "SalesTax": m("0"), "TaxableAmount": m("0"),
             "chargePaymentID": 0},
        ]),
        table("tblPaymentReceived", [
            {"trxID": 7, "recFrom": "00010001", "recMethod": "Postal Mail",
             "recPOT": d("2019-02-01"), "payAmount": m("262.5"), "payMethod": "Check",
             "payDescr": "Check #1234"},
            {"trxID": 8, "recFrom": "00010001", "recMethod": "Personally Delivered",
             "recPOT": d("2024-05-30"), "payAmount": m("63.75"), "payMethod": "Cash",
             "payDescr": "For invoice 1003"},
            {"trxID": 9, "recFrom": "00010002", "recMethod": "Postal Mail",
             "recPOT": d("2005-02-04"), "payAmount": m("50"), "payMethod": "Check",
             "payDescr": "Donation"},
        ]),
        table("tblDepositHdr", [
            {"depositID": 1, "depositDate": d("2019-02-05"), "depositNotes": "Feb"},
            {"depositID": 2, "depositDate": None, "depositNotes": "No date"},
        ]),
        table("tblDepositDtl", [
            {"depositItemId": 1, "depositId": 1, "depAmount": m("262.5"), "depDescr": "Acme"},
            {"depositItemId": 2, "depositId": 2, "depAmount": m("10"), "depDescr": "Misc"},
            {"depositItemId": 3, "depositId": None, "depAmount": m("99"), "depDescr": "Orphan"},
        ]),
        table("tblExpenseJournal", [
            {"trxJournalID": 1, "trxDate": d("2019-03-01"), "entryDate": d("2019-03-02"),
             "descr": "Hosting", "fileNo": "10003", "refFileNo": "00010000", "refInvNo": "A-1"},
            {"trxJournalID": 2, "trxDate": d("2020-01-01"), "entryDate": d("2020-01-01"),
             "descr": "Unknown vendor", "fileNo": "99999999", "refFileNo": None,
             "refInvNo": None},
        ]),
        table("tblExpenseTrx", [
            {"expTrxID": 1, "ExpJorunalID": 1, "trxAccount": 1, "amount": m("100")},
            {"expTrxID": 2, "ExpJorunalID": 1, "trxAccount": 2, "amount": m("20.5")},
            {"expTrxID": 3, "ExpJorunalID": 2, "trxAccount": 1, "amount": m("5")},
            {"expTrxID": 4, "ExpJorunalID": None, "trxAccount": 1, "amount": m("0")},
        ]),
        table("tblProjectHdr", [{"projectID": 1, "nick": "Old project"}]),
    ]  # fmt: skip
    return {t.name: t for t in tables}
