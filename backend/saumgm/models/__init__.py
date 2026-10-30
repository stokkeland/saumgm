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

"""ORM models. Every model module is imported here so Alembic autogenerate sees it."""

from saumgm.db import Base
from saumgm.models.accounts import Account
from saumgm.models.assets import Asset, AssetAttachment, AssetCategory
from saumgm.models.audit import AuditLog
from saumgm.models.banking import BankAccount, BankEntry, BankReconciliation
from saumgm.models.catalog import CatalogItem, CatalogPackage, CatalogPackageItem, RevenueCategory
from saumgm.models.email import EmailMessage, EmailTemplate
from saumgm.models.expenses import Expense, ExpenseAttachment, ExpenseLine
from saumgm.models.files import StoredFile
from saumgm.models.invoices import Invoice, InvoiceLine, InvoiceRevision, InvoiceTax
from saumgm.models.knowledge import KbArticle, KbArticleVersion, KbAttachment, KbCategory
from saumgm.models.organization import NumberSequence, Organization, OrganizationAddress
from saumgm.models.parties import Party, PartyAddress, PartyContact, PartyRole
from saumgm.models.party_documents import PartyDocument
from saumgm.models.payments import Deposit, DepositItem, Payment, PaymentAllocation
from saumgm.models.subscriptions import (
    Subscription,
    SubscriptionLine,
    SubscriptionUse,
    VendorSubscription,
)
from saumgm.models.tax import (
    TaxabilityRule,
    TaxCategory,
    TaxExemption,
    TaxFiling,
    TaxJurisdiction,
    TaxRate,
    TaxRegistration,
)
from saumgm.models.users import AuthSession, User, UserIdentity, UserRole

__all__ = [
    "Account",
    "Asset",
    "AssetAttachment",
    "AssetCategory",
    "AuditLog",
    "AuthSession",
    "BankAccount",
    "BankEntry",
    "BankReconciliation",
    "Base",
    "CatalogItem",
    "CatalogPackage",
    "CatalogPackageItem",
    "Deposit",
    "DepositItem",
    "EmailMessage",
    "EmailTemplate",
    "Expense",
    "ExpenseAttachment",
    "ExpenseLine",
    "Invoice",
    "InvoiceLine",
    "InvoiceRevision",
    "InvoiceTax",
    "KbArticle",
    "KbArticleVersion",
    "KbAttachment",
    "KbCategory",
    "NumberSequence",
    "Organization",
    "OrganizationAddress",
    "Party",
    "PartyAddress",
    "PartyContact",
    "PartyDocument",
    "PartyRole",
    "Payment",
    "PaymentAllocation",
    "RevenueCategory",
    "StoredFile",
    "Subscription",
    "SubscriptionLine",
    "SubscriptionUse",
    "TaxCategory",
    "TaxExemption",
    "TaxFiling",
    "TaxJurisdiction",
    "TaxRate",
    "TaxRegistration",
    "TaxabilityRule",
    "User",
    "UserIdentity",
    "UserRole",
    "VendorSubscription",
]
