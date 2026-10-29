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

"""PDF documents: invoices and credit notes, payment receipts, deposit slips, reports.

Everything business-specific comes from the organization's settings (logo, name, addresses valid on
the document date, "payable to", footer, locale and currency), so the layout works for anyone.
"""

import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape

from babel.dates import format_date, format_datetime
from babel.numbers import format_currency, format_decimal, format_percent
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from saumgm.enums import AddressType, InvoiceKind, InvoiceStatus
from saumgm.models import (
    Deposit,
    Invoice,
    Organization,
    OrganizationAddress,
    Party,
    PartyAddress,
    Payment,
    StoredFile,
)
from saumgm.storage import read_file

ACCENT = colors.HexColor("#1c4e80")
LIGHT = colors.HexColor("#eef2f7")
MUTED = colors.HexColor("#666666")

_styles = getSampleStyleSheet()
BODY = ParagraphStyle(
    "body", parent=_styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=12
)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10, textColor=MUTED)
BOLD = ParagraphStyle("bold", parent=BODY, fontName="Helvetica-Bold")
RIGHT = ParagraphStyle("right", parent=BODY, alignment=TA_RIGHT)
TITLE = ParagraphStyle(
    "title",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=20,
    leading=24,
    alignment=TA_RIGHT,
    textColor=ACCENT,
)
NAME = ParagraphStyle("name", parent=BODY, fontName="Helvetica-Bold", fontSize=15, leading=18)


class Formatter:
    def __init__(self, org: Organization) -> None:
        self.currency = org.currency_code
        self.locale = org.locale.replace("-", "_")

    def money(self, value: Decimal | None) -> str:
        return "" if value is None else format_currency(value, self.currency, locale=self.locale)

    def number(self, value: Decimal) -> str:
        return format_decimal(value.normalize(), locale=self.locale)

    def rate(self, value: Decimal | None) -> str:
        return "" if value is None else format_percent(value, "#,##0.###%", locale=self.locale)

    def date(self, value: date | None) -> str:
        return "" if value is None else format_date(value, "medium", locale=self.locale)

    def timestamp(self, value: datetime) -> str:
        # Babel puts a narrow no-break space before AM/PM, which the PDF fonts do not have.
        return format_datetime(value, "short", locale=self.locale).replace("\u202f", " ")


def text(value: Any, style: ParagraphStyle = BODY) -> Paragraph:
    """A paragraph from plain text (escaped; newlines kept)."""
    return Paragraph(escape(str(value or "")).replace("\n", "<br/>"), style)


def lines_of(*parts: str | None) -> str:
    return "\n".join(p for p in parts if p)


# -- shared lookups -------------------------------------------------------------------------------


def org_address(
    session: Session, org: Organization, on: date | None, *types: AddressType
) -> OrganizationAddress | None:
    """The business address of a type that was valid on a day (the current one if no date)."""
    day = on or date.today()
    candidates = session.scalars(
        select(OrganizationAddress).where(
            OrganizationAddress.organization_id == org.id,
            OrganizationAddress.address_type.in_(types),
            or_(
                OrganizationAddress.effective_from.is_(None),
                OrganizationAddress.effective_from <= day,
            ),
            or_(
                OrganizationAddress.effective_to.is_(None), OrganizationAddress.effective_to >= day
            ),
        )
    ).all()
    for kind in types:  # in order of preference
        for address in candidates:
            if address.address_type == kind:
                return address
    return None


def format_address(a: OrganizationAddress | PartyAddress | None) -> str:
    if a is None:
        return ""
    city = " ".join(p for p in (a.city and f"{a.city},", a.region, a.postal_code) if p)
    return lines_of(a.line1, a.line2, city)


def logo(
    session: Session, org: Organization, max_width: float, max_height: float
) -> Flowable | None:
    if org.logo_file_id is None:
        return None
    stored = session.get(StoredFile, org.logo_file_id)
    if stored is None:
        return None
    try:
        data = read_file(stored)
        width, height = ImageReader(io.BytesIO(data)).getSize()
    except Exception:
        return None
    scale = min(max_width / width, max_height / height)
    return Image(io.BytesIO(data), width=width * scale, height=height * scale, hAlign="LEFT")


def letterhead(
    session: Session,
    org: Organization,
    on: date | None,
    title: str,
    meta: Sequence[tuple[str, str]],
    title_style: ParagraphStyle = TITLE,
    label_width: float = 1.1 * inch,
) -> Table:
    """Logo/name and business details on the left; document title and key facts on the right."""
    physical = org_address(session, org, on, AddressType.PHYSICAL, AddressType.REMIT)
    left: list[Flowable] = []
    image = logo(session, org, 2.6 * inch, 0.8 * inch)
    left.append(image if image else text(org.display_name, NAME))
    if org.tagline:
        left.append(text(org.tagline, SMALL))
    left.append(Spacer(1, 4))
    left.append(text(lines_of(format_address(physical), org.phone, org.email, org.website), SMALL))

    facts = Table(
        [[text(label, SMALL), text(value, RIGHT)] for label, value in meta],
        colWidths=[label_width, 2.7 * inch - label_width],
        style=TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        ),
    )
    right = [text(title, title_style), Spacer(1, 6), facts]
    return Table(
        [[left, right]],
        colWidths=[4.3 * inch, 2.9 * inch],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )


def boxed(title: str, body: str, width: float) -> Table:
    return Table(
        [[text(title, SMALL)], [text(body)]],
        colWidths=[width],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
    )


def totals_table(rows: Sequence[tuple[str, str, bool]]) -> Table:
    data = [
        [
            text(label, BOLD if strong else BODY),
            text(value, ParagraphStyle("t", parent=BOLD if strong else BODY, alignment=TA_RIGHT)),
        ]
        for label, value, strong in rows
    ]
    style: list[tuple[Any, ...]] = [
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for i, (_, _, strong) in enumerate(rows):
        if strong:
            style += [
                ("LINEABOVE", (0, i), (-1, i), 0.75, ACCENT),
                ("BACKGROUND", (0, i), (-1, i), LIGHT),
            ]
    return Table(data, colWidths=[1.9 * inch, 1.4 * inch], style=TableStyle(style), hAlign="RIGHT")


def items_table(
    header: Sequence[str], rows: Sequence[Sequence[Any]], widths: Sequence[float], right_from: int
) -> Table:
    data = [
        [
            text(
                h,
                ParagraphStyle(
                    "h",
                    parent=BOLD,
                    textColor=colors.white,
                    alignment=TA_RIGHT if i >= right_from else 0,
                ),
            )
            for i, h in enumerate(header)
        ]
    ]
    for row in rows:
        data.append(
            [
                cell
                if isinstance(cell, Flowable)
                else text(cell, RIGHT if i >= right_from else BODY)
                for i, cell in enumerate(row)
            ]
        )
    return Table(
        data,
        colWidths=list(widths),
        repeatRows=1,
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.lightgrey),
            ]
        ),
    )


def build(story: list[Flowable], footer: str, stamp: str | None = None) -> bytes:
    """Lay out the story on Letter pages with a "page x of y" footer and an optional stamp."""
    buffer = io.BytesIO()

    class NumberedCanvas(Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._pages: list[dict[str, Any]] = []

        def showPage(self) -> None:
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._pages)
            for number, state in enumerate(self._pages, start=1):
                self.__dict__.update(state)
                self.setFont("Helvetica", 7.5)
                self.setFillColor(MUTED)
                self.drawString(0.65 * inch, 0.45 * inch, footer)
                self.drawRightString(
                    LETTER[0] - 0.65 * inch, 0.45 * inch, f"Page {number} of {total}"
                )
                if stamp:
                    self.saveState()
                    self.setFont("Helvetica-Bold", 90)
                    self.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.18))
                    self.translate(LETTER[0] / 2, LETTER[1] / 2)
                    self.rotate(35)
                    self.drawCentredString(0, 0, stamp)
                    self.restoreState()
                super().showPage()
            super().save()

    SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.8 * inch,
    ).build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()


# -- documents ------------------------------------------------------------------------------------


def invoice_pdf(session: Session, org: Organization, invoice: Invoice) -> bytes:
    f = Formatter(org)
    party = session.get(Party, invoice.party_id)
    credit = invoice.kind == InvoiceKind.CREDIT_NOTE
    title = "CREDIT NOTE" if credit else "INVOICE"
    number = invoice.number or "DRAFT"
    meta = [
        (f"{'Credit note' if credit else 'Invoice'} no.", number),
        ("Date", f.date(invoice.issue_date) or "—"),
    ]
    if not credit and invoice.due_date:
        meta.append(("Due", f.date(invoice.due_date)))
    if invoice.terms_text:
        meta.append(("Terms", invoice.terms_text))
    if party:
        meta.append(("Client no.", party.party_no))
    if credit and invoice.credited_invoice_id:
        original = session.get(Invoice, invoice.credited_invoice_id)
        if original and original.number:
            meta.append(("For invoice", original.number))

    story: list[Flowable] = [
        letterhead(session, org, invoice.issue_date, title, meta),
        Spacer(1, 16),
    ]
    bill_to = lines_of(
        invoice.bill_to_company,
        invoice.bill_to_name
        and (f"Attn: {invoice.bill_to_name}" if invoice.bill_to_company else invoice.bill_to_name),
        invoice.bill_to_line1,
        invoice.bill_to_line2,
        " ".join(
            p
            for p in (
                invoice.bill_to_city and f"{invoice.bill_to_city},",
                invoice.bill_to_region,
                invoice.bill_to_postal_code,
            )
            if p
        ),
        invoice.bill_to_country,
        invoice.bill_to_email,
    )
    story += [boxed("Bill to", bill_to, 3.4 * inch), Spacer(1, 14)]

    # The SKU column only when a line has one; it takes its width from the description.
    with_sku = any(line.sku for line in invoice.lines)
    rows = []
    for line in invoice.lines:
        qty = f.number(line.quantity) + (f" {line.unit}" if line.unit else "")
        discount = f.money(line.unit_discount) if line.unit_discount else ""
        row = [line.description, qty, f.money(line.unit_price), discount, f.money(line.line_total)]
        rows.append([line.sku or "", *row] if with_sku else row)
    header = ["Description", "Qty", "Unit price", "Discount", "Amount"]
    widths = [3.25 * inch, 0.9 * inch, 1.0 * inch, 0.9 * inch, 1.15 * inch]
    if with_sku:
        header = ["SKU", *header]
        widths = [1.15 * inch, 2.1 * inch, *widths[1:]]
    story.append(items_table(header, rows, widths, 2 if with_sku else 1))
    story.append(Spacer(1, 8))

    totals: list[tuple[str, str, bool]] = [("Subtotal", f.money(invoice.subtotal), False)]
    if invoice.freight:
        totals.append(("Freight", f.money(invoice.freight), False))
    if invoice.adjustment:
        totals.append((invoice.adjustment_note or "Adjustment", f.money(invoice.adjustment), False))
    for tax in invoice.taxes:
        totals.append((f"{tax.name} {f.rate(tax.rate)}".strip(), f.money(tax.amount), False))
    totals.append(("Total credit" if credit else "Total due", f.money(invoice.total), True))
    story.append(KeepTogether(totals_table(totals)))

    if invoice.notes:
        story += [Spacer(1, 12), boxed("Notes", invoice.notes, 7.2 * inch)]
    if not credit:
        remit = org_address(
            session, org, invoice.issue_date, AddressType.REMIT, AddressType.PHYSICAL
        )
        payable = lines_of(org.payable_to or org.legal_name, format_address(remit))
        story += [Spacer(1, 14), boxed("Please make payment payable to", payable, 3.4 * inch)]
    if org.footer_text:
        story += [Spacer(1, 10), text(org.footer_text, SMALL)]

    stamp = {InvoiceStatus.DRAFT: "DRAFT", InvoiceStatus.VOID: "VOID"}.get(invoice.status)
    return build(story, f"{org.display_name} · {title.title()} {number}", stamp)


def receipt_pdf(session: Session, org: Organization, payment: Payment) -> bytes:
    f = Formatter(org)
    party = session.get(Party, payment.party_id)
    meta = [("Received", f.date(payment.received_date) or "—"), ("Receipt no.", str(payment.id))]
    story: list[Flowable] = [
        letterhead(session, org, payment.received_date, "RECEIPT", meta),
        Spacer(1, 16),
    ]
    address = None
    if party:
        address = next(
            (a for a in party.addresses if a.is_default),
            party.addresses[0] if party.addresses else None,
        )
    story += [
        boxed(
            "Received from",
            lines_of(party.name if party else "", format_address(address)),
            3.4 * inch,
        ),
        Spacer(1, 14),
    ]

    method = " ".join(
        p
        for p in (
            (payment.method.value.replace("_", " ").title() if payment.method else None),
            payment.reference and f"#{payment.reference}",
        )
        if p
    )
    story.append(
        totals_table(
            [
                ("Payment method", method or "—", False),
                ("Amount received", f.money(payment.amount), True),
            ]
        )
    )
    story.append(Spacer(1, 12))

    rows = []
    applied = Decimal(0)
    for allocation in payment.allocations:
        invoice = session.get(Invoice, allocation.invoice_id)
        rows.append(
            [
                f"Invoice {invoice.number if invoice else allocation.invoice_id}",
                f.date(invoice.issue_date) if invoice else "",
                f.money(allocation.amount),
            ]
        )
        applied += allocation.amount
    if payment.amount - applied:
        rows.append(["Credit on account", "", f.money(payment.amount - applied)])
    if rows:
        story.append(
            items_table(
                ["Applied to", "Invoice date", "Amount"],
                rows,
                [3.9 * inch, 1.6 * inch, 1.7 * inch],
                2,
            )
        )
    if payment.notes:
        story += [Spacer(1, 12), boxed("Notes", payment.notes, 7.2 * inch)]
    story += [Spacer(1, 18), text("Thank you!", BOLD)]
    return build(story, f"{org.display_name} · Receipt {payment.id}")


def deposit_slip_pdf(session: Session, org: Organization, deposit: Deposit) -> bytes:
    f = Formatter(org)
    bank = session.get(Party, deposit.bank_party_id) if deposit.bank_party_id else None
    meta = [("Date", f.date(deposit.deposit_date) or "—"), ("Deposit no.", str(deposit.id))]
    if bank:
        meta.append(("Bank", bank.name))
    story: list[Flowable] = [
        letterhead(session, org, deposit.deposit_date, "DEPOSIT", meta),
        Spacer(1, 16),
    ]
    rows: list[list[Any]] = []
    total = Decimal(0)
    for payment in sorted(deposit.payments, key=lambda p: (p.received_date or date.min, p.id)):
        party = session.get(Party, payment.party_id)
        kind = payment.method.value.replace("_", " ").title() if payment.method else ""
        rows.append(
            [
                f.date(payment.received_date),
                party.name if party else "",
                " ".join(p for p in (kind, payment.reference) if p),
                f.money(payment.amount),
            ]
        )
        total += payment.amount
    for item in deposit.items:
        rows.append(["", item.description or "", "", f.money(item.amount)])
        total += item.amount
    story.append(
        items_table(
            ["Received", "From", "Method / no.", "Amount"],
            rows,
            [1.2 * inch, 3.0 * inch, 1.6 * inch, 1.4 * inch],
            3,
        )
    )
    story += [
        Spacer(1, 8),
        totals_table(
            [(f"{len(rows)} item(s)", "", False), ("Deposit total", f.money(total), True)]
        ),
    ]
    if deposit.notes:
        story += [Spacer(1, 12), boxed("Notes", deposit.notes, 7.2 * inch)]
    return build(story, f"{org.display_name} · Deposit {deposit.id}")


# -- reports --------------------------------------------------------------------------------------


@dataclass
class Rate:
    """A tax rate in a report cell (formatted as a percentage, not as money)."""

    value: Decimal | None


@dataclass
class ReportRow:
    cells: list[Any]  # str, int (a count), Decimal (money), Rate, date or None
    strong: bool = False  # a subtotal or total


@dataclass
class ReportDocument:
    """One report as a table, the same for the CSV download, the PDF and the email."""

    name: str  # file name without the extension, e.g. "sales-by-month-cash-2026-01-01-2026-12-31"
    title: str
    facts: list[tuple[str, str]]  # period, basis, grouping... (PDF heading)
    header: list[str]
    widths: list[float]  # inches; together 7.2 (the width between the margins)
    rows: list[ReportRow]
    right_from: int = 1  # the columns from here on are numbers
    summary: list[ReportRow] = field(default_factory=list)  # totals under the table
    note: str | None = None


REPORT_TITLE = ParagraphStyle("report-title", parent=TITLE, fontSize=15, leading=18)


def _cell(f: Formatter, value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f.money(value)
    if isinstance(value, Rate):
        return f.rate(value.value)
    if isinstance(value, date):
        return f.date(value)
    return str(value)


def report_pdf(
    session: Session, org: Organization, report: ReportDocument, generated: datetime
) -> bytes:
    f = Formatter(org)
    story: list[Flowable] = [
        # Narrow labels, so a period ("Jan 1, 2026 - Dec 31, 2026") fits on one line.
        letterhead(
            session, org, generated.date(), report.title, report.facts, REPORT_TITLE, 0.75 * inch
        ),
        Spacer(1, 16),
    ]
    strong_body = ParagraphStyle("strong-body", parent=BOLD)
    strong_right = ParagraphStyle("strong-right", parent=BOLD, alignment=TA_RIGHT)
    rows: list[list[Any]] = []
    for row in report.rows:
        cells = [_cell(f, v) for v in row.cells]
        if row.strong:
            rows.append(
                [
                    text(c, strong_right if i >= report.right_from else strong_body)
                    for i, c in enumerate(cells)
                ]
            )
        else:
            rows.append(cells)
    if not rows:
        rows.append(["Nothing in this period", *[""] * (len(report.header) - 1)])
    table = items_table(report.header, rows, [w * inch for w in report.widths], report.right_from)
    table.setStyle(
        TableStyle(
            [
                cmd
                for i, row in enumerate(report.rows, start=1)
                if row.strong
                for cmd in (
                    ("LINEABOVE", (0, i), (-1, i), 0.75, ACCENT),
                    ("BACKGROUND", (0, i), (-1, i), LIGHT),
                )
            ]
        )
    )
    story.append(table)
    if report.summary:
        story.append(Spacer(1, 10))
        summary = [
            (
                str(row.cells[0]),
                _cell(f, next((v for v in reversed(row.cells) if v not in (None, "")), None)),
                row.strong,
            )
            for row in report.summary
        ]
        story.append(KeepTogether(totals_table(summary)))
    if report.note:
        story += [Spacer(1, 12), text(report.note, SMALL)]
    footer = f"{org.display_name} · {report.title} · generated {f.timestamp(generated)}"
    return build(story, footer)
