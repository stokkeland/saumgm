from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from saumgm.models import Organization, Payment
from tests.api_helpers import contact, issued_invoice, ok


def pay(client: TestClient, party_id: int, amount: str, **extra: Any) -> dict[str, Any]:
    return ok(
        client.post(
            "/api/payments",
            json={"party_id": party_id, "received_date": "2026-02-01", "amount": amount,
                  "method": "check", "reference": "1001"} | extra,
        ),
        201,
    )  # fmt: skip


def invoice(client: TestClient, invoice_id: int) -> dict[str, Any]:
    return ok(client.get(f"/api/invoices/{invoice_id}"))


def test_payment_is_applied_oldest_first(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    older = issued_invoice(owner_client, acme["id"], "100", "2026-01-01")
    newer = issued_invoice(owner_client, acme["id"], "50", "2026-01-15")

    payment = pay(owner_client, acme["id"], "120")
    assert [(a["invoice_id"], a["amount"]) for a in payment["allocations"]] == [
        (older["id"], "100.0000"),
        (newer["id"], "20.0000"),
    ]
    assert payment["unapplied"] == "0.0000"
    assert invoice(owner_client, older["id"])["payment_status"] == "paid"
    newer_now = invoice(owner_client, newer["id"])
    assert (newer_now["payment_status"], newer_now["balance_due"]) == ("partially_paid", "30.0000")
    assert newer_now["payments"][0]["reference"] == "1001"


def test_explicit_allocations_are_validated(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    other = contact(owner_client, "OTHER")
    mine = issued_invoice(owner_client, acme["id"], "100")
    theirs = issued_invoice(owner_client, other["id"], "100")

    def attempt(amount: str, allocations: list[dict[str, Any]]) -> int:
        response = owner_client.post(
            "/api/payments",
            json={"party_id": acme["id"], "received_date": "2026-02-01", "amount": amount,
                  "allocations": allocations},
        )  # fmt: skip
        code: int = response.status_code
        return code

    assert attempt("150", [{"invoice_id": mine["id"], "amount": "150"}]) == 409  # > balance
    assert attempt("50", [{"invoice_id": mine["id"], "amount": "60"}]) == 409  # > payment
    assert attempt("50", [{"invoice_id": theirs["id"], "amount": "50"}]) == 409  # other contact
    assert attempt("40", [{"invoice_id": mine["id"], "amount": "40"}]) == 201


def test_overpayment_becomes_client_credit(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    issued_invoice(owner_client, acme["id"], "150", "2020-01-01")
    issued_invoice(owner_client, acme["id"], "80", "2020-02-01")
    payment = pay(owner_client, acme["id"], "200", allocations=[])
    assert payment["unapplied"] == "200.0000"

    balance = ok(owner_client.get(f"/api/contacts/{acme['id']}/balance"))
    assert balance == {
        "receivable": "230.0000",
        "overdue": "230.0000",
        "open_invoices": 2,
        "unapplied_credit": "200.0000",
        "net": "30.0000",
    }

    reapplied = ok(owner_client.patch(f"/api/payments/{payment['id']}", json={"reallocate": True}))
    assert reapplied["unapplied"] == "0.0000"
    assert ok(owner_client.get(f"/api/contacts/{acme['id']}/balance"))["net"] == "30.0000"


def test_deposits(owner_client: TestClient) -> None:
    acme = contact(owner_client, "ACME")
    issued_invoice(owner_client, acme["id"], "300")
    first = pay(owner_client, acme["id"], "100")
    second = pay(owner_client, acme["id"], "150", reference="1002")

    waiting = ok(owner_client.get("/api/payments", params={"undeposited": True}))
    assert {p["id"] for p in waiting["items"]} == {first["id"], second["id"]}

    deposit = ok(
        owner_client.post(
            "/api/deposits",
            json={"deposit_date": "2026-02-02", "payment_ids": [first["id"], second["id"]],
                  "items": [{"amount": "20", "description": "Cash sale"}]},
        ),
        201,
    )  # fmt: skip
    assert deposit["total"] == "270.0000"
    assert ok(owner_client.get("/api/payments", params={"undeposited": True}))["total"] == 0

    # deposited payments are locked
    locked = owner_client.patch(f"/api/payments/{first['id']}", json={"amount": "90"})
    assert locked.status_code == 409

    smaller = ok(
        owner_client.patch(f"/api/deposits/{deposit['id']}", json={"payment_ids": [first["id"]]})
    )
    assert smaller["total"] == "120.0000"
    assert owner_client.delete(f"/api/deposits/{deposit['id']}").status_code == 204
    assert ok(owner_client.get("/api/payments", params={"undeposited": True}))["total"] == 2


def test_imported_payments_are_protected(
    owner_client: TestClient, db_session: Session, org: Organization
) -> None:
    acme = contact(owner_client, "ACME")
    old = Payment(
        organization_id=org.id, party_id=acme["id"], amount=Decimal(5), is_historical=True
    )
    db_session.add(old)
    db_session.flush()

    assert owner_client.delete(f"/api/payments/{old.id}").status_code == 409
    deposit = owner_client.post(
        "/api/deposits", json={"deposit_date": "2026-02-02", "payment_ids": [old.id]}
    )
    assert deposit.status_code == 409
    assert ok(owner_client.get("/api/payments", params={"undeposited": True}))["total"] == 0
