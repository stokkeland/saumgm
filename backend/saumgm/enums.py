from enum import StrEnum


class PartyKind(StrEnum):
    COMPANY = "company"
    PERSON = "person"


class PartyRoleType(StrEnum):
    SELF = "self"
    CLIENT = "client"
    VENDOR = "vendor"
    FINANCIAL = "financial"
    TAX_AUTHORITY = "tax_authority"
    RESOURCE = "resource"


class AddressType(StrEnum):
    BILLING = "billing"
    SERVICE = "service"
    REMIT = "remit"
    PHYSICAL = "physical"
    OTHER = "other"


class ItemType(StrEnum):
    GOODS = "goods"
    SERVICE_HOURLY = "service_hourly"
    SERVICE_FIXED = "service_fixed"
    SUBSCRIPTION = "subscription"


class BillingTiming(StrEnum):
    ADVANCE = "advance"
    ARREARS = "arrears"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class AccountType(StrEnum):
    EXPENSE = "expense"
    COGS = "cogs"
    REVENUE = "revenue"


class JurisdictionLevel(StrEnum):
    COUNTRY = "country"
    STATE = "state"
    COUNTY = "county"
    CITY = "city"
    OTHER = "other"


class FilingFrequency(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class DocumentType(StrEnum):
    """Kinds of documents kept on file for a contact."""

    W9 = "w9"  # US taxpayer identification (needed for 1099s)
    W8 = "w8"  # foreign status (W-8BEN / W-8BEN-E)
    TAX_EXEMPTION = "tax_exemption"  # sales-tax exemption or resale certificate
    INSURANCE = "insurance"  # certificate of insurance
    CONTRACT = "contract"  # contract, agreement, NDA
    OTHER = "other"


class DocumentStatus(StrEnum):
    """Computed from the expiry date; never stored."""

    NO_EXPIRY = "no_expiry"
    VALID = "valid"
    EXPIRING = "expiring"  # within its reminder window
    EXPIRED = "expired"


class TaxBasis(StrEnum):
    ACCRUAL = "accrual"  # tax reported by invoice date
    CASH = "cash"  # tax reported by payment date


class InvoiceKind(StrEnum):
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    VOID = "void"


class PaymentStatus(StrEnum):
    """Computed from issued invoices, payments and credit notes; never stored."""

    DRAFT = "draft"
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERPAID = "overpaid"
    VOID = "void"
    CREDIT = "credit"  # an issued credit note
    WRITTEN_OFF = "written_off"  # uncollectible; balance given up


class PaymentMethod(StrEnum):
    CHECK = "check"
    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    PAYPAL = "paypal"
    MONEY_ORDER = "money_order"
    OTHER = "other"


class PaymentChannel(StrEnum):
    MAIL = "mail"
    IN_PERSON = "in_person"
    ELECTRONIC = "electronic"


class UserRoleType(StrEnum):
    OWNER = "owner"
    BOOKKEEPER = "bookkeeper"
    VIEWER = "viewer"


class IdentityProvider(StrEnum):
    LOCAL = "local"
    OIDC = "oidc"
    SAML = "saml"


class AuditActor(StrEnum):
    USER = "user"
    SYSTEM = "system"
