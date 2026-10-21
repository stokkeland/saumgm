"""Reference data every new organization starts with."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from saumgm.enums import JurisdictionLevel
from saumgm.models import (
    NumberSequence,
    Organization,
    TaxabilityRule,
    TaxCategory,
    TaxJurisdiction,
)

COUNTRIES = {"US": "United States", "CA": "Canada"}

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico",
}  # fmt: skip

CA_PROVINCES = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador", "NS": "Nova Scotia", "NT": "Northwest Territories",
    "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island", "QC": "Quebec",
    "SK": "Saskatchewan", "YT": "Yukon",
}  # fmt: skip

REGIONS = {"US": US_STATES, "CA": CA_PROVINCES}

# Starting taxability classes; which are taxable where is configured per jurisdiction.
TAX_CATEGORIES = [
    ("goods", "Tangible goods", "Hardware, parts, physical products."),
    ("software", "Prewritten software", "Off-the-shelf software and licenses."),
    ("digital", "Hosting and digital services", "Web hosting, domains, certificates, SaaS."),
    ("services", "Labor and professional services", "Consulting, development, repair labor."),
    ("exempt", "Non-taxable", "Never taxed."),
]


@dataclass
class OrganizationSetup:
    legal_name: str
    display_name: str
    country_code: str = "US"
    currency_code: str = "USD"
    locale: str = "en-US"
    timezone: str = "America/New_York"
    payable_to: str | None = None
    tagline: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    default_terms_days: int = 30
    invoice_number_next: int = 1
    invoice_number_prefix: str = ""
    party_number_next: int = 1
    party_number_pad: int = 8


def jurisdiction_code(country: str, region: str | None = None) -> str:
    return f"{country}-{region}" if region else country


def create_organization(session: Session, setup: OrganizationSetup) -> Organization:
    """Create an organization with its number sequences, jurisdictions and tax categories."""
    org = Organization(
        legal_name=setup.legal_name,
        display_name=setup.display_name,
        payable_to=setup.payable_to,
        tagline=setup.tagline,
        phone=setup.phone,
        email=setup.email,
        website=setup.website,
        country_code=setup.country_code,
        currency_code=setup.currency_code,
        locale=setup.locale,
        timezone=setup.timezone,
        default_terms_days=setup.default_terms_days,
    )
    session.add(org)
    session.flush()

    session.add_all(
        [
            NumberSequence(
                organization_id=org.id,
                name="invoice",
                next_value=setup.invoice_number_next,
                prefix=setup.invoice_number_prefix,
                pad_width=0,
            ),
            NumberSequence(
                organization_id=org.id,
                name="party",
                next_value=setup.party_number_next,
                prefix="",
                pad_width=setup.party_number_pad,
            ),
        ]
    )

    countries: dict[str, TaxJurisdiction] = {}
    for country, country_name in COUNTRIES.items():
        parent = TaxJurisdiction(
            organization_id=org.id,
            level=JurisdictionLevel.COUNTRY,
            code=jurisdiction_code(country),
            name=country_name,
        )
        session.add(parent)
        session.flush()
        countries[country] = parent
        session.add_all(
            TaxJurisdiction(
                organization_id=org.id,
                parent_id=parent.id,
                level=JurisdictionLevel.STATE,
                code=jurisdiction_code(country, region),
                name=region_name,
            )
            for region, region_name in REGIONS[country].items()
        )

    categories = {
        code: TaxCategory(organization_id=org.id, code=code, name=name, description=description)
        for code, name, description in TAX_CATEGORIES
    }
    session.add_all(categories.values())
    session.flush()

    # "Non-taxable" is never taxed: a rule at each country level, inherited by everything below.
    for country in COUNTRIES:
        session.add(
            TaxabilityRule(
                jurisdiction_id=countries[country].id,
                tax_category_id=categories["exempt"].id,
                is_taxable=False,
            )
        )
    session.flush()
    return org
