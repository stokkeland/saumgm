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

// Run the API with EMAIL_URL=console:// (the default) and EMAIL_REDIRECT_TO set: the imported
// data holds real client addresses, and nothing may reach them.
import { expect, test } from '@playwright/test'

import { login, screenshot, watchErrors } from './support'

test('set the sender, send a test and an invoice, find them in the log', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/admin/email')
  await expect(page.getByText('EMAIL_REDIRECT_TO on the server')).toBeVisible()
  await page.getByRole('textbox', { name: 'From address' }).fill('billing@e2e.example')
  // A new name each run, so the form always has a change to save.
  const name = `E2E Billing ${Date.now() % 100000}`
  await page.getByRole('textbox', { name: 'From name' }).fill(name)
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText(`${name} <billing@e2e.example>`)).toBeVisible()
  await page.getByRole('button', { name: 'Send test' }).click()
  await expect(page.getByText(/Test message sent to/)).toBeVisible()
  await screenshot(page, 'admin-email')

  await page.goto('/invoices?view=all&archived=all&q=1364')
  await page.getByRole('cell', { name: '1364', exact: true }).click()
  await page.getByRole('button', { name: 'Email' }).click()
  const dialog = page.getByRole('dialog', { name: 'Send by email' })
  await expect(dialog.getByRole('textbox', { name: 'Subject' })).toHaveValue(/Invoice 1364 from /)
  await expect(dialog.getByText('invoice-1364.pdf')).toBeVisible()
  await expect(dialog.getByText(/sends every message to/)).toBeVisible()
  await dialog.getByRole('textbox', { name: 'Message' }).fill('Hello,\n\nYour invoice is attached.')
  await screenshot(page, 'invoice-email-dialog')
  await dialog.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByText(/\(redirected\)/)).toBeVisible()

  await page.getByRole('tab', { name: 'History' }).click()
  await expect(page.getByText('email', { exact: true }).first()).toBeVisible()

  await page.goto('/admin/email?tab=log')
  await expect(page.getByRole('cell', { name: /Invoice 1364 from/ }).first()).toBeVisible()
  await screenshot(page, 'admin-email-log')
  expect(errors).toEqual([])
})

test('a report goes out by email with its PDF', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/reports?tab=pl&from=2008-01-01&to=2008-12-31')
  await page.getByText('By payment date', { exact: true }).click()
  await expect(page).toHaveURL(/income=cash/)
  await page.getByRole('button', { name: 'Email' }).click()
  const dialog = page.getByRole('dialog', { name: 'Send by email' })
  await expect(dialog.getByRole('textbox', { name: 'Subject' })).toHaveValue(/^Profit & loss, Jan 1, 2008/)
  await expect(dialog.getByText('profit-loss-cash-2008-01-01-2008-12-31.pdf')).toBeVisible()
  await screenshot(page, 'report-email-dialog')
  await dialog.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByText(/\(redirected\)/)).toBeVisible()
  expect(errors).toEqual([])
})
