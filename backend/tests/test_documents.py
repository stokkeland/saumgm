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

import io
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader
from sqlalchemy.orm import Session

from saumgm.enums import AddressType, InvoiceStatus
from saumgm.models import Invoice, Organization, OrganizationAddress
from tests.api_helpers import contact, issued_invoice, ok


def pdf_text(response: object) -> str:
    assert response.status_code == 200, response.text  # type: ignore[attr-defined]
    assert response.headers["content-type"] == "application/pdf"  # type: ignore[attr-defined]
    reader = PdfReader(io.BytesIO(response.content))  # type: ignore[attr-defined]
    return "\n".join(page.extract_text() for page in reader.pages)


def test_issued_invoice_pdf_is_kept(
    owner_client: TestClient, db_session: Session, org: Organization
) -> None:
    owner_client.patch(
        "/api/settings/organization",
        json={"payable_to": "J. Owner", "footer_text": "Thank you for your business"},
    )
    db_session.add_all(
        [
            OrganizationAddress(
                organization_id=org.id,
                address_type=AddressType.REMIT,
                line1="1 Old Road",
                city="Fillmore",
                region="NY",
                effective_to=date(2019, 12, 31),
            ),
            OrganizationAddress(
                organization_id=org.id,
                address_type=AddressType.REMIT,
                line1="2 New Street",
                city="Olean",
                region="NY",
            ),
        ]
    )
    db_session.flush()
    acme = contact(owner_client, "ACME")
    invoice = issued_invoice(owner_client, acme["id"], "1234.5", "2026-03-01")
    assert db_session.get(Invoice, invoice["id"]).pdf_file_id is not None  # type: ignore[union-attr]

    text = pdf_text(owner_client.get(f"/api/invoices/{invoice['id']}/pdf"))
    assert "INVOICE" in text and invoice["number"] in text
    assert "Work" in text and "$1,234.50" in text
    assert "J. Owner" in text and "2 New Street" in text and "1 Old Road" not in text
    assert "Thank you for your business" in text and "Page 1 of 1" in text

    old = issued_invoice(owner_client, acme["id"], "10", "2018-05-01")
    assert "1 Old Road" in pdf_text(owner_client.get(f"/api/invoices/{old['id']}/pdf"))


def test_revisions_keep_the_earlier_document(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    invoice = issued_invoice(owner_client, acme["id"], "100")
    owner_client.post(
        f"/api/invoices/{invoice['id']}/revise",
        json={"reason": "Price change", "lines": [{"description": "Work", "unit_price": "90"}]},
    )
    assert "$90.00" in pdf_text(owner_client.get(f"/api/invoices/{invoice['id']}/pdf"))
    before = pdf_text(owner_client.get(f"/api/invoices/{invoice['id']}/revisions/0/pdf"))
    assert "$100.00" in before and "$90.00" not in before


def test_drafts_and_imported_invoices_render_on_demand(
    owner_client: TestClient, db_session: Session, org: Organization
) -> None:
    acme = contact(owner_client, "ACME")
    draft = ok(
        owner_client.post(
            "/api/invoices",
            json={"party_id": acme["id"], "lines": [{"description": "Plan", "unit_price": "5"}]},
        ),
        201,
    )
    assert "DRAFT" in pdf_text(owner_client.get(f"/api/invoices/{draft['id']}/pdf"))

    old = Invoice(
        organization_id=org.id,
        party_id=acme["id"],
        number="1124",
        status=InvoiceStatus.ISSUED,
        is_historical=True,
        subtotal=Decimal(40),
        total=Decimal(40),
        issue_date=date(2004, 8, 10),
    )
    db_session.add(old)
    db_session.flush()
    assert "1124" in pdf_text(owner_client.get(f"/api/invoices/{old.id}/pdf"))


def test_receipt_and_deposit_slip(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    invoice = issued_invoice(owner_client, acme["id"], "75")
    payment = ok(
        owner_client.post(
            "/api/payments",
            json={
                "party_id": acme["id"],
                "received_date": "2026-02-01",
                "amount": "100",
                "method": "check",
                "reference": "4321",
                "allocations": [{"invoice_id": invoice["id"], "amount": "75"}],
            },
        ),
        201,
    )
    receipt = pdf_text(owner_client.get(f"/api/payments/{payment['id']}/receipt.pdf"))
    assert "RECEIPT" in receipt and "$100.00" in receipt and "#4321" in receipt
    assert f"Invoice {invoice['number']}" in receipt and "Credit on account" in receipt

    deposit = ok(
        owner_client.post(
            "/api/deposits",
            json={
                "deposit_date": "2026-02-02",
                "payment_ids": [payment["id"]],
                "items": [{"amount": "20", "description": "Cash sale"}],
            },
        ),
        201,
    )
    slip = pdf_text(owner_client.get(f"/api/deposits/{deposit['id']}/slip.pdf"))
    assert "DEPOSIT" in slip and "ACME Inc" in slip and "Cash sale" in slip and "$120.00" in slip


def test_logo_upload(owner_client: TestClient) -> None:
    png = io.BytesIO()
    Image.new("RGB", (300, 80), "blue").save(png, format="PNG")
    response = owner_client.put(
        "/api/settings/logo", files={"file": ("logo.png", png.getvalue(), "image/png")}
    )
    assert response.status_code == 204
    logo = owner_client.get("/api/settings/logo")
    assert logo.status_code == 200 and logo.headers["content-type"] == "image/png"

    acme = contact(owner_client, "ACME")
    invoice = issued_invoice(owner_client, acme["id"], "10")
    reader = PdfReader(io.BytesIO(owner_client.get(f"/api/invoices/{invoice['id']}/pdf").content))
    assert len(reader.pages[0].images) == 1

    wrong = owner_client.put(
        "/api/settings/logo", files={"file": ("x.txt", b"hello", "text/plain")}
    )
    assert wrong.status_code == 415
