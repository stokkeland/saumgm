from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saumgm.enums import InvoiceStatus
from saumgm.models import AuditLog, Invoice, InvoiceTax, Organization, Payment, PaymentAllocation
from tests.tax_setup import NewYork, setup_new_york


@pytest.fixture
def ny(db_session: Session, org: Organization) -> NewYork:
    return setup_new_york(db_session, org)


@pytest.fixture
def acme(owner_client: TestClient) -> dict[str, Any]:
    response = owner_client.post(
        "/api/contacts",
        json={
            "short_code": "ACME",
            "name": "Acme Corporation",
            "roles": ["client"],
            "default_terms_days": 30,
            "addresses": [{"address_type": "billing", "is_default": True, "line1": "1 Main St",
                           "city": "Olean", "region": "NY", "country_code": "US"}],
            "people": [{"name": "Ann Smith", "email": "ann@acme.example", "is_primary": True}],
        },
    )  # fmt: skip
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture
def items(owner_client: TestClient, ny: NewYork) -> dict[str, dict[str, Any]]:
    def item(**body: Any) -> dict[str, Any]:
        response = owner_client.post("/api/catalog", json=body)
        assert response.status_code == 201, response.text
        result: dict[str, Any] = response.json()
        return result

    return {
        "router": item(name="Router", item_type="goods", price="200", unit="ea",
                       tax_category_id=ny.goods.id),
        "hosting": item(name="Web Hosting", item_type="subscription", price="10", unit="Month",
                        billing_interval_months=12, default_discount_pct="5",
                        tax_category_id=ny.digital.id),
    }  # fmt: skip


def new_invoice(
    client: TestClient, party_id: int, lines: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    response = client.post("/api/invoices", json={"party_id": party_id, "lines": lines} | extra)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_draft_uses_contact_and_catalog_defaults(
    owner_client: TestClient, acme: dict[str, Any], items: dict[str, Any], ny: NewYork
) -> None:
    draft = new_invoice(
        owner_client,
        acme["id"],
        [
            {"catalog_item_id": items["router"]["id"]},
            {"catalog_item_id": items["hosting"]["id"], "quantity": "12"},
        ],
    )
    assert draft["status"] == "draft" and draft["number"] is None
    assert (draft["bill_to_company"], draft["bill_to_name"]) == ("Acme Corporation", "Ann Smith")
    assert draft["bill_to_email"] == "ann@acme.example"
    assert (draft["terms_days"], draft["terms_text"]) == (30, "Net 30 days")
    assert draft["tax_jurisdiction_id"] == ny.state.id  # from the NY billing address

    router, hosting = draft["lines"]
    assert (router["description"], router["line_total"]) == ("Router", "200.0000")
    assert hosting["unit_discount"] == "0.5000"  # 5% default discount
    assert hosting["line_total"] == "114.0000"  # (10 - 0.50) x 12
    # Only the router is taxable in NY (hosting is "digital"); 4% state
    assert [(t["name"], t["amount"]) for t in draft["taxes"]] == [("New York State", "8.0000")]
    assert (draft["subtotal"], draft["tax_total"], draft["total"]) == (
        "314.0000",
        "8.0000",
        "322.0000",
    )


def test_issue_assigns_number_and_due_date(
    owner_client: TestClient, acme: dict[str, Any], items: dict[str, Any]
) -> None:
    draft = new_invoice(owner_client, acme["id"], [{"catalog_item_id": items["router"]["id"]}])
    issued = owner_client.post(
        f"/api/invoices/{draft['id']}/issue", json={"issue_date": "2026-10-01"}
    ).json()
    assert issued["status"] == "issued" and issued["number"] == "1"
    assert issued["due_date"] == "2026-10-31"
    assert issued["payment_status"] == "unpaid"

    second = new_invoice(owner_client, acme["id"], [{"description": "Labor", "unit_price": "50"}])
    assert owner_client.post(f"/api/invoices/{second['id']}/issue", json={}).json()["number"] == "2"

    # issued invoices are not edited directly
    patch = owner_client.patch(f"/api/invoices/{draft['id']}", json={"notes": "x"})
    assert patch.status_code == 409
    assert owner_client.delete(f"/api/invoices/{draft['id']}").status_code == 409


def test_empty_drafts_cannot_be_issued(owner_client: TestClient, acme: dict[str, Any]) -> None:
    draft = new_invoice(owner_client, acme["id"], [])
    assert owner_client.post(f"/api/invoices/{draft['id']}/issue", json={}).status_code == 409


def test_draft_edit_and_delete(owner_client: TestClient, acme: dict[str, Any]) -> None:
    draft = new_invoice(owner_client, acme["id"], [{"description": "A", "unit_price": "10"}])
    updated = owner_client.patch(
        f"/api/invoices/{draft['id']}",
        json={"lines": [{"description": "B", "unit_price": "20", "quantity": "2",
                         "discount_pct": "10"}], "freight": "5"},
    ).json()  # fmt: skip
    assert updated["lines"][0]["line_total"] == "36.0000"  # (20 - 2) x 2
    assert updated["total"] == "41.0000"
    assert owner_client.delete(f"/api/invoices/{draft['id']}").status_code == 204


def test_revise_keeps_the_previous_version(
    owner_client: TestClient, acme: dict[str, Any], db_session: Session
) -> None:
    draft = new_invoice(owner_client, acme["id"], [{"description": "Work", "unit_price": "100"}])
    owner_client.post(f"/api/invoices/{draft['id']}/issue", json={"issue_date": "2026-10-01"})

    no_reason = owner_client.post(f"/api/invoices/{draft['id']}/revise", json={})
    assert no_reason.status_code == 422

    revised = owner_client.post(
        f"/api/invoices/{draft['id']}/revise",
        json={"reason": "Wrong hours billed", "lines": [{"description": "Work",
              "unit_price": "100", "quantity": "1.5"}]},
    ).json()  # fmt: skip
    assert revised["total"] == "150.0000" and revised["number"] == "1"
    assert revised["revision_no"] == 1
    assert [r["reason"] for r in revised["revisions"]] == ["Wrong hours billed"]

    old = owner_client.get(f"/api/invoices/{draft['id']}/revisions/0").json()
    assert old["snapshot"]["total"] == "100.0000"
    assert old["snapshot"]["lines"][0]["quantity"] == "1.0000"

    entry = db_session.scalars(select(AuditLog).where(AuditLog.action == "revise")).one()
    assert entry.reason == "Wrong hours billed"


def test_revise_warns_when_payments_exceed_the_total(
    owner_client: TestClient, acme: dict[str, Any], db_session: Session, org: Organization
) -> None:
    draft = new_invoice(owner_client, acme["id"], [{"description": "Work", "unit_price": "100"}])
    owner_client.post(f"/api/invoices/{draft['id']}/issue", json={})
    payment = Payment(organization_id=org.id, party_id=acme["id"], amount=Decimal(100))
    payment.allocations.append(PaymentAllocation(invoice_id=draft["id"], amount=Decimal(100)))
    db_session.add(payment)
    db_session.flush()

    revised = owner_client.post(
        f"/api/invoices/{draft['id']}/revise",
        json={"reason": "Discount agreed", "lines": [{"description": "Work", "unit_price": "80"}]},
    ).json()
    assert revised["payment_status"] == "overpaid"
    assert "exceed the new total by 20" in revised["warnings"][0]

    # paid invoices cannot be voided
    void = owner_client.post(f"/api/invoices/{draft['id']}/void", json={"reason": "duplicate"})
    assert void.status_code == 409


def test_void(owner_client: TestClient, acme: dict[str, Any]) -> None:
    draft = new_invoice(owner_client, acme["id"], [{"description": "Work", "unit_price": "100"}])
    owner_client.post(f"/api/invoices/{draft['id']}/issue", json={})
    voided = owner_client.post(f"/api/invoices/{draft['id']}/void", json={"reason": "Duplicate"})
    assert voided.json()["status"] == "void" and voided.json()["void_reason"] == "Duplicate"
    assert voided.json()["balance_due"] == "0.0000"


def test_credit_note_reduces_the_balance(owner_client: TestClient, acme: dict[str, Any]) -> None:
    draft = new_invoice(owner_client, acme["id"], [{"description": "Work", "unit_price": "100"}])
    owner_client.post(f"/api/invoices/{draft['id']}/issue", json={})

    note = owner_client.post(
        f"/api/invoices/{draft['id']}/credit-note",
        json={"lines": [{"description": "Goodwill discount", "unit_price": "25"}]},
    ).json()
    assert note["kind"] == "credit_note" and note["credited_invoice_id"] == draft["id"]
    issued = owner_client.post(f"/api/invoices/{note['id']}/issue", json={}).json()
    assert issued["number"] == "CN-1" and issued["payment_status"] == "credit"

    invoice = owner_client.get(f"/api/invoices/{draft['id']}").json()
    assert (invoice["amount_credited"], invoice["balance_due"]) == ("25.0000", "75.0000")
    assert invoice["payment_status"] == "partially_paid"
    assert invoice["credit_note_ids"] == [note["id"]]


def test_list_filters(owner_client: TestClient, acme: dict[str, Any]) -> None:
    old = new_invoice(owner_client, acme["id"], [{"description": "Old", "unit_price": "10"}])
    owner_client.post(f"/api/invoices/{old['id']}/issue", json={"issue_date": "2020-01-01"})
    new = new_invoice(owner_client, acme["id"], [{"description": "New", "unit_price": "10"}])
    owner_client.post(f"/api/invoices/{new['id']}/issue", json={"issue_date": str(date.today())})
    new_invoice(owner_client, acme["id"], [{"description": "Draft", "unit_price": "10"}])

    def numbers(**params: Any) -> list[str | None]:
        page = owner_client.get("/api/invoices", params=params).json()
        return [i["number"] for i in page["items"]]

    assert len(numbers()) == 3
    assert numbers(status="draft") == [None]
    assert sorted(n or "" for n in numbers(payment="open")) == ["1", "2"]
    assert numbers(payment="overdue") == ["1"]
    assert numbers(q="1", status="issued") == ["1"]


def test_calculate_saves_nothing(
    owner_client: TestClient, acme: dict[str, Any], items: dict[str, Any], db_session: Session
) -> None:
    before = db_session.scalar(select(func.count()).select_from(Invoice))
    result = owner_client.post(
        "/api/invoices/calculate",
        json={"party_id": acme["id"], "lines": [{"catalog_item_id": items["router"]["id"],
              "quantity": "2"}]},
    ).json()  # fmt: skip
    assert (result["subtotal"], result["tax_total"], result["total"]) == (
        "400.0000",
        "16.0000",
        "416.0000",
    )
    assert db_session.scalar(select(func.count()).select_from(Invoice)) == before


def test_historical_invoices_keep_their_tax(
    owner_client: TestClient, acme: dict[str, Any], db_session: Session, org: Organization
) -> None:
    invoice = Invoice(
        organization_id=org.id,
        party_id=acme["id"],
        number="1124",
        status=InvoiceStatus.ISSUED,
        is_historical=True,
        subtotal=Decimal("36.9545"),
        tax_total=Decimal("3.0487"),
        total=Decimal("40.0032"),
    )
    invoice.taxes.append(
        InvoiceTax(name="Salamanca NY", taxable_base=Decimal("36.9545"), amount=Decimal("3.0487"))
    )
    db_session.add(invoice)
    db_session.flush()

    revised = owner_client.post(
        f"/api/invoices/{invoice.id}/revise",
        json={"reason": "Fix description", "lines": [{"description": "Cable",
              "unit_price": "0.14", "quantity": "100"}]},
    ).json()  # fmt: skip
    assert revised["tax_total"] == "3.0487"  # historical tax is not recalculated
    assert revised["total"] == "17.0487"


def test_archived_invoices_are_read_only(owner_client: TestClient, acme: dict[str, Any]) -> None:
    draft = new_invoice(owner_client, acme["id"], [{"description": "Work", "unit_price": "100"}])
    owner_client.post(f"/api/invoices/{draft['id']}/issue", json={})
    assert owner_client.post(f"/api/invoices/{draft['id']}/archive").status_code == 200
    assert owner_client.get("/api/invoices").json()["total"] == 0
    revise = owner_client.post(f"/api/invoices/{draft['id']}/revise", json={"reason": "x y z"})
    assert revise.status_code == 409


def test_owner_only_revisions(
    owner_client: TestClient, acme: dict[str, Any], client: TestClient, db_session: Session,
    org: Organization,
) -> None:  # fmt: skip
    from saumgm.enums import UserRoleType
    from saumgm.services.auth import create_user
    from tests.support import PASSWORD, login

    draft = new_invoice(owner_client, acme["id"], [{"description": "Work", "unit_price": "100"}])
    owner_client.post(f"/api/invoices/{draft['id']}/issue", json={})
    owner_client.patch("/api/settings/organization", json={"invoice_revision_owner_only": True})

    create_user(db_session, org.id, "bea@example.com", "Bea", UserRoleType.BOOKKEEPER, PASSWORD)
    login(client, "bea@example.com")
    response = client.post(f"/api/invoices/{draft['id']}/revise", json={"reason": "typo fix"})
    assert response.status_code == 403
