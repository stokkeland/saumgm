"""Invoice lifecycle: drafts, issuing, voiding, revisions, credit notes and balances
(docs/design.md 4.4)."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from saumgm import audit
from saumgm.documents import invoice_pdf
from saumgm.enums import AddressType, InvoiceKind, InvoiceStatus, PartyKind, PaymentStatus
from saumgm.models import (
    CatalogItem,
    Invoice,
    InvoiceLine,
    InvoiceRevision,
    InvoiceTax,
    Organization,
    Party,
    PartyAddress,
    PaymentAllocation,
    RevenueCategory,
    Subscription,
    TaxCategory,
    TaxFiling,
    TaxJurisdiction,
)
from saumgm.schemas.invoices import LineIn
from saumgm.services.money import ZERO, discount_amount, line_total, round_money
from saumgm.services.numbering import next_number
from saumgm.services.tax_engine import TaxableLine, TaxEngine, default_engine
from saumgm.storage import store_file
from saumgm.timeutil import today_in, utcnow

# Up to half a cent either way counts as settled (old totals had fractions of a cent, payments
# were rounded to cents).
PAID_TOLERANCE = Decimal("0.005")

BILL_TO_FIELDS = (
    "bill_to_company", "bill_to_name", "bill_to_line1", "bill_to_line2", "bill_to_city",
    "bill_to_region", "bill_to_postal_code", "bill_to_country", "bill_to_phone", "bill_to_email",
)  # fmt: skip
HEADER_FIELDS = (
    "issue_date", "terms_days", "terms_text", "tax_jurisdiction_id", "freight", "adjustment",
    "adjustment_note", "notes", *BILL_TO_FIELDS,
)  # fmt: skip


class InvoiceError(Exception):
    """A request that is not allowed in the invoice's current state."""


@dataclass(frozen=True)
class BalanceInfo:
    paid: Decimal
    credited: Decimal
    balance_due: Decimal
    status: PaymentStatus
    overdue: bool


# -- references -----------------------------------------------------------------------------------


def _owned(session: Session, model: Any, record_id: int | None, org_id: int, what: str) -> Any:
    if record_id is None:
        return None
    obj = session.get(model, record_id)
    if obj is None or obj.organization_id != org_id:
        raise InvoiceError(f"{what} {record_id} not found")
    return obj


def _check_header_refs(session: Session, org_id: int, header: dict[str, Any]) -> None:
    _owned(session, TaxJurisdiction, header.get("tax_jurisdiction_id"), org_id, "Jurisdiction")


# -- defaults from the contact --------------------------------------------------------------------


def _addresses_by_preference(party: Party, *types: AddressType) -> list[PartyAddress]:
    ordered: list[PartyAddress] = []
    for kind in types:
        ordered += [a for a in party.addresses if a.address_type == kind and a.is_default]
        ordered += [a for a in party.addresses if a.address_type == kind and not a.is_default]
    ordered += [a for a in party.addresses if a not in ordered]
    return ordered


def bill_to_snapshot(party: Party) -> dict[str, Any]:
    """The bill-to block copied onto an invoice, so later changes to the contact don't alter it."""
    addresses = _addresses_by_preference(party, AddressType.BILLING)
    address = addresses[0] if addresses else None
    primary = next((c for c in party.contacts if c.is_primary), None) or (
        party.contacts[0] if party.contacts else None
    )
    is_company = party.kind == PartyKind.COMPANY
    return {
        "bill_to_company": party.name if is_company else None,
        "bill_to_name": (primary.name if primary else None) if is_company else party.name,
        "bill_to_line1": address.line1 if address else None,
        "bill_to_line2": address.line2 if address else None,
        "bill_to_city": address.city if address else None,
        "bill_to_region": address.region if address else None,
        "bill_to_postal_code": address.postal_code if address else None,
        "bill_to_country": address.country_code if address else None,
        "bill_to_phone": party.phone or (primary.phone if primary else None),
        "bill_to_email": (primary.email if primary and primary.email else None) or party.email,
    }


def default_tax_jurisdiction(session: Session, org_id: int, party: Party) -> int | None:
    """Where the client is served: the service address first, then the billing address."""
    for address in _addresses_by_preference(party, AddressType.SERVICE, AddressType.BILLING):
        if address.tax_jurisdiction_id:
            return address.tax_jurisdiction_id
        if address.country_code and address.region:
            code = f"{address.country_code.upper()}-{address.region.strip().upper()}"
            found = session.scalars(
                select(TaxJurisdiction.id).where(
                    TaxJurisdiction.organization_id == org_id, TaxJurisdiction.code == code
                )
            ).first()
            if found:
                return found
    return None


# -- lines ----------------------------------------------------------------------------------------


def build_line(session: Session, org_id: int, data: LineIn, order: int) -> InvoiceLine:
    item: CatalogItem | None = _owned(
        session, CatalogItem, data.catalog_item_id, org_id, "Catalog item"
    )
    _owned(session, Subscription, data.subscription_id, org_id, "Subscription")
    _owned(session, TaxCategory, data.tax_category_id, org_id, "Tax category")
    _owned(session, RevenueCategory, data.revenue_category_id, org_id, "Revenue category")

    description = data.description or (item.name if item else None)
    if not description:
        raise InvoiceError(f"Line {order + 1}: a description or catalog item is required")
    unit_price = data.unit_price if data.unit_price is not None else (item.price if item else None)
    if unit_price is None:
        raise InvoiceError(f"Line {order + 1}: a unit price or catalog item is required")
    if data.discount_pct is not None:
        unit_discount = discount_amount(unit_price, data.discount_pct)
    elif data.unit_discount is not None:
        unit_discount = data.unit_discount
    elif item is not None:
        unit_discount = discount_amount(unit_price, item.default_discount_pct)
    else:
        unit_discount = ZERO
    return InvoiceLine(
        sort_order=order,
        catalog_item_id=item.id if item else None,
        subscription_id=data.subscription_id,
        description=description,
        quantity=data.quantity,
        unit=data.unit if "unit" in data.model_fields_set else (item.unit if item else None),
        unit_price=unit_price,
        unit_discount=unit_discount,
        line_total=ZERO,
        tax_category_id=data.tax_category_id or (item.tax_category_id if item else None),
        revenue_category_id=data.revenue_category_id
        or (item.revenue_category_id if item else None),
    )


def _replace_lines(
    session: Session, org_id: int, invoice: Invoice, lines: Sequence[LineIn]
) -> None:
    invoice.lines = [build_line(session, org_id, data, i) for i, data in enumerate(lines)]


# -- totals ---------------------------------------------------------------------------------------


def recalculate(
    session: Session, org: Organization, invoice: Invoice, engine: TaxEngine = default_engine
) -> None:
    """Line totals, tax and totals. Historical (imported) invoices keep their stored tax and the
    old system's 4-decimal precision."""
    currency = org.currency_code
    if invoice.is_historical:
        for line in invoice.lines:
            line.line_total = ((line.unit_price - line.unit_discount) * line.quantity).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        invoice.subtotal = sum((ln.line_total for ln in invoice.lines), ZERO)
        invoice.total = invoice.subtotal + invoice.freight + invoice.adjustment + invoice.tax_total
        return

    for line in invoice.lines:
        line.line_total = line_total(line.unit_price, line.unit_discount, line.quantity, currency)
    invoice.subtotal = round_money(sum((ln.line_total for ln in invoice.lines), ZERO), currency)
    taxes = engine.calculate(
        session,
        organization_id=org.id,
        currency=currency,
        jurisdiction_id=invoice.tax_jurisdiction_id,
        on_date=invoice.issue_date or today_in(org.timezone),
        party_id=invoice.party_id,
        lines=[TaxableLine(ln.line_total, ln.tax_category_id) for ln in invoice.lines],
    )
    invoice.taxes = [
        InvoiceTax(
            jurisdiction_id=t.jurisdiction_id,
            name=t.name,
            rate=t.rate,
            taxable_base=t.taxable_base,
            amount=t.amount,
        )
        for t in taxes
    ]
    invoice.tax_total = round_money(sum((t.amount for t in taxes), ZERO), currency)
    invoice.total = round_money(
        invoice.subtotal + (invoice.freight or ZERO) + (invoice.adjustment or ZERO)
        + invoice.tax_total,
        currency,
    )  # fmt: skip


# -- lifecycle ------------------------------------------------------------------------------------


def _apply_header(invoice: Invoice, header: dict[str, Any]) -> None:
    for key in HEADER_FIELDS:
        if key in header:
            value = header[key]
            if key in ("freight", "adjustment") and value is None:
                value = ZERO
            setattr(invoice, key, value)


def _default_terms(org: Organization, party: Party) -> tuple[int, str]:
    days = (
        party.default_terms_days if party.default_terms_days is not None else org.default_terms_days
    )
    return days, ("Due on receipt" if days == 0 else f"Net {days} days")


def create_invoice(
    session: Session,
    org: Organization,
    party: Party,
    header: dict[str, Any],
    lines: Sequence[LineIn],
    *,
    kind: InvoiceKind = InvoiceKind.INVOICE,
    credited_invoice: Invoice | None = None,
) -> Invoice:
    if party.organization_id != org.id:
        raise InvoiceError("Contact not found")
    if party.archived_at is not None:
        raise InvoiceError("The contact is archived")
    _check_header_refs(session, org.id, header)
    days, text = _default_terms(org, party)
    invoice = Invoice(
        organization_id=org.id,
        kind=kind,
        party_id=party.id,
        status=InvoiceStatus.DRAFT,
        credited_invoice_id=credited_invoice.id if credited_invoice else None,
        terms_days=days,
        terms_text=text,
        freight=ZERO,
        adjustment=ZERO,
        tax_jurisdiction_id=default_tax_jurisdiction(session, org.id, party),
        **bill_to_snapshot(party),
    )
    if "terms_days" in header and "terms_text" not in header:
        header = {**header, "terms_text": None}
    _apply_header(invoice, header)
    _replace_lines(session, org.id, invoice, lines)
    session.add(invoice)
    recalculate(session, org, invoice)
    session.flush()
    return invoice


def update_draft(
    session: Session,
    org: Organization,
    invoice: Invoice,
    header: dict[str, Any],
    lines: Sequence[LineIn] | None,
    party: Party | None = None,
) -> None:
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvoiceError("Only drafts can be edited; use revise for issued invoices")
    _check_header_refs(session, org.id, header)
    if party is not None and party.id != invoice.party_id:
        invoice.party_id = party.id
        for key, value in bill_to_snapshot(party).items():
            if key not in header:
                setattr(invoice, key, value)
        if "tax_jurisdiction_id" not in header:
            invoice.tax_jurisdiction_id = default_tax_jurisdiction(session, org.id, party)
    _apply_header(invoice, header)
    if lines is not None:
        _replace_lines(session, org.id, invoice, lines)
    recalculate(session, org, invoice)
    session.flush()


def delete_draft(session: Session, invoice: Invoice) -> None:
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvoiceError("Only drafts can be deleted; void issued invoices instead")
    session.delete(invoice)
    session.flush()


def issue(session: Session, org: Organization, invoice: Invoice, issue_date: date | None) -> None:
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvoiceError("Only drafts can be issued")
    if not invoice.lines:
        raise InvoiceError("An invoice needs at least one line")
    invoice.issue_date = issue_date or invoice.issue_date or today_in(org.timezone)
    invoice.due_date = invoice.issue_date + timedelta(days=invoice.terms_days or 0)
    sequence = "credit_note" if invoice.kind == InvoiceKind.CREDIT_NOTE else "invoice"
    invoice.number = next_number(session, org.id, sequence)
    invoice.status = InvoiceStatus.ISSUED
    invoice.issued_at = utcnow()
    recalculate(session, org, invoice)
    session.flush()
    store_pdf(session, org, invoice)
    audit.record(
        session,
        "issue",
        entity_type="invoice",
        entity_id=str(invoice.id),
        changes={"number": invoice.number, "total": str(invoice.total)},
    )


def void(session: Session, invoice: Invoice, reason: str) -> None:
    if invoice.status != InvoiceStatus.ISSUED:
        raise InvoiceError("Only issued invoices can be voided (delete drafts instead)")
    if invoice.write_off_date is not None:
        raise InvoiceError("Undo the write-off before voiding this invoice")
    paid = session.scalar(
        select(func.count())
        .select_from(PaymentAllocation)
        .where(PaymentAllocation.invoice_id == invoice.id)
    )
    if paid:
        raise InvoiceError("Remove the payments applied to this invoice before voiding it")
    invoice.status = InvoiceStatus.VOID
    invoice.voided_at = utcnow()
    invoice.void_reason = reason
    session.flush()
    audit.record(session, "void", entity_type="invoice", entity_id=str(invoice.id), reason=reason)


def snapshot(invoice: Invoice) -> dict[str, Any]:
    """The complete invoice as plain JSON (stored with each revision)."""

    def columns(obj: Any) -> dict[str, Any]:
        return {
            attr.key: audit.jsonable(getattr(obj, attr.key))
            for attr in inspect(obj).mapper.column_attrs
        }

    data = columns(invoice)
    data["lines"] = [columns(line) for line in invoice.lines]
    data["taxes"] = [columns(tax) for tax in invoice.taxes]
    return data


def revise(
    session: Session,
    org: Organization,
    invoice: Invoice,
    header: dict[str, Any],
    lines: Sequence[LineIn] | None,
    *,
    reason: str,
    user_id: int | None,
) -> list[str]:
    """Correct an issued invoice. The previous version is kept as a revision. Returns warnings."""
    if invoice.status != InvoiceStatus.ISSUED:
        raise InvoiceError("Only issued invoices can be revised (edit drafts directly)")
    if invoice.write_off_date is not None:
        raise InvoiceError("Undo the write-off before revising this invoice")
    _check_header_refs(session, org.id, header)
    session.add(
        InvoiceRevision(
            invoice_id=invoice.id,
            revision_no=invoice.revision_no,
            snapshot=snapshot(invoice),
            reason=reason,
            changed_by_user_id=user_id,
            changed_at=utcnow(),
            # The document the client had before this change.
            pdf_file_id=invoice.pdf_file_id,
        )
    )
    invoice.revision_no += 1
    _apply_header(invoice, header)
    if "issue_date" in header and invoice.issue_date:
        invoice.due_date = invoice.issue_date + timedelta(days=invoice.terms_days or 0)
    if lines is not None:
        _replace_lines(session, org.id, invoice, lines)
    recalculate(session, org, invoice)
    session.flush()
    session.refresh(invoice, ["lines", "taxes"])
    store_pdf(session, org, invoice)
    audit.record(
        session,
        "revise",
        entity_type="invoice",
        entity_id=str(invoice.id),
        reason=reason,
        changes={"revision_no": invoice.revision_no, "total": str(invoice.total)},
    )

    warnings = []
    if invoice.issue_date is not None:
        filed = session.scalars(
            select(TaxFiling).where(
                TaxFiling.organization_id == org.id,
                TaxFiling.period_start <= invoice.issue_date,
                TaxFiling.period_end >= invoice.issue_date,
            )
        ).first()
        if filed is not None:
            warnings.append(
                f"The invoice date falls in a sales-tax period already filed "
                f"({filed.period_start.isoformat()} to {filed.period_end.isoformat()}); the "
                "return may need an amendment."
            )
    info = balances(session, [invoice], today_in(org.timezone))[invoice.id]
    if info.balance_due < -PAID_TOLERANCE:
        warnings.append(
            f"Payments exceed the new total by {-info.balance_due}: leave it as client credit "
            "or refund it."
        )
    return warnings


def create_credit_note(
    session: Session,
    org: Organization,
    invoice: Invoice,
    lines: Sequence[LineIn],
    notes: str | None,
) -> Invoice:
    if invoice.kind != InvoiceKind.INVOICE or invoice.status != InvoiceStatus.ISSUED:
        raise InvoiceError("Credit notes can only be made for issued invoices")
    party = session.get(Party, invoice.party_id)
    assert party is not None
    header: dict[str, Any] = {
        "notes": notes or f"Credit for invoice {invoice.number}",
        "terms_days": 0,
        "terms_text": None,
        "tax_jurisdiction_id": invoice.tax_jurisdiction_id,
        **{key: getattr(invoice, key) for key in BILL_TO_FIELDS},
    }
    return create_invoice(
        session,
        org,
        party,
        header,
        lines,
        kind=InvoiceKind.CREDIT_NOTE,
        credited_invoice=invoice,
    )


def store_pdf(session: Session, org: Organization, invoice: Invoice) -> None:
    """Render the invoice as issued and keep that exact document."""
    kind = "credit-note" if invoice.kind == InvoiceKind.CREDIT_NOTE else "invoice"
    name = f"{kind}-{invoice.number}"
    if invoice.revision_no:
        name += f"-rev{invoice.revision_no}"
    stored = store_file(
        session, org.id, invoice_pdf(session, org, invoice), f"{name}.pdf", "application/pdf"
    )
    invoice.pdf_file_id = stored.id
    session.flush()


# -- bad debt -------------------------------------------------------------------------------------


def write_off(
    session: Session, org: Organization, invoice: Invoice, reason: str, on: date | None
) -> Decimal:
    """Give up on what is still owed. The sale stays in the books; the balance becomes zero.
    Returns the amount written off."""
    if invoice.kind != InvoiceKind.INVOICE or invoice.status != InvoiceStatus.ISSUED:
        raise InvoiceError("Only issued invoices can be written off")
    if invoice.write_off_date is not None:
        raise InvoiceError(f"Invoice {invoice.number} is already written off")
    info = balances(session, [invoice], today_in(org.timezone))[invoice.id]
    if info.balance_due <= PAID_TOLERANCE:
        raise InvoiceError(f"Invoice {invoice.number} has nothing left to write off")
    invoice.write_off_amount = info.balance_due
    invoice.write_off_date = on or today_in(org.timezone)
    invoice.write_off_reason = reason
    session.flush()
    audit.record(
        session,
        "write_off",
        entity_type="invoice",
        entity_id=str(invoice.id),
        reason=reason,
        changes={"amount": str(info.balance_due), "date": invoice.write_off_date.isoformat()},
    )
    return info.balance_due


def undo_write_off(session: Session, invoice: Invoice, reason: str) -> None:
    """The client paid after all (or it was a mistake): the balance is owed again."""
    if invoice.write_off_date is None:
        raise InvoiceError(f"Invoice {invoice.number} is not written off")
    amount = invoice.write_off_amount
    invoice.write_off_amount = None
    invoice.write_off_date = None
    invoice.write_off_reason = None
    session.flush()
    audit.record(
        session,
        "write_off_undone",
        entity_type="invoice",
        entity_id=str(invoice.id),
        reason=reason,
        changes={"amount": str(amount)},
    )


def written_off_tax(invoice: Invoice) -> Decimal:
    """The sales-tax part of a written-off amount (for bad-debt tax credits)."""
    if not invoice.write_off_amount or not invoice.total:
        return ZERO
    share = invoice.write_off_amount * invoice.tax_total / invoice.total
    return share.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# -- balances -------------------------------------------------------------------------------------


def balance_info(invoice: Invoice, paid: Decimal, credited: Decimal, today: date) -> BalanceInfo:
    written_off = invoice.write_off_amount or ZERO
    balance = invoice.total - paid - credited - written_off
    if invoice.status == InvoiceStatus.DRAFT:
        status = PaymentStatus.DRAFT
    elif invoice.status == InvoiceStatus.VOID:
        status = PaymentStatus.VOID
    elif invoice.kind == InvoiceKind.CREDIT_NOTE:
        status = PaymentStatus.CREDIT
    elif written_off and abs(balance) <= PAID_TOLERANCE:
        status = PaymentStatus.WRITTEN_OFF
    elif balance < -PAID_TOLERANCE:
        status = PaymentStatus.OVERPAID
    elif balance <= PAID_TOLERANCE:
        status = PaymentStatus.PAID
    elif paid or credited:
        status = PaymentStatus.PARTIALLY_PAID
    else:
        status = PaymentStatus.UNPAID
    overdue = (
        status in (PaymentStatus.UNPAID, PaymentStatus.PARTIALLY_PAID)
        and invoice.due_date is not None
        and invoice.due_date < today
    )
    # Settled within the tolerance (e.g. 8088.625 paid as 8088.63) reads as nothing due.
    if status in (
        PaymentStatus.DRAFT,
        PaymentStatus.VOID,
        PaymentStatus.CREDIT,
        PaymentStatus.PAID,
        PaymentStatus.WRITTEN_OFF,
    ):
        balance = ZERO
    return BalanceInfo(paid, credited, balance, status, overdue)


def amounts(
    session: Session, invoice_ids: Iterable[int]
) -> tuple[dict[int, Decimal], dict[int, Decimal]]:
    """Paid and credited amounts per invoice (issued credit notes count as credit)."""
    ids = list(invoice_ids)
    if not ids:
        return {}, {}
    paid: dict[int, Decimal] = {
        invoice_id: amount
        for invoice_id, amount in session.execute(
            select(PaymentAllocation.invoice_id, func.sum(PaymentAllocation.amount))
            .where(PaymentAllocation.invoice_id.in_(ids))
            .group_by(PaymentAllocation.invoice_id)
        )
    }
    credited: dict[int, Decimal] = {
        invoice_id: amount
        for invoice_id, amount in session.execute(
            select(Invoice.credited_invoice_id, func.sum(Invoice.total))
            .where(
                Invoice.credited_invoice_id.in_(ids),
                Invoice.status == InvoiceStatus.ISSUED,
            )
            .group_by(Invoice.credited_invoice_id)
        )
        if invoice_id is not None
    }
    return paid, credited


def balances(session: Session, invoices: Sequence[Invoice], today: date) -> dict[int, BalanceInfo]:
    paid, credited = amounts(session, (i.id for i in invoices))
    return {
        i.id: balance_info(i, paid.get(i.id, ZERO), credited.get(i.id, ZERO), today)
        for i in invoices
    }
