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
    """How tax and income are reported (separate settings for each)."""

    ACCRUAL = "accrual"  # by invoice date
    CASH = "cash"  # by payment date


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


class EmailKind(StrEnum):
    """What an email is about; each kind has its own template (Admin -> Email)."""

    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"
    RECEIPT = "receipt"
    REPORT = "report"
    TEST = "test"
    DIGEST = "digest"  # the reminders digest (`python -m saumgm notify`)


class EmailStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"


class AuditActor(StrEnum):
    USER = "user"
    SYSTEM = "system"


class BankAccountKind(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"  # the balance is what is owed (negative = owed)
    OTHER = "other"  # PayPal, a payment processor, cash


class BankEntryStatus(StrEnum):
    UNCLEARED = "uncleared"  # recorded here, not yet seen on the bank's side
    CLEARED = "cleared"  # seen at the bank
    RECONCILED = "reconciled"  # matched to a statement; locked


class BankEntryKind(StrEnum):
    """Where a register line comes from. Linked lines follow their deposit, expense or transfer."""

    MANUAL = "manual"  # a free entry: fees, interest, owner draws, odd items
    DEPOSIT = "deposit"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"  # brings the register in line with a statement


class AssetStatus(StrEnum):
    IN_USE = "in_use"
    IN_STOCK = "in_stock"
    IN_REPAIR = "in_repair"
    RETIRED = "retired"  # no longer used, still on hand
    DISPOSED = "disposed"  # sold, scrapped, returned


class AssetFieldType(StrEnum):
    """Types of a category's extra fields."""

    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOL = "bool"
