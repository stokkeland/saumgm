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

import { expect, type Page } from '@playwright/test'

export const SCREENS = process.env.E2E_SCREENS ?? '../tmp/screens'

export function credentials(): { email: string; password: string } {
  const email = process.env.E2E_EMAIL
  const password = process.env.E2E_PASSWORD
  if (!email || !password) throw new Error('Set E2E_EMAIL and E2E_PASSWORD')
  return { email, password }
}

/** Fail the test on any uncaught error in the page. */
export function watchErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (msg) => {
    // The 'am I signed in?' check answers 401 before login; that is expected.
    if (msg.type() === 'error' && !msg.text().includes('status of 401')) errors.push(msg.text())
  })
  return errors
}

export async function login(page: Page) {
  const { email, password } = credentials()
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByRole('textbox', { name: 'Password' }).fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
}

export async function screenshot(page: Page, name: string) {
  await page.waitForLoadState('networkidle')
  await page.screenshot({ path: `${SCREENS}/${name}.png`, fullPage: true })
}

/** A local date (like the business's own time zone; not UTC, which may already be tomorrow). */
export function isoInDays(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** The CSRF header for calling the API directly from a signed-in page. */
export async function csrfHeader(page: Page): Promise<Record<string, string>> {
  const csrf = (await page.context().cookies()).find((c) => c.name === 'saumgm_csrf')!.value
  return { 'X-CSRF-Token': csrf }
}

/** A vendor of our own, so tests do not depend on the imported vendors. Returns its id. */
export async function e2eVendor(page: Page): Promise<number> {
  const found = await page.request.get('/api/contacts?q=E2E%20Hosting%20Vendor&role=vendor')
  const page1 = await found.json()
  if (page1.total > 0) return page1.items[0].id
  const created = await page.request.post('/api/contacts', {
    headers: await csrfHeader(page),
    data: { short_code: 'E2EHOSTV', name: 'E2E Hosting Vendor', roles: ['vendor'] },
  })
  expect(created.status()).toBe(201)
  return (await created.json()).id
}
