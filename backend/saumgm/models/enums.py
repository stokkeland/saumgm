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
