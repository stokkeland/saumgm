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

"""Email about a record: compose from a template, send with the business's sender, log it.

A record type is what the email is about (an invoice, a payment). `compose` fills the draft the
user sees (recipients, subject, message, attachments); `send` sends what the user approved.
Every attempt is kept in `email_message`, and the record's history gets an "email" entry.
"""

import html
import re
from dataclasses import dataclass, field
from email.utils import formataddr
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm import audit
from saumgm.config import get_settings
from saumgm.documents import Formatter, invoice_pdf, receipt_pdf
from saumgm.email import Attachment, EmailError, Message, get_backend
from saumgm.enums import EmailKind, EmailStatus, InvoiceKind, InvoiceStatus
from saumgm.models import (
    EmailMessage,
    EmailTemplate,
    Invoice,
    Organization,
    Party,
    Payment,
    StoredFile,
    User,
)
from saumgm.services.invoices import balances, bill_to_snapshot
from saumgm.storage import read_file
from saumgm.timeutil import today_in

# Built-in subject and message per kind, used until the business saves its own (Admin -> Email).
DEFAULT_TEMPLATES: dict[EmailKind, tuple[str, str]] = {
    EmailKind.INVOICE: (
        "Invoice {invoice_number} from {business_name}",
        "Hello {client_name},\n\n"
        "Please find attached invoice {invoice_number} of {invoice_date} for {total}, due on "
        "{due_date}.\n\n"
        "Thank you for your business.\n\n"
        "{business_name}",
    ),
    EmailKind.CREDIT_NOTE: (
        "Credit note {invoice_number} from {business_name}",
        "Hello {client_name},\n\n"
        "Please find attached credit note {invoice_number} of {invoice_date} for {total}.\n\n"
        "{business_name}",
    ),
    EmailKind.RECEIPT: (
        "Payment received - thank you",
        "Hello {client_name},\n\n"
        "Thank you for your payment of {amount}, received on {payment_date}. The receipt is "
        "attached.\n\n"
        "{business_name}",
    ),
    EmailKind.TEST: (
        "Test message from {business_name}",
        "This is a test message from SauMGM. If you can read it, sending email works.",
    ),
}

# The placeholders each kind offers (listed in Admin -> Email).
PLACEHOLDERS: dict[EmailKind, dict[str, str]] = {
    EmailKind.INVOICE: {
        "invoice_number": "Invoice number",
        "invoice_date": "Invoice date",
        "due_date": "Due date",
        "total": "Invoice total",
        "balance_due": "What is still owed",
        "client_name": "Client (the company, or the person)",
        "contact_name": "Person the invoice is addressed to",
        "business_name": "Your business name",
    },
    EmailKind.CREDIT_NOTE: {
        "invoice_number": "Credit note number",
        "invoice_date": "Credit note date",
        "total": "Credit note total",
        "client_name": "Client (the company, or the person)",
        "contact_name": "Person the credit note is addressed to",
        "business_name": "Your business name",
    },
    EmailKind.RECEIPT: {
        "amount": "Amount received",
        "payment_date": "Date received",
        "reference": "Check number or other reference",
        "invoices": "Invoices the payment was applied to",
        "client_name": "Client name",
        "business_name": "Your business name",
    },
    EmailKind.TEST: {"business_name": "Your business name"},
}

PLACEHOLDER = re.compile(r"\{(\w+)\}")
ADDRESS = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


@dataclass
class Draft:
    kind: EmailKind
    entity_type: str | None
    entity_id: str | None
    to: list[str]
    cc: list[str]
    subject: str
    body: str
    attachments: list[Attachment] = field(default_factory=list)


def fill(text: str, values: dict[str, str]) -> str:
    """Replace the known {placeholders}; anything else in braces stays as written."""
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def template(session: Session, org_id: int, kind: EmailKind) -> tuple[str, str, bool]:
    """Subject, message, and whether the business has changed them from the built-in text."""
    saved = session.scalars(
        select(EmailTemplate).where(
            EmailTemplate.organization_id == org_id, EmailTemplate.kind == kind
        )
    ).one_or_none()
    if saved is not None:
        return saved.subject, saved.body, True
    subject, body = DEFAULT_TEMPLATES[kind]
    return subject, body, False


def sender(org: Organization) -> str | None:
    address = org.email_from_address or get_settings().email_from
    if not address:
        return None
    return formataddr((org.email_from_name or org.display_name, address))


def text_to_html(text: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    body = "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)
    return (
        '<div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; '
        f'line-height: 1.5; color: #222">{body}</div>'
    )


# -- drafts per record type -----------------------------------------------------------------------


def _invoice_draft(session: Session, org: Organization, invoice: Invoice) -> Draft:
    if invoice.status != InvoiceStatus.ISSUED:
        raise EmailError("Only issued invoices can be sent by email (issue the draft first)")
    credit = invoice.kind == InvoiceKind.CREDIT_NOTE
    party = session.get(Party, invoice.party_id)
    f = Formatter(org)
    info = balances(session, [invoice], today_in(org.timezone))[invoice.id]
    values = {
        "invoice_number": invoice.number or "",
        "invoice_date": f.date(invoice.issue_date),
        "due_date": f.date(invoice.due_date),
        "total": f.money(invoice.total),
        "balance_due": f.money(info.balance_due),
        "client_name": invoice.bill_to_company
        or invoice.bill_to_name
        or (party.name if party else ""),
        "contact_name": invoice.bill_to_name or "",
        "business_name": org.display_name,
    }
    stored = session.get(StoredFile, invoice.pdf_file_id) if invoice.pdf_file_id else None
    if stored is not None:  # the document exactly as issued
        pdf = Attachment(stored.original_name, read_file(stored), "application/pdf")
    else:  # imported invoices have no stored document; render it as the download does
        name = f"{'credit-note' if credit else 'invoice'}-{invoice.number}.pdf"
        pdf = Attachment(name, invoice_pdf(session, org, invoice), "application/pdf")
    kind = EmailKind.CREDIT_NOTE if credit else EmailKind.INVOICE
    to = invoice.bill_to_email or (party.email if party else None)
    return _draft(session, org, kind, ("invoice", invoice.id), to, values, [pdf])


def _payment_draft(session: Session, org: Organization, payment: Payment) -> Draft:
    party = session.get(Party, payment.party_id)
    assert party is not None
    f = Formatter(org)
    invoice_ids = [a.invoice_id for a in payment.allocations]
    numbers = session.scalars(select(Invoice.number).where(Invoice.id.in_(invoice_ids))).all()
    values = {
        "amount": f.money(payment.amount),
        "payment_date": f.date(payment.received_date),
        "reference": payment.reference or "",
        "invoices": ", ".join(sorted(n for n in numbers if n)),
        "client_name": party.name,
        "business_name": org.display_name,
    }
    pdf = Attachment(
        f"receipt-{payment.id}.pdf", receipt_pdf(session, org, payment), "application/pdf"
    )
    to = bill_to_snapshot(party)["bill_to_email"]
    return _draft(session, org, EmailKind.RECEIPT, ("payment", payment.id), to, values, [pdf])


def _draft(
    session: Session,
    org: Organization,
    kind: EmailKind,
    record: tuple[str, int],
    to: str | None,
    values: dict[str, str],
    attachments: list[Attachment],
) -> Draft:
    subject, body, _ = template(session, org.id, kind)
    return Draft(
        kind=kind,
        entity_type=record[0],
        entity_id=str(record[1]),
        to=[to] if to else [],
        cc=[],
        subject=fill(subject, values),
        body=fill(body, values),
        attachments=attachments,
    )


def compose(session: Session, org: Organization, record_type: str, record_id: int) -> Draft:
    """The email as it would go out for this record. LookupError if there is no such record."""
    if record_type == "invoice":
        invoice = session.get(Invoice, record_id)
        if invoice is None or invoice.organization_id != org.id:
            raise LookupError("Invoice")
        return _invoice_draft(session, org, invoice)
    if record_type == "payment":
        payment = session.get(Payment, record_id)
        if payment is None or payment.organization_id != org.id:
            raise LookupError("Payment")
        return _payment_draft(session, org, payment)
    raise LookupError(f"Email for {record_type!r}")


def test_draft(session: Session, org: Organization, user: User) -> Draft:
    subject, body, _ = template(session, org.id, EmailKind.TEST)
    values = {"business_name": org.display_name}
    return Draft(
        kind=EmailKind.TEST,
        entity_type=None,
        entity_id=None,
        to=[user.email],
        cc=[],
        subject=fill(subject, values),
        body=fill(body, values),
    )


# -- sending --------------------------------------------------------------------------------------


def _addresses(values: list[str], what: str) -> list[str]:
    cleaned = [v.strip() for v in values if v.strip()]
    bad = [v for v in cleaned if not ADDRESS.match(v)]
    if bad:
        raise EmailError(f"Not an email address ({what}): {', '.join(bad)}")
    return cleaned


def send(session: Session, org: Organization, draft: Draft, user_id: int | None) -> EmailMessage:
    """Send the draft and log it.

    Mistakes found before sending (no recipient, no sender) raise EmailError and nothing is
    logged. A refusal by the provider is logged as failed and returned, so the caller can keep
    the log and still report the error.
    """
    to = _addresses(draft.to, "to")
    cc = _addresses(draft.cc, "cc")
    if not to:
        raise EmailError("Add at least one recipient")
    if not draft.subject.strip():
        raise EmailError("The subject is empty")
    from_address = sender(org)
    if from_address is None:
        raise EmailError("Set the sender address first (Admin -> Email)")

    text = draft.body
    redirect = get_settings().email_redirect_to
    deliver_to, deliver_cc = to, cc
    if redirect:
        # Development and test installations: the real recipients never get anything.
        meant_for = ", ".join(to) + (f"; cc: {', '.join(cc)}" if cc else "")
        text = f"[Sent to {redirect} by EMAIL_REDIRECT_TO. Meant for: {meant_for}]\n\n{text}"
        deliver_to, deliver_cc = [redirect], []

    backend = get_backend()
    message = Message(
        sender=from_address,
        to=deliver_to,
        cc=deliver_cc,
        reply_to=org.email_reply_to,
        subject=draft.subject.strip(),
        text=text,
        html=text_to_html(text),
        attachments=draft.attachments,
    )
    log = EmailMessage(
        organization_id=org.id,
        sent_by_user_id=user_id,
        kind=draft.kind,
        entity_type=draft.entity_type,
        entity_id=draft.entity_id,
        from_address=from_address,
        to_addresses=", ".join(to),
        cc_addresses=", ".join(cc) or None,
        redirected_to=redirect or None,
        subject=message.subject,
        body_text=draft.body,
        attachments=[{"filename": a.filename, "size": len(a.content)} for a in draft.attachments]
        or None,
        provider=backend.name,
    )
    try:
        log.provider_message_id = backend.send(message)
        log.status = EmailStatus.SENT
    except EmailError as exc:
        log.status = EmailStatus.FAILED
        log.error = str(exc)
    session.add(log)
    session.flush()
    if draft.entity_type and draft.entity_id:
        changes: dict[str, Any] = {"to": log.to_addresses}
        if log.cc_addresses:
            changes["cc"] = log.cc_addresses
        changes |= {"subject": log.subject, "status": log.status.value}
        audit.record(
            session,
            "email",
            entity_type=draft.entity_type,
            entity_id=draft.entity_id,
            changes=changes,
        )
    return log
