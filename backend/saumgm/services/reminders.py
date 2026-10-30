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

"""What needs doing: the to-do list, and the digest email that sends it.

The list is made of sections (bill clients, pay vendors, collect, documents), each from one
provider in SECTIONS; a new module adds its own provider there, as it adds its router to
main.ROUTERS. The to-do page, the dashboard and `python -m saumgm notify` all use `build`.
Billing clients and paying vendors stay separate sections on purpose.
"""

import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from saumgm.config import get_settings
from saumgm.documents import Formatter
from saumgm.enums import (
    DocumentStatus,
    DocumentType,
    EmailKind,
    InvoiceKind,
    InvoiceStatus,
    SubscriptionStatus,
    UserRoleType,
)
from saumgm.models import (
    BankAccount,
    CatalogItem,
    Invoice,
    Organization,
    Party,
    PartyDocument,
    User,
    UserRole,
    VendorSubscription,
)
from saumgm.schemas.reminders import ReminderItem, ReminderSection, RemindersOut
from saumgm.services import assets, banking, party_documents
from saumgm.services import invoices as invoice_service
from saumgm.services import subscriptions as subscription_service
from saumgm.services.emailing import ADDRESS, Draft
from saumgm.timeutil import today_in, utcnow

# The digest lists this many items per section, then says how many more there are.
DIGEST_ITEMS = 25

DOCUMENT_TYPES = {
    DocumentType.W9: "W-9",
    DocumentType.W8: "W-8",
    DocumentType.TAX_EXEMPTION: "Tax exemption certificate",
    DocumentType.INSURANCE: "Certificate of insurance",
    DocumentType.CONTRACT: "Contract",
    DocumentType.OTHER: "Document",
}


@dataclass
class Item:
    title: str
    date: date | None
    link: str  # a path in the app
    amount: Decimal | None = None
    note: str | None = None
    # overdue, autopay, expired, expiring: lets the screen colour the row
    flag: str | None = None


@dataclass
class Section:
    key: str
    title: str
    # One clause for the digest's opening and the dashboard, e.g. "3 client subscriptions are
    # due for billing within 14 days".
    summary: str
    # A few words for the email subject, e.g. "3 to bill".
    short: str
    link: str
    items: list[Item]
    action: tuple[str, str] | None = None  # (label, path), e.g. the billing run


@dataclass
class Reminders:
    today: date
    last_sign_in: datetime | None
    sections: list[Section] = field(default_factory=list)  # only sections with something in

    @property
    def idle_days(self) -> int | None:
        """Whole days since anyone signed in; None if nobody ever has."""
        if self.last_sign_in is None:
            return None
        return max((utcnow() - self.last_sign_in).days, 0)

    @property
    def count(self) -> int:
        return sum(len(s.items) for s in self.sections)


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else many or one + 's'}"


def path(base: str, **query: str | None) -> str:
    values = {k: v for k, v in query.items() if v}
    return f"{base}?{urlencode(values)}" if values else base


# -- sections -------------------------------------------------------------------------------------


def bill_clients(session: Session, org: Organization, today: date) -> Section | None:
    through = today + timedelta(days=org.remind_bill_days)
    due = subscription_service.due_subscriptions(session, org.id, through)
    names = _party_names(session, {s.party_id for s in due})
    items = []
    for sub in sorted(due, key=lambda s: (s.next_bill_date or today, s.id)):
        total = Decimal(0)
        for line in sub.lines:
            item = session.get(CatalogItem, line.catalog_item_id)
            assert item is not None
            total += subscription_service.line_total(line, item, org.currency_code)
        what = ", ".join(line.description for line in sub.lines)
        if sub.service_identifier:
            what += f" ({sub.service_identifier})"
        late = sub.next_bill_date is not None and sub.next_bill_date < today
        items.append(
            Item(
                title=f"{names.get(sub.party_id, '?')}: {what}",
                date=sub.next_bill_date,
                link=path("/subscriptions", due=through.isoformat(), q=sub.service_identifier),
                amount=total,
                note="billing date has passed" if late else None,
                flag="overdue" if late else None,
            )
        )
    drafts = (
        session.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.organization_id == org.id, Invoice.status == InvoiceStatus.DRAFT)
        )
        or 0
    )
    if drafts:
        items.append(
            Item(
                title=f"{plural(drafts, 'draft invoice')} to review and issue",
                date=None,
                link="/invoices?view=draft",
            )
        )
    if not items:
        return None
    parts = []
    if due:
        are = "is" if len(due) == 1 else "are"
        within = plural(org.remind_bill_days, "day")
        parts.append(
            f"{plural(len(due), 'client subscription')} {are} due for billing within {within}"
        )
    if drafts:
        are = "is" if drafts == 1 else "are"
        parts.append(f"{plural(drafts, 'draft invoice')} {are} waiting to be issued")
    return Section(
        key="bill",
        title="Bill clients",
        summary="; ".join(parts),
        short=f"{len(due)} to bill" if due else plural(drafts, "draft"),
        link=path("/subscriptions", due=through.isoformat()),
        items=items,
        action=("Billing run", path("/subscriptions", bill=through.isoformat())) if due else None,
    )


def pay_vendors(session: Session, org: Organization, today: date) -> Section | None:
    through = today + timedelta(days=org.remind_pay_days)
    due = session.scalars(
        select(VendorSubscription)
        .where(
            VendorSubscription.organization_id == org.id,
            VendorSubscription.status == SubscriptionStatus.ACTIVE,
            VendorSubscription.next_due_date.is_not(None),
            VendorSubscription.next_due_date <= through,
            or_(
                VendorSubscription.end_date.is_(None),
                VendorSubscription.next_due_date <= VendorSubscription.end_date,
            ),
        )
        .order_by(VendorSubscription.next_due_date, VendorSubscription.id)
    ).all()
    if not due:
        return None
    names = _party_names(session, {v.party_id for v in due})
    items = []
    for vendor in due:
        late = vendor.next_due_date is not None and vendor.next_due_date < today
        what = vendor.name + (
            f" ({vendor.service_identifier})" if vendor.service_identifier else ""
        )
        note: str | None = None
        flag: str | None = None
        if vendor.autopay:
            note, flag = "autopay: will be charged, check the account", "autopay"
        elif late:
            note, flag = "past due", "overdue"
        items.append(
            Item(
                title=f"{names.get(vendor.party_id, '?')}: {what}",
                date=vendor.next_due_date,
                link=path(
                    "/vendor-subscriptions",
                    due=through.isoformat(),
                    q=vendor.service_identifier or vendor.name,
                ),
                amount=vendor.amount,
                note=note,
                flag=flag,
            )
        )
    are = "is" if len(due) == 1 else "are"
    within = plural(org.remind_pay_days, "day")
    autopay = sum(1 for v in due if v.autopay)
    summary = f"{plural(len(due), 'vendor payment')} {are} due within {within}"
    if autopay:
        summary += f" ({autopay} by autopay)"
    return Section(
        key="pay",
        title="Pay vendors",
        summary=summary,
        short=f"{len(due)} to pay",
        link=path("/vendor-subscriptions", due=through.isoformat()),
        items=items,
    )


def collect(session: Session, org: Organization, today: date) -> Section | None:
    issued = session.scalars(
        select(Invoice).where(
            Invoice.organization_id == org.id,
            Invoice.kind == InvoiceKind.INVOICE,
            Invoice.status == InvoiceStatus.ISSUED,
            Invoice.due_date < today,
        )
    ).all()
    infos = invoice_service.balances(session, issued, today)
    overdue = sorted(
        (i for i in issued if infos[i.id].overdue), key=lambda i: (i.due_date or today, i.id)
    )
    if not overdue:
        return None
    names = _party_names(session, {i.party_id for i in overdue})
    items = [
        Item(
            title=f"{names.get(i.party_id, '?')}: invoice {i.number}",
            date=i.due_date,
            link=f"/invoices/{i.id}",
            amount=infos[i.id].balance_due,
            note=plural((today - i.due_date).days, "day") + " overdue" if i.due_date else None,
            flag="overdue",
        )
        for i in overdue
    ]
    total = sum((infos[i.id].balance_due for i in overdue), Decimal(0))
    are = "is" if len(overdue) == 1 else "are"
    return Section(
        key="collect",
        title="Collect",
        summary=f"{plural(len(overdue), 'invoice')} {are} overdue, "
        f"{Formatter(org).money(total)} in all",
        short=f"{len(overdue)} overdue",
        link="/invoices?view=overdue",
        items=items,
    )


def documents(session: Session, org: Organization, today: date) -> Section | None:
    docs: list[PartyDocument] = party_documents.needing_attention(session, org.id, today)
    if not docs:
        return None
    names = _party_names(session, {d.party_id for d in docs})
    items = []
    for doc in docs:
        expired = party_documents.status(doc, today) == DocumentStatus.EXPIRED
        kind = DOCUMENT_TYPES.get(doc.document_type, "Document")
        title = doc.title if doc.title.lower().startswith(kind.lower()) else f"{kind}: {doc.title}"
        items.append(
            Item(
                title=f"{names.get(doc.party_id, '?')}: {title}",
                date=doc.expires_on,
                link=f"/contacts/{doc.party_id}?tab=documents",
                note="expired" if expired else "expires soon",
                flag="expired" if expired else "expiring",
            )
        )
    expired_count = sum(1 for i in items if i.flag == "expired")
    parts = []
    if expired_count:
        parts.append(f"{expired_count} expired")
    if len(items) - expired_count:
        parts.append(f"{len(items) - expired_count} expiring soon")
    return Section(
        key="documents",
        title="Documents",
        summary=f"{plural(len(items), 'contact document')} need attention ({', '.join(parts)})",
        short=plural(len(items), "document"),
        link="/contacts",
        items=items,
    )


def reconcile(session: Session, org: Organization, today: date) -> Section | None:
    """Open accounts whose last reconciled statement (or start) is older than the lead time."""
    accounts = session.scalars(
        select(BankAccount)
        .where(BankAccount.organization_id == org.id, BankAccount.is_active.is_(True))
        .order_by(BankAccount.name)
    ).all()
    last = banking.last_reconciliations(session, (a.id for a in accounts))
    cutoff = today - timedelta(days=org.remind_reconcile_days)
    items = []
    for account in accounts:
        rec = last.get(account.id)
        since = rec.statement_date if rec else account.opening_date
        if since >= cutoff:
            continue
        note = (
            f"last statement reconciled: {plural((today - since).days, 'day')} ago"
            if rec
            else "never reconciled"
        )
        items.append(
            Item(
                title=account.name,
                date=rec.statement_date if rec else None,
                link=f"/banking/{account.id}",
                note=note,
                flag="overdue",
            )
        )
    if not items:
        return None
    have = "has" if len(items) == 1 else "have"
    return Section(
        key="banking",
        title="Banking",
        summary=f"{plural(len(items), 'bank account')} {have} not been reconciled within "
        f"{plural(org.remind_reconcile_days, 'day')}",
        short=f"{len(items)} to reconcile",
        link="/banking",
        items=items,
    )


def asset_contracts(session: Session, org: Organization, today: date) -> Section | None:
    """Warranties and support contracts of assets in use ending soon (or just ended)."""
    rows = assets.ending(session, org.id, today, org.remind_asset_days)
    if not rows:
        return None
    names = _party_names(session, {a.owner_party_id for a, _, _ in rows if a.owner_party_id})
    items = []
    for asset, what, day in rows:
        label = "warranty" if what == "warranty" else "support contract"
        owner = names.get(asset.owner_party_id) if asset.owner_party_id else None
        mine = asset.owner_party_id is None or asset.owner_party_id == org.self_party_id
        items.append(
            Item(
                title=f"{asset.tag} {asset.name}" + ("" if mine or not owner else f" ({owner})"),
                date=day,
                link=f"/assets/{asset.id}",
                note=f"{label} {'ended' if day < today else 'ends'}",
                flag="expired" if day < today else "expiring",
            )
        )
    are = "is" if len(items) == 1 else "are"
    contract, contracts = "warranty or support contract", "warranties or support contracts"
    return Section(
        key="assets",
        title="Assets",
        summary=f"{plural(len(items), contract, contracts)} {are} ending around now "
        f"(within {plural(org.remind_asset_days, 'day')})",
        short=plural(len(items), "warranty", "warranties"),
        link="/assets",
        items=items,
    )


# The to-do list in order.
SECTIONS: tuple[Callable[[Session, Organization, date], Section | None], ...] = (
    bill_clients,
    pay_vendors,
    collect,
    documents,
    reconcile,
    asset_contracts,
)


def _party_names(session: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict(session.execute(select(Party.id, Party.name).where(Party.id.in_(ids))).all())


def last_sign_in(session: Session, org_id: int) -> datetime | None:
    return session.scalar(
        select(func.max(User.last_login_at))
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.organization_id == org_id, User.is_active.is_(True))
    )


def build(session: Session, org: Organization, today: date | None = None) -> Reminders:
    today = today or today_in(org.timezone)
    sections = [s for provider in SECTIONS if (s := provider(session, org, today)) is not None]
    return Reminders(today=today, last_sign_in=last_sign_in(session, org.id), sections=sections)


def to_out(reminders: Reminders) -> RemindersOut:
    """For the API and `notify --json`."""
    return RemindersOut(
        today=reminders.today,
        last_sign_in=reminders.last_sign_in,
        idle_days=reminders.idle_days,
        summary=opening(reminders),
        count=reminders.count,
        sections=[
            ReminderSection(
                key=s.key,
                title=s.title,
                summary=s.summary,
                link=s.link,
                action_label=s.action[0] if s.action else None,
                action_link=s.action[1] if s.action else None,
                items=[
                    ReminderItem(
                        title=i.title,
                        date=i.date,
                        link=i.link,
                        amount=i.amount,
                        note=i.note,
                        flag=i.flag,
                    )
                    for i in s.items
                ],
            )
            for s in reminders.sections
        ],
    )


# -- the digest -----------------------------------------------------------------------------------


def owners(session: Session, org_id: int) -> list[str]:
    return list(
        session.scalars(
            select(User.email)
            .join(UserRole, UserRole.user_id == User.id)
            .where(
                UserRole.organization_id == org_id,
                UserRole.role == UserRoleType.OWNER,
                User.is_active.is_(True),
            )
            .order_by(User.id)
        )
    )


def split_addresses(value: str | None) -> list[str]:
    return [a for a in re.split(r"[\s,;]+", value or "") if a]


def recipients(session: Session, org: Organization) -> list[str]:
    """Admin -> Reminders, or else every owner."""
    return split_addresses(org.remind_to) or owners(session, org.id)


def bad_addresses(addresses: list[str]) -> list[str]:
    return [a for a in addresses if not ADDRESS.match(a)]


def opening(reminders: Reminders) -> str:
    """'Nobody has signed in for 20 days. 3 client subscriptions are due for billing ...'"""
    sentences = []
    idle = reminders.idle_days
    if idle is None:
        sentences.append("Nobody has signed in yet.")
    elif idle >= 2:
        sentences.append(f"Nobody has signed in for {idle} days.")
    if reminders.sections:
        clauses = "; ".join(s.summary for s in reminders.sections)
        sentences.append(clauses[0].upper() + clauses[1:] + ".")
    else:
        sentences.append("Nothing needs doing right now.")
    return " ".join(sentences)


def digest_draft(session: Session, org: Organization, reminders: Reminders) -> Draft:
    f = Formatter(org)
    base = (get_settings().app_url or "").rstrip("/")

    def url(link: str) -> str | None:
        return base + link if base else None

    def line(item: Item) -> str:
        parts = [item.title]
        if item.amount is not None:
            parts.append(f.money(item.amount))
        text = ", ".join(parts)
        if item.note:
            text += f" ({item.note})"
        return f"{f.date(item.date)}: {text}" if item.date else text

    subject = f"To do at {org.display_name}"
    if reminders.sections:
        subject += ": " + ", ".join(s.short for s in reminders.sections)

    text = [opening(reminders)]
    page = [f"<p>{html.escape(opening(reminders))}</p>"]
    for section in reminders.sections:
        shown, more = section.items[:DIGEST_ITEMS], len(section.items) - DIGEST_ITEMS
        text.append(
            "\n".join(
                [section.title.upper()]
                + [f"- {line(i)}" for i in shown]
                + ([f"- and {more} more"] if more > 0 else [])
                + ([f"Open: {url(section.link)}"] if base else [])
            )
        )
        rows = []
        for i in shown:
            target = url(i.link)
            label = html.escape(line(i))
            rows.append(
                f'<li><a href="{html.escape(target)}">{label}</a></li>'
                if target
                else f"<li>{label}</li>"
            )
        if more > 0:
            rows.append(f"<li>and {more} more</li>")
        heading = html.escape(section.title)
        if base:
            heading = f'<a href="{html.escape(base + section.link)}">{heading}</a>'
        actions = ""
        if section.action and base:
            label, link = section.action
            actions = f'<p><a href="{html.escape(base + link)}">{html.escape(label)}</a></p>'
        page.append(f"<h3>{heading}</h3><ul>{''.join(rows)}</ul>{actions}")
    if base:
        text.append(f"To-do list: {base}/todo")
        page.append(f'<p><a href="{html.escape(base)}/todo">Open the to-do list</a></p>')
    text.append(f"Sent by SauMGM for {org.display_name}.")
    page.append(f'<p style="color:#888">Sent by SauMGM for {html.escape(org.display_name)}.</p>')

    return Draft(
        kind=EmailKind.DIGEST,
        entity_type=None,
        entity_id=None,
        to=recipients(session, org),
        cc=[],
        subject=subject,
        body="\n\n".join(text),
        html=(
            '<div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; '
            f'line-height: 1.5; color: #222">{"".join(page)}</div>'
        ),
    )
