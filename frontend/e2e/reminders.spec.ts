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

import { expect, test } from '@playwright/test'

import { csrfHeader, e2eVendor, isoInDays, login, screenshot, watchErrors } from './support'

test('the to-do list shows a vendor payment due, and the lead time decides how early', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  const vendorId = await e2eVendor(page)
  const headers = await csrfHeader(page)
  const name = `E2E phone ${Date.now()}`
  const created = await page.request.post('/api/vendor-subscriptions', {
    headers,
    data: { party_id: vendorId, name, amount: '25', interval_months: 1, next_due_date: isoInDays(3), autopay: true },
  })
  expect(created.status()).toBe(201)
  const sub = await created.json()

  try {
    await page.getByRole('link', { name: 'To do' }).click()
    const row = page.getByRole('row', { name: new RegExp(name) })
    await expect(row).toBeVisible()
    await expect(row.getByText('autopay: will be charged, check the account')).toBeVisible()
    await screenshot(page, 'todo')

    // the dashboard has the same list, shortened
    await page.getByRole('link', { name: 'Dashboard' }).click()
    await expect(page.getByRole('heading', { name: 'To do' })).toBeVisible()

    // Admin -> Reminders: the digest preview lists it; with one day of lead time it is not due yet
    await page.getByRole('link', { name: 'Reminders' }).click()
    await expect(page.getByText(new RegExp(`E2E Hosting Vendor: ${name}`))).toBeVisible()
    await screenshot(page, 'admin-reminders')
    await page.getByRole('textbox', { name: 'Pay vendors' }).fill('1')
    await page.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByText(new RegExp(`E2E Hosting Vendor: ${name}`))).toBeHidden()
    await page.getByRole('link', { name: 'To do' }).click()
    await expect(page.getByRole('heading', { name: 'To do' })).toBeVisible()
    await expect(page.getByRole('row', { name: new RegExp(name) })).toBeHidden()
  } finally {
    await page.request.patch('/api/reminders/settings', { headers, data: { pay_days: 10 } })
    await page.request.patch(`/api/vendor-subscriptions/${sub.id}`, { headers, data: { status: 'cancelled' } })
  }
  expect(errors).toEqual([])
})

test('the billing run opens from a link with its date', async ({ page }) => {
  await login(page)
  await page.goto('/subscriptions?bill=2026-12-31')
  const dialog = page.getByRole('dialog', { name: 'Bill subscriptions' })
  await expect(dialog.getByLabel('Bill everything due through')).toHaveValue('2026-12-31')
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(page).not.toHaveURL(/bill=/)
})
