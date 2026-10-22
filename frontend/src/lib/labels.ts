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

export function labelOf(options: { value: string; label: string }[], value: string | null | undefined) {
  return options.find((o) => o.value === value)?.label ?? value ?? ''
}
