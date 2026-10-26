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

from fastapi.testclient import TestClient

from saumgm.enums import FilingFrequency
from saumgm.models import Invoice, TaxRegistration
from saumgm.services.invoices import written_off_tax
from saumgm.services.tax_periods import is_period_start, period_containing, periods_between
from tests.api_helpers import contact, issued_invoice, ok, ok_list

# -- write-offs -----------------------------------------------------------------------------------


def test_write_off_clears_the_balance_but_keeps_the_sale(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    bad = issued_invoice(owner_client, acme["id"], "300", "2019-01-01")
    owner_client.post(
        "/api/payments",
        json={"party_id": acme["id"], "received_date": "2019-02-01", "amount": "100",
              "allocations": [{"invoice_id": bad["id"], "amount": "100"}]},
    )  # fmt: skip

    written = ok(
        owner_client.post(
            f"/api/invoices/{bad['id']}/write-off",
            json={"reason": "Client went out of business", "write_off_date": "2020-06-30"},
        )
    )
    assert written["payment_status"] == "written_off"
    assert (written["balance_due"], written["write_off_amount"]) == ("0.0000", "200.0000")
    assert written["is_overdue"] is False
    assert written["total"] == "300.0000"  # the sale is unchanged

    balance = ok(owner_client.get(f"/api/contacts/{acme['id']}/balance"))
    assert (balance["receivable"], balance["overdue"]) == ("0.0000", "0.0000")
    open_list = ok(owner_client.get("/api/invoices", params={"payment": "open"}))
    assert open_list["total"] == 0
    written_list = ok(owner_client.get("/api/invoices", params={"payment": "written_off"}))
    assert [i["id"] for i in written_list["items"]] == [bad["id"]]

    # locked while written off
    revise = owner_client.post(f"/api/invoices/{bad['id']}/revise", json={"reason": "fix typo"})
    assert revise.status_code == 409
    again = owner_client.post(f"/api/invoices/{bad['id']}/write-off", json={"reason": "again"})
    assert again.status_code == 409

    # they paid after all
    undone = ok(
        owner_client.post(
            f"/api/invoices/{bad['id']}/undo-write-off", json={"reason": "Paid in full at last"}
        )
    )
    assert (undone["payment_status"], undone["balance_due"]) == ("partially_paid", "200.0000")


def test_bulk_write_off_reports_what_was_skipped(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    first = issued_invoice(owner_client, acme["id"], "10", "2018-01-01")
    second = issued_invoice(owner_client, acme["id"], "20", "2018-02-01")
    draft = ok(
        owner_client.post(
            "/api/invoices",
            json={"party_id": acme["id"], "lines": [{"description": "x", "unit_price": "5"}]},
        ),
        201,
    )
    result = ok(
        owner_client.post(
            "/api/invoices/write-off",
            json={"invoice_ids": [first["id"], second["id"], draft["id"], 999999],
                  "reason": "Uncollectible"},
        )
    )  # fmt: skip
    assert [w["amount"] for w in result["written_off"]] == ["10.0000", "20.0000"]
    assert [s["invoice_id"] for s in result["skipped"]] == [draft["id"], 999999]
    assert ok(owner_client.get("/api/dashboard"))["receivable"] == "0.0000"


def test_tax_share_of_a_write_off() -> None:
    invoice = Invoice(total=Decimal("108"), tax_total=Decimal("8"), write_off_amount=Decimal("54"))
    assert written_off_tax(invoice) == Decimal("4.00")


# -- tax periods ----------------------------------------------------------------------------------


def registration(frequency: FilingFrequency, start_month: int = 1) -> TaxRegistration:
    return TaxRegistration(filing_frequency=frequency, period_start_month=start_month)


def test_new_york_quarters_and_year() -> None:
    ny_quarterly = registration(FilingFrequency.QUARTERLY, 3)
    assert period_containing(ny_quarterly, date(2026, 1, 15)) == (
        date(2025, 12, 1),
        date(2026, 2, 28),
    )
    assert period_containing(ny_quarterly, date(2026, 3, 1)) == (
        date(2026, 3, 1),
        date(2026, 5, 31),
    )
    assert period_containing(ny_quarterly, date(2026, 11, 30)) == (
        date(2026, 9, 1),
        date(2026, 11, 30),
    )

    ny_annual = registration(FilingFrequency.ANNUAL, 3)
    assert period_containing(ny_annual, date(2026, 2, 10)) == (date(2025, 3, 1), date(2026, 2, 28))
    assert period_containing(ny_annual, date(2024, 3, 1)) == (date(2024, 3, 1), date(2025, 2, 28))
    assert is_period_start(ny_annual, date(2026, 3, 1))
    assert not is_period_start(ny_annual, date(2026, 1, 1))


def test_calendar_and_monthly_periods() -> None:
    quarterly = registration(FilingFrequency.QUARTERLY)
    assert period_containing(quarterly, date(2026, 5, 5)) == (date(2026, 4, 1), date(2026, 6, 30))
    monthly = registration(FilingFrequency.MONTHLY)
    assert period_containing(monthly, date(2024, 2, 10)) == (date(2024, 2, 1), date(2024, 2, 29))
    starts = [s for s, _ in periods_between(quarterly, date(2026, 1, 1), date(2026, 12, 31))]
    assert starts == [date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1)]


def test_periods_filings_and_revision_warning(owner_client: TestClient) -> None:
    ny = next(
        j for j in ok_list(owner_client.get("/api/tax/jurisdictions")) if j["code"] == "US-NY"
    )
    reg = ok(
        owner_client.post(
            "/api/tax/registrations",
            json={"jurisdiction_id": ny["id"], "effective_from": "2004-01-01",
                  "filing_frequency": "quarterly", "period_start_month": 3},
        ),
        201,
    )  # fmt: skip
    periods = ok_list(
        owner_client.get("/api/tax/periods", params={"registration_id": reg["id"], "year": 2026})
    )
    assert [p["period_start"] for p in periods] == [
        "2026-03-01", "2026-06-01", "2026-09-01", "2026-12-01",
    ]  # fmt: skip

    wrong = owner_client.post(
        "/api/tax/filings",
        json={"registration_id": reg["id"], "period_start": "2026-04-01", "filed_on": "2026-06-20"},
    )
    assert wrong.status_code == 409
    filing = ok(
        owner_client.post(
            "/api/tax/filings",
            json={"registration_id": reg["id"], "period_start": "2026-03-01",
                  "filed_on": "2026-06-20", "amount_paid": "123.45", "reference": "CONF-1"},
        ),
        201,
    )  # fmt: skip
    assert filing["period_end"] == "2026-05-31"

    acme = contact(owner_client, "ACME")
    invoice = issued_invoice(owner_client, acme["id"], "100", "2026-04-15")
    revised = ok(
        owner_client.post(
            f"/api/invoices/{invoice['id']}/revise", json={"reason": "Wrong amount", "notes": "x"}
        )
    )
    assert "already filed" in revised["warnings"][0]
