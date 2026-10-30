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

"""Demo data: a fictional IT business with 10 clients, 5 vendors and about 15 months of history.

    python -m saumgm load-demo        # into an empty, migrated database

Everything goes through the same services the app uses (numbering, tax, billing run, payments,
deposits, PDFs), so the result behaves like real data: open and overdue invoices, a credit note,
a revision, a void, a write-off, deposits, expenses with receipts, client subscriptions coming
up for renewal and the vendor subscriptions behind them, a sales-tax filing, a tax-exempt client
and documents that are about to expire.

Dates are relative to the day it is loaded, so a fresh demo always looks current. Names,
addresses and numbers are made up (555 phone numbers, .example domains).
"""

import io
import random
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saumgm.email import NoSendBackend, use_backend
from saumgm.enums import (
    AccountType,
    AddressType,
    ArticleStatus,
    ArticleVisibility,
    AssetStatus,
    BankAccountKind,
    BankEntryStatus,
    BillingTiming,
    DocumentType,
    EmailKind,
    FilingFrequency,
    InvoiceKind,
    InvoiceStatus,
    ItemType,
    JurisdictionLevel,
    PartyKind,
    PartyRoleType,
    PaymentChannel,
    PaymentMethod,
    SubscriptionStatus,
    TaxBasis,
    UserRoleType,
)
from saumgm.models import (
    Account,
    Asset,
    AssetAttachment,
    AssetCategory,
    BankAccount,
    BankEntry,
    CatalogItem,
    CatalogPackage,
    CatalogPackageItem,
    EmailTemplate,
    Expense,
    ExpenseAttachment,
    ExpenseLine,
    Invoice,
    KbArticle,
    KbAttachment,
    KbCategory,
    Organization,
    OrganizationAddress,
    Party,
    PartyAddress,
    PartyContact,
    PartyDocument,
    PartyRole,
    Payment,
    RevenueCategory,
    Subscription,
    SubscriptionLine,
    SubscriptionUse,
    TaxabilityRule,
    TaxCategory,
    TaxExemption,
    TaxFiling,
    TaxJurisdiction,
    TaxRate,
    TaxRegistration,
    User,
    VendorSubscription,
)
from saumgm.schemas.invoices import LineIn
from saumgm.seed import OrganizationSetup, create_organization
from saumgm.services import (
    archive,
    banking,
    emailing,
    knowledge,
    payments,
    reports,
    subscriptions,
    tax_periods,
)
from saumgm.services import invoices as invoice_service
from saumgm.services.auth import create_user
from saumgm.services.numbering import next_number
from saumgm.storage import store_file
from saumgm.timeutil import today_in

DEMO_PASSWORD = "saumgm-demo"
DEMO_USERS = [
    ("owner@example.com", "Dana Owner", UserRoleType.OWNER),
    ("bookkeeper@example.com", "Ben Bookkeeper", UserRoleType.BOOKKEEPER),
    ("viewer@example.com", "Val Viewer", UserRoleType.VIEWER),
]
MONTHS_OF_HISTORY = 15

D = Decimal


class DemoError(Exception):
    pass


@dataclass
class Summary:
    organization: Organization
    counts: dict[str, int] = field(default_factory=dict)


# -- generated files ------------------------------------------------------------------------------


def _pdf(title: str, lines: list[str]) -> bytes:
    """A one-page placeholder PDF (demo documents and receipts)."""
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=LETTER)
    page.setTitle(title)
    page.setFont("Helvetica-Bold", 18)
    page.drawString(72, 700, title)
    page.setFont("Helvetica", 11)
    y = 670
    for line in lines:
        page.drawString(72, y, line)
        y -= 18
    page.setFont("Helvetica-Oblique", 9)
    page.drawString(72, 72, "SauMGM demo data: a made-up sample document, not a real form.")
    page.showPage()
    page.save()
    return buffer.getvalue()


def _logo() -> bytes:
    image = Image.new("RGB", (900, 220), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 30, 170, 190), radius=28, fill=(31, 111, 92))
    draw.polygon([(40, 165), (90, 60), (140, 165)], fill=(255, 255, 255))
    try:
        font = ImageFont.load_default(size=74)
        small = ImageFont.load_default(size=30)
    except TypeError:  # Pillow < 10.1
        font = small = ImageFont.load_default()
    draw.text((200, 40), "Maple Ridge Tech", fill=(31, 111, 92), font=font)
    draw.text((204, 140), "Web hosting · IT support · Networking", fill=(90, 90, 90), font=small)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _diagram() -> bytes:
    """A network diagram for the demo's knowledge base."""
    image = Image.new("RGB", (720, 260), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=22)
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
    boxes = [("Internet", 20), ("Router 10.0.0.1", 260), ("NAS 10.0.0.20", 500)]
    for label, x in boxes:
        draw.rounded_rectangle((x, 90, x + 200, 170), radius=14, outline=(31, 111, 92), width=4)
        draw.text((x + 16, 118), label, fill=(31, 111, 92), font=font)
    for x in (220, 460):
        draw.line((x, 130, x + 40, 130), fill=(90, 90, 90), width=4)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


# -- the loader -----------------------------------------------------------------------------------


class DemoLoader:
    def __init__(self, session: Session, today: date | None = None, seed: int = 2026) -> None:
        self.s = session
        self.rng = random.Random(seed)
        self._today = today
        self.parties: dict[str, Party] = {}
        self.items: dict[str, CatalogItem] = {}
        self.accounts: dict[str, Account] = {}
        self.categories: dict[str, TaxCategory] = {}
        self.vendor_subs: dict[str, VendorSubscription] = {}
        self.special: set[int] = set()  # invoices whose payment story is scripted

    # -- setup ------------------------------------------------------------------------------------

    def organization(self) -> None:
        self.org = create_organization(
            self.s,
            OrganizationSetup(
                legal_name="Maple Ridge Tech LLC",
                display_name="Maple Ridge Tech",
                payable_to="Maple Ridge Tech LLC",
                tagline="Web hosting, IT support and networking",
                phone="(716) 555-0100",
                email="billing@mapleridge.example",
                website="https://www.mapleridge.example",
                invoice_number_next=1001,
            ),
        )
        org = self.org
        org.footer_text = "Thank you for your business! Questions? billing@mapleridge.example"
        org.tax_basis = TaxBasis.ACCRUAL
        org.fiscal_year_start_month = 1
        self.today = self._today or today_in(org.timezone)
        self.start = self.today - timedelta(days=MONTHS_OF_HISTORY * 30)

        self.s.add_all(
            [
                OrganizationAddress(
                    organization_id=org.id, address_type=AddressType.REMIT,
                    line1="PO Box 214", city="Springville", region="NY", postal_code="14141",
                    country_code="US", effective_from=self.today - timedelta(days=5 * 365),
                ),
                OrganizationAddress(
                    organization_id=org.id, address_type=AddressType.PHYSICAL,
                    line1="88 Maple Ridge Road", city="Springville", region="NY",
                    postal_code="14141", country_code="US", phone="(716) 555-0100",
                ),
            ]
        )  # fmt: skip
        logo = store_file(self.s, org.id, _logo(), "maple-ridge-logo.png", "image/png")
        org.logo_file_id = logo.id

        self.owner: User | None = None
        for email, name, role in DEMO_USERS:
            user = create_user(self.s, org.id, email, name, role, DEMO_PASSWORD)
            if role == UserRoleType.OWNER:
                self.owner = user

        me = self.party(
            "SELF", "Maple Ridge Tech LLC", [PartyRoleType.SELF], city="Springville",
            line1="88 Maple Ridge Road", postal="14141", email="billing@mapleridge.example",
            phone="(716) 555-0100",
        )  # fmt: skip
        org.self_party_id = me.id
        self.s.flush()

    def jurisdiction(self, code: str) -> TaxJurisdiction:
        return self.s.scalars(
            select(TaxJurisdiction).where(
                TaxJurisdiction.organization_id == self.org.id, TaxJurisdiction.code == code
            )
        ).one()

    def tax_setup(self) -> None:
        org = self.org
        self.categories = {
            c.code: c
            for c in self.s.scalars(
                select(TaxCategory).where(TaxCategory.organization_id == org.id)
            )
        }
        ny = self.jurisdiction("US-NY")
        self.ny = ny

        def county(code: str, name: str, rate: str) -> TaxJurisdiction:
            j = TaxJurisdiction(
                organization_id=org.id, parent_id=ny.id, level=JurisdictionLevel.COUNTY,
                code=code, name=name,
            )  # fmt: skip
            self.s.add(j)
            self.s.flush()
            self.s.add(
                TaxRate(jurisdiction_id=j.id, name=name, rate=D(rate), effective_from=self.start)
            )
            return j

        self.erie = county("US-NY-ERIE", "Erie County", "0.0475")
        self.catt = county("US-NY-CATTARAUGUS", "Cattaraugus County", "0.04")
        self.s.add(
            TaxRate(
                jurisdiction_id=ny.id, name="New York State", rate=D("0.04"),
                effective_from=self.start - timedelta(days=3650),
            )
        )  # fmt: skip
        # In this demo, labor and hosting are not taxed in New York; goods and software are.
        for code in ("services", "digital"):
            self.s.add(
                TaxabilityRule(
                    jurisdiction_id=ny.id,
                    tax_category_id=self.categories[code].id,
                    is_taxable=False,
                )
            )
        self.registration = TaxRegistration(
            organization_id=org.id,
            jurisdiction_id=ny.id,
            registration_number="DEMO-123456789",
            filing_frequency=FilingFrequency.ANNUAL,
            period_start_month=3,  # New York's sales-tax year starts in March
            effective_from=self.start - timedelta(days=3 * 365),
        )
        self.s.add(self.registration)
        self.s.flush()

    def party(
        self,
        key: str,
        name: str,
        roles: list[PartyRoleType],
        *,
        city: str,
        region: str = "NY",
        country: str = "US",
        postal: str = "",
        line1: str = "",
        kind: PartyKind = PartyKind.COMPANY,
        email: str | None = None,
        phone: str | None = None,
        person: tuple[str, str | None] | None = None,
        county: TaxJurisdiction | None = None,
        terms: int | None = None,
        tax_id: str | None = None,
        notes: str | None = None,
    ) -> Party:
        party = Party(
            organization_id=self.org.id,
            party_no=next_number(self.s, self.org.id, "party"),
            short_code=key,
            name=name,
            kind=kind,
            email=email,
            phone=phone,
            default_terms_days=terms,
            tax_id=tax_id,
            notes=notes,
        )
        party.roles = [PartyRole(role=r) for r in roles]
        party.addresses = [
            PartyAddress(
                address_type=AddressType.BILLING, is_default=True, line1=line1 or None,
                city=city, region=region, postal_code=postal or None, country_code=country,
                tax_jurisdiction_id=county.id if county else None,
            )
        ]  # fmt: skip
        if person:
            party.contacts = [
                PartyContact(name=person[0], title=person[1], email=email, phone=phone,
                             is_primary=True)
            ]  # fmt: skip
        self.s.add(party)
        self.s.flush()
        self.parties[key] = party
        return party

    def contacts(self) -> None:
        p = self.party
        client, vendor = [PartyRoleType.CLIENT], [PartyRoleType.VENDOR]
        p(
            "HILLTOP",
            "Hilltop Dental Group",
            client,
            city="Buffalo",
            postal="14201",
            line1="415 Delaware Ave",
            county=self.erie,
            email="office@hilltopdental.example",
            phone="(716) 555-0142",
            person=("Dr. Priya Raman", "Practice owner"),
        )
        p(
            "RIVERBEND",
            "Riverbend Diner",
            client,
            city="Olean",
            postal="14760",
            line1="12 Union St",
            county=self.catt,
            email="riverbenddiner@mail.example",
            phone="(716) 555-0177",
            person=("Gus Petrakis", "Owner"),
            terms=15,
            notes="Slow payer; call before doing new work.",
        )
        p(
            "STMARKS",
            "St. Mark's Lutheran Church",
            client,
            city="Springville",
            postal="14141",
            line1="30 Church St",
            county=self.erie,
            email="secretary@stmarks.example",
            phone="(716) 555-0110",
            person=("Ruth Anderson", "Church secretary"),
        )
        p(
            "NLPHOTO",
            "Northern Lights Photography",
            client,
            city="Ellicottville",
            postal="14731",
            line1="7 Washington St",
            county=self.catt,
            kind=PartyKind.PERSON,
            email="jenna@northernlights.example",
            phone="(716) 555-0123",
            person=("Jenna Kowalski", None),
        )
        p(
            "KEYSTONE",
            "Keystone Auto Parts",
            client,
            city="Bradford",
            region="PA",
            postal="16701",
            line1="220 Main St",
            email="ap@keystoneauto.example",
            phone="(814) 555-0190",
            person=("Mike Dolan", "Office manager"),
        )
        p(
            "LAKESHORE",
            "Lakeshore Realty",
            client,
            city="Dunkirk",
            postal="14048",
            line1="51 Lake Shore Dr E",
            email="info@lakeshorerealty.example",
            phone="(716) 555-0166",
            person=("Carla Mendes", "Broker"),
        )
        p(
            "GLROBOT",
            "Great Lakes Robotics Inc.",
            client,
            city="Toronto",
            region="ON",
            country="CA",
            postal="M5V 2T6",
            line1="100 King St W, Suite 400",
            email="accounts@glrobotics.example",
            phone="(416) 555-0133",
            person=("Owen Tremblay", "Controller"),
            terms=45,
        )
        p(
            "MARTINFARM",
            "Martin Family Farm",
            client,
            city="Arcade",
            postal="14009",
            line1="9800 Route 39",
            kind=PartyKind.PERSON,
            email="tom@martinfarm.example",
            phone="(585) 555-0104",
            person=("Tom Martin", None),
        )
        p(
            "CYSL",
            "Cattaraugus Youth Soccer League",
            client,
            city="Little Valley",
            postal="14755",
            line1="PO Box 55",
            county=self.catt,
            email="treasurer@cysl.example",
            person=("Amy Fischer", "Treasurer"),
        )
        p(
            "PINECREST",
            "Pinecrest Senior Living",
            client,
            city="Salamanca",
            postal="14779",
            line1="600 Broad St",
            county=self.catt,
            email="it@pinecrest.example",
            phone="(716) 555-0188",
            person=("Luis Ortega", "Facilities director"),
        )

        p(
            "CLOUDPEAK",
            "CloudPeak Hosting",
            vendor,
            city="Pittsburgh",
            region="PA",
            postal="15222",
            email="billing@cloudpeak.example",
            phone="(412) 555-0150",
            tax_id="12-3456789",
        )
        p(
            "NAMEKEEPER",
            "NameKeeper Domains",
            vendor,
            city="Austin",
            region="TX",
            postal="78701",
            email="support@namekeeper.example",
        )
        p(
            "ALLEGHENY",
            "Allegheny Cable & Supply",
            vendor,
            city="Jamestown",
            postal="14701",
            email="orders@alleghenycable.example",
            phone="(716) 555-0155",
            person=("Sam Ricci", "Sales rep"),
            tax_id="16-9876543",
        )
        p(
            "PAPERTRAIL",
            "Paper Trail Office Supply",
            vendor,
            city="Orchard Park",
            postal="14127",
            email="orders@papertrail.example",
        )
        p(
            "VALLEYFIBER",
            "Valley Fiber Internet",
            vendor,
            city="Springville",
            postal="14141",
            email="accounts@valleyfiber.example",
            phone="(716) 555-0199",
        )

        p(
            "BANK",
            "Community Savings Bank",
            [PartyRoleType.FINANCIAL],
            city="Springville",
            postal="14141",
            line1="1 Main St",
        )
        p("NYSDTF", "NYS Department of Taxation and Finance", [PartyRoleType.TAX_AUTHORITY],
          city="Albany", postal="12227", line1="W A Harriman Campus")  # fmt: skip

    def catalog(self) -> None:
        org = self.org
        cats = {
            name: RevenueCategory(organization_id=org.id, name=name)
            for name in ("Hosting", "Domains", "Hardware", "Services", "Support plans")
        }
        self.s.add_all(cats.values())
        accounts = [
            ("4010", "Hosting costs", AccountType.COGS),
            ("4020", "Domain registrations", AccountType.COGS),
            ("4030", "Hardware for resale", AccountType.COGS),
            ("6100", "Internet and phone", AccountType.EXPENSE),
            ("6200", "Office supplies", AccountType.EXPENSE),
            ("6300", "Software subscriptions", AccountType.EXPENSE),
            ("6400", "Vehicle and travel", AccountType.EXPENSE),
            ("6500", "Bank fees", AccountType.EXPENSE),
        ]
        for code, name, kind in accounts:
            account = Account(organization_id=org.id, code=code, name=name, account_type=kind)
            self.accounts[code] = account
        self.s.add_all(self.accounts.values())
        self.s.flush()

        def item(
            key: str, name: str, kind: ItemType, price: str, category: str, tax: str, **extra: Any
        ) -> None:
            self.items[key] = CatalogItem(
                organization_id=org.id, name=name, item_type=kind, price=D(price),
                revenue_category_id=cats[category].id,
                tax_category_id=self.categories[tax].id, **extra,
            )  # fmt: skip

        sub = ItemType.SUBSCRIPTION
        vendor = self.parties
        item(
            "HOST",
            "Web hosting - business plan",
            sub,
            "240.00",
            "Hosting",
            "digital",
            unit="year",
            billing_interval_months=12,
            billing_timing=BillingTiming.ADVANCE,
            default_vendor_id=vendor["CLOUDPEAK"].id,
            unit_cost=D("96.00"),
            cogs_account_id=self.accounts["4010"].id,
            sku="HOST-BIZ",
        )
        item(
            "DOMAIN",
            "Domain registration (.com)",
            sub,
            "24.00",
            "Domains",
            "digital",
            unit="year",
            billing_interval_months=12,
            billing_timing=BillingTiming.ADVANCE,
            default_vendor_id=vendor["NAMEKEEPER"].id,
            unit_cost=D("12.50"),
            cogs_account_id=self.accounts["4020"].id,
            sku="DOM-COM",
        )
        item(
            "SSL",
            "SSL certificate",
            sub,
            "79.00",
            "Hosting",
            "digital",
            unit="year",
            billing_interval_months=12,
            billing_timing=BillingTiming.ADVANCE,
            sku="SSL-DV",
        )
        item(
            "BACKUP",
            "Managed cloud backup",
            sub,
            "35.00",
            "Support plans",
            "digital",
            unit="month",
            billing_interval_months=1,
            billing_timing=BillingTiming.ADVANCE,
            sku="BKP-100",
        )
        item(
            "CARE",
            "IT care plan (up to 3 hours)",
            sub,
            "189.00",
            "Support plans",
            "services",
            unit="month",
            billing_interval_months=1,
            billing_timing=BillingTiming.ADVANCE,
            sku="CARE-3",
        )
        item(
            "CONSULT",
            "Consulting",
            ItemType.SERVICE_HOURLY,
            "95.00",
            "Services",
            "services",
            unit="hour",
            sku="SVC-HR",
        )
        item(
            "ONSITE",
            "On-site support",
            ItemType.SERVICE_HOURLY,
            "110.00",
            "Services",
            "services",
            unit="hour",
            sku="SVC-ONS",
        )
        item(
            "WEBSITE",
            "Website setup (5 pages)",
            ItemType.SERVICE_FIXED,
            "850.00",
            "Services",
            "services",
            sku="WEB-5",
        )
        item(
            "ROUTER",
            "Business Wi-Fi router",
            ItemType.GOODS,
            "189.00",
            "Hardware",
            "goods",
            unit="ea",
            default_vendor_id=vendor["ALLEGHENY"].id,
            unit_cost=D("121.00"),
            cogs_account_id=self.accounts["4030"].id,
            sku="HW-RTR",
        )
        item(
            "SWITCH",
            "8-port network switch",
            ItemType.GOODS,
            "79.00",
            "Hardware",
            "goods",
            unit="ea",
            default_vendor_id=vendor["ALLEGHENY"].id,
            unit_cost=D("44.00"),
            cogs_account_id=self.accounts["4030"].id,
            sku="HW-SW8",
        )
        item(
            "CABLE",
            "Cat6 patch cable, 25 ft",
            ItemType.GOODS,
            "18.00",
            "Hardware",
            "goods",
            unit="ea",
            default_vendor_id=vendor["ALLEGHENY"].id,
            unit_cost=D("6.50"),
            cogs_account_id=self.accounts["4030"].id,
            sku="HW-C6-25",
        )
        item(
            "OFFICE",
            "Office suite license (1 year)",
            ItemType.GOODS,
            "99.00",
            "Hardware",
            "software",
            unit="ea",
            sku="SW-OFF",
        )
        self.items["OLDHOST"] = CatalogItem(
            organization_id=org.id, name="Web hosting - starter plan (retired)", item_type=sub,
            price=D("120.00"), is_active=False, billing_interval_months=12,
            revenue_category_id=cats["Hosting"].id, tax_category_id=self.categories["digital"].id,
        )  # fmt: skip
        self.s.add_all(self.items.values())
        self.s.flush()

    def exemptions_and_documents(self) -> None:
        church = self.parties["STMARKS"]
        exemption = TaxExemption(
            party_id=church.id,
            jurisdiction_id=self.ny.id,
            certificate_type="Exempt organization (ST-119.1)",
            certificate_number="EX-204518",
            valid_from=self.start - timedelta(days=700),
            valid_to=self.today + timedelta(days=25),
        )
        church.tax_exemptions.append(exemption)
        self.s.flush()

        def doc(
            key: str,
            kind: DocumentType,
            title: str,
            *,
            with_file: bool = True,
            signed: int | None = None,
            expires: int | None = None,
            **extra: Any,
        ) -> None:
            party = self.parties[key]
            stored = None
            if with_file:
                pdf = _pdf(
                    title, [party.name, f"Signed: {self.today - timedelta(days=signed or 0)}"]
                )
                name = title.lower().replace(" ", "-").replace("/", "-") + ".pdf"
                stored = store_file(self.s, self.org.id, pdf, name, "application/pdf")
            self.s.add(
                PartyDocument(
                    organization_id=self.org.id, party_id=party.id, document_type=kind,
                    title=title, file_id=stored.id if stored else None,
                    document_date=self.today - timedelta(days=signed) if signed else None,
                    expires_on=self.today + timedelta(days=expires) if expires is not None
                    else None, **extra,
                )
            )  # fmt: skip

        doc(
            "STMARKS",
            DocumentType.TAX_EXEMPTION,
            "ST-119.1 exempt organization certificate",
            signed=700,
            expires=25,
            tax_exemption_id=exemption.id,
        )
        doc("CLOUDPEAK", DocumentType.W9, "W-9", signed=400)
        doc("ALLEGHENY", DocumentType.W9, "W-9", signed=380)
        doc(
            "NAMEKEEPER",
            DocumentType.W9,
            "W-9 (paper copy)",
            with_file=False,
            signed=300,
            notes="Original in the vendor binder",
        )
        doc(
            "ALLEGHENY",
            DocumentType.INSURANCE,
            "Certificate of liability insurance",
            signed=353,
            expires=12,
            remind_days_before=30,
        )
        doc("GLROBOT", DocumentType.W8, "W-8BEN-E", signed=420)
        doc(
            "HILLTOP",
            DocumentType.CONTRACT,
            "Managed services agreement",
            signed=380,
            expires=-6,
            notes="Renewal sent; waiting for signature",
        )
        doc("PINECREST", DocumentType.CONTRACT, "IT care plan agreement", signed=200, expires=165)
        self.s.flush()

    # -- subscriptions and the billing history ----------------------------------------------------

    def subs(self) -> None:
        org, items = self.org, self.items

        for name, entries in (
            ("Hosting + domain", [("HOST", None), ("DOMAIN", None)]),
            ("Website starter", [("HOST", None), ("DOMAIN", None), ("SSL", "59.00")]),
            ("Care plan with backup", [("CARE", None), ("BACKUP", "29.00")]),
        ):
            package = CatalogPackage(organization_id=org.id, name=name)
            package.items = [
                CatalogPackageItem(sort_order=n, catalog_item_id=items[key].id,
                                   price=D(price) if price else None)
                for n, (key, price) in enumerate(entries)
            ]  # fmt: skip
            self.s.add(package)

        def next_on(day: int) -> date:
            """The next time this day of the month comes round, after today."""
            due = self.today.replace(day=day)
            return due if due > self.today else subscriptions.add_months(due, 1)

        def anniversary(start: date) -> date:
            due = start
            while due <= self.today:
                due = subscriptions.add_months(due, 12)
            return due

        def vendor_sub(
            key: str, vendor: str, name: str, amount: str, months: int, account: str, **extra: Any
        ) -> VendorSubscription:
            vs = VendorSubscription(
                organization_id=org.id, party_id=self.parties[vendor].id, name=name,
                amount=D(amount), interval_months=months,
                expense_account_id=self.accounts[account].id, **extra,
            )  # fmt: skip
            self.s.add(vs)
            self.vendor_subs[key] = vs
            return vs

        # Paid every month in `expenses`, which links each payment to these.
        vendor_sub("FIBER", "VALLEYFIBER", "Business fiber", "89.99", 1, "6100",
                   next_due_date=next_on(5), autopay=True, paid_from_account_id=self.card.id,
                   notes="Charged to the business card")  # fmt: skip
        vendor_sub("SERVER", "CLOUDPEAK", "Reseller server", "120.00", 1, "4010",
                   service_identifier="host-01.cloudpeak.example", next_due_date=next_on(10),
                   autopay=True, paid_from_account_id=self.card.id)  # fmt: skip
        vendor_sub("OLDPLAN", "CLOUDPEAK", "Shared hosting plan", "8.00", 1, "4010",
                   status=SubscriptionStatus.CANCELLED, auto_renew=False,
                   end_date=self.start + timedelta(days=30),
                   notes="Replaced by the reseller server")  # fmt: skip
        self.s.flush()

        def sub(
            key: str,
            days_ago: int,
            identifier: str | None,
            lines: list[tuple[str, dict[str, Any]]],
            **extra: Any,
        ) -> None:
            start = self.today - timedelta(days=days_ago)
            first = items[lines[0][0]]
            subscription = Subscription(
                organization_id=org.id, party_id=self.parties[key].id,
                service_identifier=identifier,
                billing_interval_months=first.billing_interval_months or 1,
                start_date=start, next_bill_date=start, status=SubscriptionStatus.ACTIVE,
                **extra,
            )  # fmt: skip
            for n, (item_key, values) in enumerate(lines):
                values = dict(values)
                uses = values.pop("uses", [])
                if item_key == "HOST":
                    uses.append(self.vendor_subs["SERVER"])
                if item_key == "DOMAIN" and identifier:
                    quantity = values.get("quantity", D(1))
                    uses.append(
                        vendor_sub(
                            f"DOMAIN-{identifier}",
                            "NAMEKEEPER",
                            f"{identifier} registration",
                            str(D("12.50") * quantity),
                            12,
                            "4020",
                            service_identifier=identifier,
                            next_due_date=anniversary(start),
                        )
                    )
                    self.s.flush()
                line = SubscriptionLine(
                    sort_order=n, catalog_item_id=items[item_key].id,
                    description=values.pop("description", items[item_key].name), **values,
                )  # fmt: skip
                line.uses = [SubscriptionUse(vendor_subscription_id=vs.id) for vs in uses]
                subscription.lines.append(line)
            self.s.add(subscription)

        none: dict[str, Any] = {}
        sub(
            "HILLTOP",
            420,
            "hilltopdental.example",
            [("HOST", none), ("DOMAIN", none), ("SSL", {"price_override": D("59.00")})],
        )
        sub("HILLTOP", 300, None, [("BACKUP", none)])
        sub("RIVERBEND", 380, "riverbenddiner.example", [("HOST", {"price_override": D("199.00")})])
        sub(
            "STMARKS",
            352,
            "stmarks.example",
            [("HOST", {"discount_pct": D("25")}), ("DOMAIN", none)],
        )
        sub("NLPHOTO", 330, "northernlights.example", [("HOST", none), ("DOMAIN", none)])
        sub(
            "LAKESHORE",
            345,
            "lakeshorerealty.example",
            [("DOMAIN", {"quantity": D("3"), "description": "Domain registrations (.com), 3"})],
            notes="Three domains, renewed together",
        )
        sub("PINECREST", 200, None, [("CARE", none), ("BACKUP", {"price_override": D("29.00")})])
        sub("CYSL", 100, "cysl.example", [("DOMAIN", none)])
        cancelled = Subscription(
            organization_id=org.id, party_id=self.parties["MARTINFARM"].id,
            service_identifier="martinfarm.example", billing_interval_months=12,
            start_date=self.start - timedelta(days=400), next_bill_date=None,
            end_date=self.start + timedelta(days=30), status=SubscriptionStatus.CANCELLED,
            auto_renew=False, notes="Moved to a free site builder",
        )  # fmt: skip
        old_line = SubscriptionLine(catalog_item_id=items["OLDHOST"].id,
                                    description=items["OLDHOST"].name)  # fmt: skip
        old_line.uses = [SubscriptionUse(vendor_subscription_id=self.vendor_subs["OLDPLAN"].id)]
        cancelled.lines = [old_line]
        self.s.add(cancelled)
        self.s.flush()

    # -- invoices, in date order ------------------------------------------------------------------

    def line(self, item: str, qty: str = "1", **extra: Any) -> LineIn:
        return LineIn(catalog_item_id=self.items[item].id, quantity=D(qty), **extra)

    def invoice(
        self, key: str, days_ago: int, lines: list[LineIn], *, issue: bool = True, **header: Any
    ) -> Invoice:
        day = self.today - timedelta(days=days_ago)
        invoice = invoice_service.create_invoice(
            self.s, self.org, self.parties[key], {"issue_date": day, **header}, lines
        )
        if issue:
            invoice_service.issue(self.s, self.org, invoice, day)
        return invoice

    def invoices(self) -> list[Invoice]:
        """Create every invoice in date order, so numbers follow dates as in real books: the
        subscription billing run on the first of each month, one-off jobs, and special cases.
        Returns the invoices whose payments `pay` makes up."""
        made: list[Invoice] = []
        events: list[tuple[date, int, Callable[[], None]]] = []

        def bill(month: date) -> None:
            for invoice in subscriptions.run_billing(self.s, self.org, month).invoices:
                invoice_service.issue(self.s, self.org, invoice, month)
                made.append(invoice)

        month = date(self.start.year, self.start.month, 1)
        while month <= self.today:
            events.append((month, 0, partial(bill, month)))
            month = (month + timedelta(days=32)).replace(day=1)

        def job(key: str, days: int, lines: Callable[[], list[LineIn]], header: Any) -> None:
            made.append(self.invoice(key, days, lines(), **header))

        for days, key, lines, header in self.one_off_jobs():
            day = self.today - timedelta(days=days)
            events.append((day, 1, partial(job, key, days, lines, header)))
        for days, step in self.special_cases(made):
            events.append((self.today - timedelta(days=days), 1, step))
        for _, _, event in sorted(events, key=lambda e: (e[0], e[1])):
            event()
        self.s.flush()
        return made

    def one_off_jobs(self) -> list[tuple[int, str, Callable[[], list[LineIn]], dict[str, Any]]]:
        rng = self.rng
        clients = ["HILLTOP", "STMARKS", "NLPHOTO", "KEYSTONE", "LAKESHORE", "GLROBOT",
                   "MARTINFARM", "CYSL", "PINECREST", "RIVERBEND"]  # fmt: skip
        kinds: list[Callable[[], list[LineIn]]] = [
            lambda: [self.line("CONSULT", rng.choice(["1", "1.5", "2", "3", "4.5"]))],
            lambda: [self.line("ONSITE", rng.choice(["1", "2", "2.5", "3"]))],
            lambda: [self.line("ROUTER"), self.line("CABLE", str(rng.randint(2, 6))),
                     self.line("ONSITE", "1.5")],
            lambda: [self.line("SWITCH"), self.line("CABLE", str(rng.randint(4, 10))),
                     self.line("ONSITE", "2")],
            lambda: [self.line("OFFICE", str(rng.randint(1, 5))), self.line("CONSULT", "1")],
        ]  # fmt: skip
        jobs: list[tuple[int, str, Callable[[], list[LineIn]], dict[str, Any]]] = [
            (rng.randint(3, MONTHS_OF_HISTORY * 30 - 20), rng.choice(clients), rng.choice(kinds),
             {})
            for _ in range(24)
        ]  # fmt: skip
        jobs.append((210, "LAKESHORE", lambda: [self.line("WEBSITE"), self.line("CONSULT", "3")],
                     {"notes": "New website for the Dunkirk office"}))  # fmt: skip
        jobs.append((75, "GLROBOT", lambda: [self.line("CONSULT", "12", description=(
            "Network design review for the Hamilton plant"))], {"terms_days": 45}))  # fmt: skip
        return jobs

    def special_cases(self, made: list[Invoice]) -> list[tuple[int, Callable[[], None]]]:
        """Scripted stories, as (days ago, step); later steps use invoices from earlier ones."""
        s, org = self.s, self.org
        kept: dict[str, Invoice] = {}

        def create(
            name: str, key: str, days: int, lines: list[LineIn], paid_later: bool, **header: Any
        ) -> Callable[[], None]:
            def step() -> None:
                invoice = self.invoice(key, days, lines, **header)
                kept[name] = invoice
                if paid_later:
                    made.append(invoice)
                else:
                    self.special.add(invoice.id)

            return step  # fmt: skip

        def revise() -> None:  # the client wanted their PO number on the invoice
            invoice_service.revise(
                s, org, kept["revised"], {"notes": "PO 4471"}, [self.line("CONSULT", "2.5")],
                reason="Client asked for their PO number; half an hour was missing",
                user_id=self.owner.id if self.owner else None,
            )  # fmt: skip

        def credit() -> None:  # returned hardware
            note = invoice_service.create_credit_note(
                s, org, kept["returned"], [LineIn(description="Returned: 8-port network switch",
                                                  quantity=D(1), unit_price=D("79.00"))],
                "Returned item",
            )  # fmt: skip
            invoice_service.issue(s, org, note, self.today - timedelta(days=120))

        def void() -> None:
            invoice_service.void(s, kept["duplicate"], "Entered twice by mistake")

        def partial_payment() -> None:
            payments.receive_payment(
                s, org, self.parties["RIVERBEND"], received_date=self.today - timedelta(days=260),
                amount=D("150.00"), method=PaymentMethod.CASH, channel=PaymentChannel.IN_PERSON,
                reference=None, notes="Partial payment", auto_allocate=False,
                allocations=[payments.Allocation(kept["lost"].id, D("150.00"))],
            )  # fmt: skip

        def write_off() -> None:  # the diner closed for good
            invoice_service.write_off(s, org, kept["lost"], "Diner closed; owner unreachable",
                                      self.today - timedelta(days=45))  # fmt: skip

        def overpay() -> None:  # the extra stays as credit on the account
            payments.receive_payment(
                s, org, self.parties["NLPHOTO"], received_date=self.today - timedelta(days=33),
                amount=D("150.00"), method=PaymentMethod.CHECK, channel=PaymentChannel.MAIL,
                reference="2231", notes="Paid more than the invoice; leave as credit",
                auto_allocate=False,
                allocations=[payments.Allocation(kept["over"].id, D("95.00"))],
            )  # fmt: skip

        return [
            (95, create("revised", "HILLTOP", 95, [self.line("CONSULT", "2")], True)),
            (90, revise),
            (130, create("returned", "KEYSTONE", 130,
                         [self.line("SWITCH", "2"), self.line("CABLE", "8")], True)),
            (120, credit),
            (60, create("duplicate", "CYSL", 60, [self.line("CONSULT", "1")], False)),
            (59, void),
            (300, create("lost", "RIVERBEND", 300,
                         [self.line("ROUTER"), self.line("ONSITE", "3")], False)),
            (260, partial_payment),
            (45, write_off),
            (40, create("over", "NLPHOTO", 40, [self.line("CONSULT", "1")], False)),
            (33, overpay),
            (2, create("draft", "LAKESHORE", 2, [self.line("WEBSITE"), self.line("CONSULT", "4")],
                       False, issue=False, notes="Phase 2: listings page")),
        ]  # fmt: skip

    # -- payments and deposits --------------------------------------------------------------------

    def pay(self, invoices: list[Invoice]) -> None:
        rng, s, org = self.rng, self.s, self.org
        infos = invoice_service.balances(s, invoices, self.today)
        for invoice in sorted(invoices, key=lambda i: (i.issue_date or self.today, i.id)):
            if invoice.id in self.special or invoice.kind != InvoiceKind.INVOICE:
                continue
            if invoice.status != InvoiceStatus.ISSUED:
                continue
            due = infos[invoice.id].balance_due
            if due <= 0:
                continue
            assert invoice.issue_date is not None
            age = (self.today - invoice.issue_date).days
            party_key = next(k for k, p in self.parties.items() if p.id == invoice.party_id)
            chance = 0.97 if age > 60 else 0.6 if age > 20 else 0.25
            if party_key == "RIVERBEND":
                chance -= 0.35
            if rng.random() > chance:
                continue  # still open (overdue if old)
            amount = due if rng.random() > 0.06 else (due / 2).quantize(D("0.01"))
            received = invoice.issue_date + timedelta(days=rng.randint(4, 38))
            received = min(received, self.today - timedelta(days=1))
            method = rng.choice([PaymentMethod.CHECK, PaymentMethod.CHECK, PaymentMethod.CARD,
                                 PaymentMethod.BANK_TRANSFER, PaymentMethod.PAYPAL])  # fmt: skip
            if party_key == "STMARKS":
                method = PaymentMethod.CHECK
            payments.receive_payment(
                s, org, self.parties[party_key], received_date=received, amount=amount,
                method=method,
                channel=PaymentChannel.MAIL if method == PaymentMethod.CHECK
                else PaymentChannel.ELECTRONIC,
                reference=str(rng.randint(1000, 9999)) if method == PaymentMethod.CHECK else None,
                notes=None, auto_allocate=False,
                allocations=[payments.Allocation(invoice.id, amount)],
            )  # fmt: skip
        s.flush()

    def deposits(self) -> None:
        """Payments go to the bank weekly (on Fridays); the last few days' are still waiting."""
        pending = self.s.scalars(
            select(Payment).where(
                Payment.organization_id == self.org.id, Payment.deposit_id.is_(None)
            )
        ).all()
        weeks: dict[date, list[Payment]] = defaultdict(list)
        for payment in pending:
            assert payment.received_date is not None
            friday = payment.received_date + timedelta(
                days=(4 - payment.received_date.weekday()) % 7
            )
            if friday < self.today - timedelta(days=3):
                weeks[friday].append(payment)
        for i, (friday, group) in enumerate(sorted(weeks.items())):
            items = []
            if i == 3:
                items = [payments.ExtraItem(D("12.50"), "Refund from NameKeeper Domains")]
            deposit = payments.create_deposit(
                self.s, self.org, deposit_date=friday, bank_party_id=self.parties["BANK"].id,
                notes=None, payment_ids=[p.id for p in group], items=items,
            )  # fmt: skip
            deposit.bank_account_id = self.checking.id
            banking.sync_deposit(self.s, deposit)
        self.s.flush()

    # -- expenses ---------------------------------------------------------------------------------

    def expense(
        self,
        day: date,
        vendor: str | None,
        lines: list[tuple[str, str, str | None]],
        reference: str | None = None,
        description: str | None = None,
        for_party: str | None = None,
        receipt: bool = False,
        subscription: str | None = None,
        paid_from: BankAccount | None = None,
    ) -> None:
        expense = Expense(
            organization_id=self.org.id, expense_date=day, entered_date=day + timedelta(days=1),
            vendor_party_id=self.parties[vendor].id if vendor else None,
            for_party_id=(self.parties[for_party] if for_party else self.parties["SELF"]).id,
            reference=reference, description=description,
            vendor_subscription_id=self.vendor_subs[subscription].id if subscription else None,
            paid_from_account_id=paid_from.id if paid_from else None,
        )  # fmt: skip
        expense.lines = [
            ExpenseLine(account_id=self.accounts[code].id, amount=D(amount), description=text,
                        sort_order=n)
            for n, (code, amount, text) in enumerate(lines)
        ]  # fmt: skip
        if receipt:
            total = sum(D(a) for _, a, _ in lines)
            pdf = _pdf(f"Receipt {reference or ''}".strip(),
                       [self.parties[vendor].name if vendor else "", f"Date: {day}",
                        f"Total: ${total:,.2f}"])  # fmt: skip
            stored = store_file(self.s, self.org.id, pdf, f"receipt-{day}.pdf", "application/pdf")
            expense.attachments = [ExpenseAttachment(file_id=stored.id)]
        self.s.add(expense)
        if paid_from is not None:
            self.s.flush()
            banking.sync_expense(self.s, expense)

    def expenses(self) -> None:
        rng = self.rng
        month = date(self.start.year, self.start.month, 1)
        n = 0
        while month <= self.today:

            def on(day: int, _month: date = month) -> date:
                return _month.replace(day=day)

            if on(5) <= self.today:
                self.expense(
                    on(5),
                    "VALLEYFIBER",
                    [("6100", "89.99", None)],
                    reference=f"VF-{on(5):%Y%m}",
                    description="Business fiber, monthly",
                    subscription="FIBER",
                    paid_from=self.card,
                )
            if on(10) <= self.today:
                self.expense(
                    on(10),
                    "CLOUDPEAK",
                    [("4010", "120.00", "Reseller server")],
                    reference=f"CP-{40000 + n}",
                    description="Hosting platform",
                    subscription="SERVER",
                    paid_from=self.card,
                )
                self.expense(
                    on(10),
                    None,
                    [("6300", "29.99", "Office 365"), ("6300", "12.00", "Password manager")],
                    description="Software subscriptions",
                    paid_from=self.card,
                )
            if on(28) <= self.today:
                self.expense(
                    on(28), "BANK", [("6500", "12.00", None)], description="Monthly account fee",
                    paid_from=self.checking,
                )  # fmt: skip
            if month.month in (1, 4, 7, 10) and on(15) <= self.today:
                self.expense(
                    on(15),
                    "PAPERTRAIL",
                    [("6200", f"{rng.randint(40, 160)}.{rng.randint(0, 99):02d}", None)],
                    reference=f"PT-{rng.randint(10000, 99999)}",
                    description="Paper, toner, labels",
                    paid_from=self.card,
                )
            if rng.random() < 0.6 and on(20) <= self.today:
                self.expense(
                    on(20),
                    "ALLEGHENY",
                    [
                        ("4030", f"{rng.randint(150, 650)}.00", "Routers, switches, cable"),
                        ("6400", "18.40", "Shipping"),
                    ],
                    reference=f"AC-{rng.randint(2000, 9999)}",
                    receipt=True,
                    description="Hardware restock",
                    paid_from=self.checking,
                )
            if rng.random() < 0.35 and on(22) <= self.today:
                self.expense(
                    on(22),
                    "NAMEKEEPER",
                    [("4020", f"{12.5 * rng.randint(1, 4):.2f}", None)],
                    description="Domain renewals",
                    paid_from=self.card,
                )
            n += 1
            month = (month + timedelta(days=32)).replace(day=1)
        # Mileage for an on-site visit, billable to the client.
        self.expense(self.today - timedelta(days=18), None,
                     [("6400", "42.10", "Mileage, 62 miles")], for_party="PINECREST",
                     description="Server room visit")  # fmt: skip
        self.s.flush()

    # -- banking ----------------------------------------------------------------------------------

    def bank_accounts(self) -> None:
        opened = date(self.start.year, self.start.month, 1) - timedelta(days=1)
        common = {"organization_id": self.org.id, "party_id": self.parties["BANK"].id,
                  "opening_date": opened}  # fmt: skip
        self.checking = BankAccount(name="Operating checking", kind=BankAccountKind.CHECKING,
                                    number_last4="4821", opening_balance=D("8250.00"),
                                    **common)  # fmt: skip
        self.card = BankAccount(name="Business card", kind=BankAccountKind.CREDIT_CARD,
                                number_last4="1006", opening_balance=D("0"),
                                notes="Monthly bills are charged here; paid from checking on "
                                "the 25th", **common)  # fmt: skip
        self.s.add_all([self.checking, self.card])
        self.s.flush()

    def _owed_before(self, day: date) -> Decimal:
        total = self.s.scalar(
            select(func.coalesce(func.sum(BankEntry.amount), 0)).where(
                BankEntry.bank_account_id == self.card.id, BankEntry.entry_date < day
            )
        )
        return -(self.card.opening_balance + Decimal(total or 0))

    def card_payments_and_statements(self) -> None:
        """The card is paid in full from checking on the 25th; statements are reconciled at
        each month end, checking one statement behind (so the to-do list asks for it)."""
        month = date(self.start.year, self.start.month, 1)
        while month <= self.today:
            day = month.replace(day=25)
            owed = self._owed_before(day)
            if day <= self.today and owed > 0:
                banking.transfer(self.s, self.org, self.checking, self.card, entry_date=day,
                                 amount=owed, description="Card payment",
                                 reference=None)  # fmt: skip
            month = (month + timedelta(days=32)).replace(day=1)
        self.s.flush()

        def month_ends(through: date) -> list[date]:
            ends, first = [], date(self.start.year, self.start.month, 1)
            while (
                end := (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            ) <= through:
                ends.append(end)
                first = end + timedelta(days=1)
            return ends

        last_month_end = date(self.today.year, self.today.month, 1) - timedelta(days=1)
        one_before = last_month_end.replace(day=1) - timedelta(days=1)
        for account, through in ((self.card, last_month_end), (self.checking, one_before)):
            for month_end in month_ends(through):
                lines = self.s.scalars(
                    select(BankEntry).where(
                        BankEntry.bank_account_id == account.id,
                        BankEntry.entry_date <= month_end,
                        BankEntry.status != BankEntryStatus.RECONCILED,
                    )
                ).all()
                statement = banking.balances(self.s, [account])[account.id].reconciled + sum(
                    (e.amount for e in lines), Decimal(0)
                )
                banking.reconcile(self.s, account, statement_date=month_end,
                                  statement_balance=statement, entry_ids=[e.id for e in lines],
                                  user_id=None)  # fmt: skip
        # What the bank has seen since: everything but the last few days.
        for entry in self.s.scalars(
            select(BankEntry).where(
                BankEntry.status == BankEntryStatus.UNCLEARED,
                BankEntry.entry_date <= self.today - timedelta(days=4),
            )
        ):
            entry.status = BankEntryStatus.CLEARED
        self.s.flush()

    # -- assets -----------------------------------------------------------------------------------

    def assets(self) -> None:
        """The business's own equipment and licenses, and equipment it manages at two clients;
        one warranty ending soon and one support contract just ended, for the to-do list."""
        categories = {
            c.name: c.id
            for c in self.s.scalars(
                select(AssetCategory).where(AssetCategory.organization_id == self.org.id)
            )
        }
        hardware = self.s.scalars(
            select(Expense)
            .where(Expense.organization_id == self.org.id, Expense.reference.like("AC-%"))
            .order_by(Expense.expense_date)
        ).first()
        t = self.today
        rows: list[dict[str, Any]] = [
            dict(name="Office NAS", category="Storage", manufacturer="Synology", model="DS923+",
                 serial_number="2290QWR7731", location="Office, rack shelf",
                 purchase_date=t - timedelta(days=340), purchase_price=D("599.99"),
                 vendor="ALLEGHENY", expense=hardware, warranty_expires=t + timedelta(days=20),
                 attributes={"capacity": "4 x 4 TB, RAID 5", "ip_address": "10.0.0.20"},
                 notes="Nightly backups of the office laptops.", receipt=True),
            dict(name="Work laptop", category="Laptop", manufacturer="Lenovo",
                 model="ThinkPad T14 Gen 4", serial_number="PF4KX2M1", assigned_to="Owner",
                 purchase_date=t - timedelta(days=500), purchase_price=D("1349.00"),
                 vendor="ALLEGHENY", warranty_expires=t + timedelta(days=595),
                 attributes={"cpu": "Ryzen 7 PRO 7840U", "ram": "32 GB", "os": "Windows 11 Pro"}),
            dict(name="Spare laptop", category="Laptop", manufacturer="Dell", model="Latitude 5420",
                 serial_number="9QW3TK3", status=AssetStatus.IN_STOCK, location="Office closet",
                 attributes={"ram": "16 GB", "os": "Windows 11 Pro"}),
            dict(name="Office router", category="Network", manufacturer="Ubiquiti",
                 model="UniFi Dream Machine", serial_number="UDM-7A21C", location="Office",
                 attributes={"ip_address": "10.0.0.1", "mac_address": "74:ac:b9:12:7a:21"}),
            dict(name="Microsoft 365 Business", category="Software license",
                 manufacturer="Microsoft", vendor=None,
                 attributes={"seats": 3, "renewal_date": (t + timedelta(days=120)).isoformat()}),
            dict(name="Old desktop", category="Desktop", manufacturer="HP", model="ProDesk 400",
                 status=AssetStatus.DISPOSED, notes="Recycled; drive wiped and shredded."),
            dict(name="Firewall", category="Network", owner="PINECREST", manufacturer="Netgate",
                 model="4200", serial_number="NG4200-1187", location="Server room",
                 support_ends=t - timedelta(days=6),
                 attributes={"ip_address": "192.168.10.1"},
                 notes="Support renewal quoted; waiting for the client."),
            dict(name="File server", category="Server", owner="PINECREST", manufacturer="Dell",
                 model="PowerEdge T360", serial_number="7XK2PV4", location="Server room",
                 warranty_expires=t + timedelta(days=700),
                 attributes={"cpu": "Xeon E-2434", "ram": "64 GB", "os": "Windows Server 2025",
                             "ip_address": "192.168.10.5"}),
            dict(name="Front desk printer", category="Printer", owner="HILLTOP",
                 manufacturer="Brother", model="HL-L6210DW", serial_number="E78113K4N",
                 location="Front desk",
                 attributes={"ip_address": "192.168.1.40"}),
        ]  # fmt: skip
        for n, row in enumerate(rows, start=1):
            owner, vendor = row.pop("owner", "SELF"), row.pop("vendor", None)
            expense, receipt = row.pop("expense", None), row.pop("receipt", False)
            asset = Asset(
                organization_id=self.org.id,
                tag=f"A-{n:04d}",
                category_id=categories[row.pop("category")],
                owner_party_id=self.parties[owner].id,
                vendor_party_id=self.parties[vendor].id if vendor else None,
                expense_id=expense.id if expense else None,
                **row,
            )
            if receipt:
                pdf = _pdf("Receipt", [self.parties["ALLEGHENY"].name, row["name"],
                                       f"Total: ${row['purchase_price']:,.2f}"])  # fmt: skip
                stored = store_file(self.s, self.org.id, pdf, "nas-receipt.pdf", "application/pdf")
                asset.attachments = [AssetAttachment(file_id=stored.id)]
            self.s.add(asset)
        self.s.flush()
        # The next automatic tag follows the demo's own.
        for _ in rows:
            next_number(self.s, self.org.id, "asset")
        self.s.flush()

    # -- knowledge base ---------------------------------------------------------------------------

    def articles(self) -> None:
        """A small category tree and articles: internal notes, a how-to that can be sent to
        clients, and one about a client's network."""

        def folder(name: str, parent: KbCategory | None = None, order: int = 0) -> KbCategory:
            c = KbCategory(organization_id=self.org.id, name=name, sort_order=order,
                           parent_id=parent.id if parent else None)  # fmt: skip
            self.s.add(c)
            self.s.flush()
            return c

        clients = folder("Clients", order=10)
        pinecrest = folder(self.parties["PINECREST"].name, clients)
        howto = folder("How-to", order=20)
        servers = folder("Servers and network", order=30)
        policies = folder("Policies", order=40)
        user = self.owner.id if self.owner else None
        rows: list[dict[str, Any]] = [
            dict(title="Set up company email on your phone", category=howto,
                 tags="email,phone,outlook", status=ArticleStatus.PUBLISHED,
                 visibility=ArticleVisibility.SHAREABLE,
                 body="Works for iPhone and Android with the Outlook app.\n\n"
                 "## Steps\n\n1. Install **Microsoft Outlook** from the App Store or Google "
                 "Play.\n2. Open it and tap **Add account**.\n3. Enter your work email address "
                 "and password.\n4. Approve the sign-in in the Authenticator app.\n\n"
                 "## If it does not work\n\n- Check that the phone has the latest updates.\n"
                 "- Remove the account and add it again.\n- Call us at the number on your "
                 "invoice; we can see the sign-in attempts.\n"),
            dict(title="Office network", category=servers, tags="network,vpn,backup",
                 status=ArticleStatus.PUBLISHED, visibility=ArticleVisibility.INTERNAL,
                 body="| Device | Address | Notes |\n|---|---|---|\n"
                 "| Router (A-0004) | 10.0.0.1 | UniFi; admin in the password manager |\n"
                 "| NAS (A-0001) | 10.0.0.20 | Nightly backups at 2:00 |\n\n"
                 "VPN: WireGuard on the router, one profile per laptop.\n\n"
                 "```\nwg-quick up office\n```\n"),
            dict(title="Pinecrest: server room and firewall", category=pinecrest,
                 tags="firewall,network", status=ArticleStatus.PUBLISHED,
                 visibility=ArticleVisibility.INTERNAL, party="PINECREST",
                 body="The firewall (Netgate 4200) is at **192.168.10.1**; the file server at "
                 "192.168.10.5.\n\n> Support on the firewall has ended: the renewal is quoted "
                 "and waiting for the client.\n\nKeys to the server room: front office.\n"),
            dict(title="Password policy", category=policies, tags="security",
                 status=ArticleStatus.DRAFT, visibility=ArticleVisibility.SHAREABLE,
                 body="Draft. At least 14 characters, a password manager for everyone, and "
                 "multi-factor sign-in on email.\n"),
        ]  # fmt: skip
        diagram = store_file(self.s, self.org.id, _diagram(), "office-network.png", "image/png")
        rows[1]["body"] += f"\n![Office network](/api/files/{diagram.id})\n"
        for row in rows:
            party = row.pop("party", None)
            category = row.pop("category")
            a = KbArticle(organization_id=self.org.id, category_id=category.id, version=1,
                          party_id=self.parties[party].id if party else None,
                          created_by_user_id=user, updated_by_user_id=user, **row)  # fmt: skip
            if row["title"] == "Office network":
                a.attachments = [KbAttachment(file_id=diagram.id)]
            self.s.add(a)
            self.s.flush()
            knowledge.add_version(self.s, a, user)
        self.s.flush()

    # -- tax filing and archive -------------------------------------------------------------------

    def tax_filing(self) -> None:
        current_start, _ = tax_periods.period_containing(self.registration, self.today)
        start, end = tax_periods.period_containing(
            self.registration, current_start - timedelta(days=1)
        )
        filed_on = end + timedelta(days=18)
        if end < self.start or filed_on > self.today:
            return
        report = reports.sales_tax(self.s, self.org, start, end, TaxBasis.ACCRUAL)
        self.s.add(
            TaxFiling(
                organization_id=self.org.id, registration_id=self.registration.id,
                period_start=start, period_end=end, filed_on=filed_on,
                amount_paid=report.net_tax, reference="ST-102 / DEMO-CONF-0001",
                notes="Annual return filed online",
            )
        )  # fmt: skip
        self.s.flush()

    def emails(self) -> None:
        """The sender, an own receipt text, and the latest invoices and a receipt "sent" (logged
        only: the demo never mails anyone, whatever EMAIL_URL says)."""
        org = self.org
        org.email_from_address = "billing@mapleridge.example"
        org.email_from_name = "Maple Ridge Tech"
        self.s.add(
            EmailTemplate(
                organization_id=org.id, kind=EmailKind.RECEIPT,
                subject="Thank you for your payment",
                body="Hi {client_name},\n\nWe received your payment of {amount} on "
                "{payment_date}. Your receipt is attached.\n\nMaple Ridge Tech",
            )
        )  # fmt: skip
        self.s.flush()
        latest = self.s.scalars(
            select(Invoice)
            .where(
                Invoice.organization_id == org.id,
                Invoice.status == InvoiceStatus.ISSUED,
                Invoice.kind == InvoiceKind.INVOICE,
            )
            .order_by(Invoice.issue_date.desc(), Invoice.id.desc())
            .limit(3)
        ).all()
        payment = self.s.scalars(
            select(Payment).where(Payment.organization_id == org.id).order_by(Payment.id.desc())
        ).first()
        drafts = [emailing.compose(self.s, org, "invoice", i.id) for i in latest]
        if payment is not None:
            drafts.append(emailing.compose(self.s, org, "payment", payment.id))
        with use_backend(NoSendBackend()):
            for draft in drafts:
                if draft.to:
                    emailing.send(self.s, org, draft, self.owner.id if self.owner else None)

    def run(self) -> Summary:
        if self.s.scalars(select(Organization.id)).first() is not None:
            raise DemoError(
                "The database already has a business; load the demo into an empty database."
            )
        self.organization()
        self.tax_setup()
        self.contacts()
        self.bank_accounts()
        self.catalog()
        self.exemptions_and_documents()
        self.subs()
        self.pay(self.invoices())
        self.deposits()
        self.expenses()
        self.card_payments_and_statements()
        self.assets()
        self.articles()
        self.tax_filing()
        self.emails()
        # The oldest two months are archived, as a business would after closing its books.
        archive.archive_through(self.s, self.org.id, self.start + timedelta(days=60),
                                batch_id="demo")  # fmt: skip
        self.s.flush()
        self.s.expire_all()  # archiving is a bulk UPDATE; reload what the session holds
        counts = {
            "contacts": len(self.parties),
            "invoices": len(self.s.scalars(select(Invoice.id)).all()),
            "payments": len(self.s.scalars(select(Payment.id)).all()),
            "expenses": len(self.s.scalars(select(Expense.id)).all()),
            "bank lines": len(self.s.scalars(select(BankEntry.id)).all()),
            "assets": len(self.s.scalars(select(Asset.id)).all()),
            "articles": len(self.s.scalars(select(KbArticle.id)).all()),
        }
        return Summary(self.org, counts)


def load_demo(session: Session, today: date | None = None) -> Summary:
    """Load the demo business into an empty database (the caller commits)."""
    return DemoLoader(session, today).run()
