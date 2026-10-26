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
a revision, a void, a write-off, deposits, expenses with receipts, subscriptions coming up for
renewal, a sales-tax filing, a tax-exempt client and documents that are about to expire.

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
from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.enums import (
    AccountType,
    AddressType,
    BillingTiming,
    DocumentType,
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
    CatalogItem,
    Expense,
    ExpenseAttachment,
    ExpenseLine,
    Invoice,
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
    TaxabilityRule,
    TaxCategory,
    TaxExemption,
    TaxFiling,
    TaxJurisdiction,
    TaxRate,
    TaxRegistration,
    User,
)
from saumgm.schemas.invoices import LineIn
from saumgm.seed import OrganizationSetup, create_organization
from saumgm.services import archive, payments, reports, subscriptions, tax_periods
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
        def sub(
            key: str, item: str, days_ago: int, identifier: str | None = None, **extra: Any
        ) -> None:
            it = self.items[item]
            start = self.today - timedelta(days=days_ago)
            self.s.add(
                Subscription(
                    organization_id=self.org.id, party_id=self.parties[key].id,
                    catalog_item_id=it.id, service_identifier=identifier,
                    billing_interval_months=it.billing_interval_months or 1,
                    start_date=start, next_bill_date=start, status=SubscriptionStatus.ACTIVE,
                    vendor_party_id=it.default_vendor_id, unit_cost=it.unit_cost, **extra,
                )
            )  # fmt: skip

        sub("HILLTOP", "HOST", 420, "hilltopdental.example")
        sub("HILLTOP", "DOMAIN", 420, "hilltopdental.example")
        sub("HILLTOP", "SSL", 340, "hilltopdental.example")
        sub("HILLTOP", "BACKUP", 300)
        sub("RIVERBEND", "HOST", 380, "riverbenddiner.example", price_override=D("199.00"))
        sub("STMARKS", "HOST", 352, "stmarks.example", discount_pct=D("25"))
        sub("STMARKS", "DOMAIN", 352, "stmarks.example")
        sub("NLPHOTO", "HOST", 330, "northernlights.example")
        sub("NLPHOTO", "DOMAIN", 330, "northernlights.example")
        sub(
            "LAKESHORE",
            "DOMAIN",
            345,
            "lakeshorerealty.example",
            quantity=D("3"),
            notes="Three domains, renewed together",
        )
        sub("PINECREST", "CARE", 200)
        sub("PINECREST", "BACKUP", 200)
        sub("CYSL", "DOMAIN", 100, "cysl.example")
        self.s.add(
            Subscription(
                organization_id=self.org.id, party_id=self.parties["MARTINFARM"].id,
                catalog_item_id=self.items["OLDHOST"].id, service_identifier="martinfarm.example",
                billing_interval_months=12, start_date=self.start - timedelta(days=400),
                next_bill_date=None, end_date=self.start + timedelta(days=30),
                status=SubscriptionStatus.CANCELLED, auto_renew=False,
                notes="Moved to a free site builder",
            )
        )  # fmt: skip
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
            payments.create_deposit(
                self.s, self.org, deposit_date=friday, bank_party_id=self.parties["BANK"].id,
                notes=None, payment_ids=[p.id for p in group], items=items,
            )  # fmt: skip
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
    ) -> None:
        expense = Expense(
            organization_id=self.org.id, expense_date=day, entered_date=day + timedelta(days=1),
            vendor_party_id=self.parties[vendor].id if vendor else None,
            for_party_id=(self.parties[for_party] if for_party else self.parties["SELF"]).id,
            reference=reference, description=description,
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
                )
            if on(10) <= self.today:
                self.expense(
                    on(10),
                    "CLOUDPEAK",
                    [("4010", "120.00", "Reseller server")],
                    reference=f"CP-{40000 + n}",
                    description="Hosting platform",
                )
                self.expense(
                    on(10),
                    None,
                    [("6300", "29.99", "Office 365"), ("6300", "12.00", "Password manager")],
                    description="Software subscriptions",
                )
            if on(28) <= self.today:
                self.expense(
                    on(28), "BANK", [("6500", "12.00", None)], description="Monthly account fee"
                )
            if month.month in (1, 4, 7, 10) and on(15) <= self.today:
                self.expense(
                    on(15),
                    "PAPERTRAIL",
                    [("6200", f"{rng.randint(40, 160)}.{rng.randint(0, 99):02d}", None)],
                    reference=f"PT-{rng.randint(10000, 99999)}",
                    description="Paper, toner, labels",
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
                )
            if rng.random() < 0.35 and on(22) <= self.today:
                self.expense(
                    on(22),
                    "NAMEKEEPER",
                    [("4020", f"{12.5 * rng.randint(1, 4):.2f}", None)],
                    description="Domain renewals",
                )
            n += 1
            month = (month + timedelta(days=32)).replace(day=1)
        # Mileage for an on-site visit, billable to the client.
        self.expense(self.today - timedelta(days=18), None,
                     [("6400", "42.10", "Mileage, 62 miles")], for_party="PINECREST",
                     description="Server room visit")  # fmt: skip
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

    def run(self) -> Summary:
        if self.s.scalars(select(Organization.id)).first() is not None:
            raise DemoError(
                "The database already has a business; load the demo into an empty database."
            )
        self.organization()
        self.tax_setup()
        self.contacts()
        self.catalog()
        self.exemptions_and_documents()
        self.subs()
        self.pay(self.invoices())
        self.deposits()
        self.expenses()
        self.tax_filing()
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
        }
        return Summary(self.org, counts)


def load_demo(session: Session, today: date | None = None) -> Summary:
    """Load the demo business into an empty database (the caller commits)."""
    return DemoLoader(session, today).run()
