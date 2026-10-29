/*
 * SauMGM - Sauen Management System: billing, sales tax and bookkeeping for small businesses
 * Copyright (C) 2026 J. Thomas Stokkeland - https://www.saumgm.com/
 *
 * This program is free software: you can redistribute it and/or modify it under the terms of the
 * GNU General Public License as published by the Free Software Foundation, either version 3 of
 * the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
 * without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 * See the GNU General Public License for more details. You should have received a copy of the
 * GNU General Public License along with this program (the LICENSE file); if not, see
 * <https://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

/** Human-readable labels for API values. */

export const ROLE_LABELS: Record<string, string> = {
  client: 'Client',
  vendor: 'Vendor',
  financial: 'Bank / financial',
  tax_authority: 'Tax authority',
  resource: 'Resource',
  self: 'This business',
}

export const ROLE_COLORS: Record<string, string> = {
  client: 'blue',
  vendor: 'orange',
  financial: 'teal',
  tax_authority: 'red',
  resource: 'gray',
  self: 'violet',
}

export const ADDRESS_TYPES = [
  { value: 'billing', label: 'Billing' },
  { value: 'service', label: 'Service / ship-to' },
  { value: 'remit', label: 'Remit-to' },
  { value: 'physical', label: 'Physical' },
  { value: 'other', label: 'Other' },
]

export const PAYMENT_METHODS = [
  { value: 'check', label: 'Check' },
  { value: 'cash', label: 'Cash' },
  { value: 'card', label: 'Card' },
  { value: 'bank_transfer', label: 'Bank transfer' },
  { value: 'paypal', label: 'PayPal' },
  { value: 'money_order', label: 'Money order' },
  { value: 'other', label: 'Other' },
]

export const PAYMENT_CHANNELS = [
  { value: 'mail', label: 'Mail' },
  { value: 'in_person', label: 'In person' },
  { value: 'electronic', label: 'Electronic' },
]

export const ITEM_TYPES = [
  { value: 'goods', label: 'Goods' },
  { value: 'service_hourly', label: 'Service (hourly)' },
  { value: 'service_fixed', label: 'Service (fixed)' },
  { value: 'subscription', label: 'Subscription' },
]

export const SUBSCRIPTION_STATUSES = [
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'cancelled', label: 'Cancelled' },
]

export const SUBSCRIPTION_STATUS_COLORS: Record<string, string> = {
  active: 'green',
  paused: 'yellow',
  cancelled: 'gray',
}

/** "every month", "every year", "every 3 months" */
export function everyMonths(months: number) {
  if (months === 1) return 'monthly'
  if (months === 12) return 'yearly'
  return `every ${months} mo.`
}

export function labelOf(options: { value: string; label: string }[], value: string | null | undefined) {
  return options.find((o) => o.value === value)?.label ?? value ?? ''
}

export const DOCUMENT_TYPES = [
  { value: 'w9', label: 'W-9' },
  { value: 'w8', label: 'W-8 (foreign)' },
  { value: 'tax_exemption', label: 'Tax exemption certificate' },
  { value: 'insurance', label: 'Certificate of insurance' },
  { value: 'contract', label: 'Contract / agreement' },
  { value: 'other', label: 'Other' },
]
