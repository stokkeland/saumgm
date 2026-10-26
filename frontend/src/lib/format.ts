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

/** Number, money and date formatting in the organization's locale and currency. */

export interface Locale {
  locale: string
  currency: string
}

const moneyFormats = new Map<string, Intl.NumberFormat>()

/** Amounts arrive from the API as decimal strings ("1234.5000"). */
export function formatMoney(value: string | number | null | undefined, l: Locale): string {
  if (value === null || value === undefined || value === '') return ''
  const key = `${l.locale}|${l.currency}`
  let format = moneyFormats.get(key)
  if (!format) {
    format = new Intl.NumberFormat(l.locale, { style: 'currency', currency: l.currency })
    moneyFormats.set(key, format)
  }
  return format.format(Number(value))
}

/** Quantities and rates without trailing zeros: "1.5000" -> "1.5". */
export function formatNumber(value: string | number | null | undefined, locale: string): string {
  if (value === null || value === undefined || value === '') return ''
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(Number(value))
}

/** A tax rate stored as a fraction ("0.040000") shown as a percentage ("4%"). */
export function formatRate(value: string | null | undefined, locale: string): string {
  if (!value) return ''
  return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 4 }).format(
    Number(value),
  )
}

/** ISO dates ("2026-10-21") in the locale's short style, without time-zone shifts. */
export function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return ''
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(
    new Date(Date.UTC(year, month - 1, day)),
  )
}

/** Timestamps from the API are UTC without a zone marker. */
export function formatDateTime(value: string | null | undefined, locale: string): string {
  if (!value) return ''
  const iso = /[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  )
}

/** Today's date as YYYY-MM-DD in the browser's time zone. */
export function todayIso(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}
