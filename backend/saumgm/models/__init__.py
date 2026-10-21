"""ORM models. Every model module is imported here so Alembic autogenerate sees it."""

from saumgm.db import Base
from saumgm.models.accounts import Account
from saumgm.models.audit import AuditLog
from saumgm.models.catalog import CatalogItem, RevenueCategory
from saumgm.models.expenses import Expense, ExpenseAttachment, ExpenseLine
from saumgm.models.files import StoredFile
from saumgm.models.invoices import Invoice, InvoiceLine, InvoiceRevision, InvoiceTax
from saumgm.models.organization import NumberSequence, Organization, OrganizationAddress
from saumgm.models.parties import Party, PartyAddress, PartyContact, PartyRole
from saumgm.models.payments import Deposit, DepositItem, Payment, PaymentAllocation
from saumgm.models.subscriptions import Subscription
from saumgm.models.tax import (
    TaxabilityRule,
    TaxCategory,
    TaxExemption,
    TaxJurisdiction,
    TaxRate,
    TaxRegistration,
)
from saumgm.models.users import AuthSession, User, UserIdentity, UserRole

__all__ = [
    "Account",
    "AuditLog",
    "AuthSession",
    "Base",
    "CatalogItem",
    "Deposit",
    "DepositItem",
    "Expense",
    "ExpenseAttachment",
    "ExpenseLine",
    "Invoice",
    "InvoiceLine",
    "InvoiceRevision",
    "InvoiceTax",
    "NumberSequence",
    "Organization",
    "OrganizationAddress",
    "Party",
    "PartyAddress",
    "PartyContact",
    "PartyRole",
    "Payment",
    "PaymentAllocation",
    "RevenueCategory",
    "StoredFile",
    "Subscription",
    "TaxCategory",
    "TaxExemption",
    "TaxJurisdiction",
    "TaxRate",
    "TaxRegistration",
    "TaxabilityRule",
    "User",
    "UserIdentity",
    "UserRole",
]
