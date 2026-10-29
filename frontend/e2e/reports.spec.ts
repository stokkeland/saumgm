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

import { login, screenshot, watchErrors } from './support'

// A 1x1 transparent PNG
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
)

test('invoice PDF opens from the invoice page', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/invoices?view=paid')
  await page.getByRole('row').nth(1).click()
  await expect(page.getByRole('heading', { name: /Invoice \d+/ })).toBeVisible()

  const pdf = page.getByRole('link', { name: 'PDF', exact: true })
  const response = await page.request.get((await pdf.getAttribute('href'))!)
  expect(response.status()).toBe(200)
  expect(response.headers()['content-type']).toBe('application/pdf')
  expect((await response.body()).subarray(0, 5).toString()).toBe('%PDF-')
  expect(errors).toEqual([])
})

test('reports show sales, sales tax, profit and aging with CSV downloads', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/reports?from=2008-01-01&to=2008-12-31')
  await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible()
  await expect(page.getByRole('cell', { name: '2008-02' })).toBeVisible()
  await screenshot(page, 'reports-sales')

  await page.getByRole('tab', { name: 'Sales tax' }).click()
  await expect(page.getByText('Net tax due')).toBeVisible()
  await page.getByText('By payment date', { exact: true }).click()
  await expect(page).toHaveURL(/basis=cash/)
  await screenshot(page, 'reports-sales-tax')

  const csv = page.getByRole('link', { name: 'Download CSV' })
  const download = await page.request.get((await csv.getAttribute('href'))!)
  expect(download.headers()['content-type']).toContain('text/csv')
  expect(await download.text()).toContain('Net tax')

  await page.getByRole('tab', { name: 'Profit & loss' }).click()
  await expect(page.getByText('Net profit')).toBeVisible()

  await page.getByRole('tab', { name: 'Receivables aging' }).click()
  await expect(page.getByRole('columnheader', { name: 'Over 90' })).toBeVisible()
  await screenshot(page, 'reports-aging')

  await page.getByRole('tab', { name: 'Expenses' }).click()
  await page.getByRole('combobox', { name: 'Period' }).click()
  await page.getByRole('option', { name: 'Last year' }).click()
  await expect(page).toHaveURL(/from=\d{4}-01-01&to=\d{4}-12-31/)
  expect(errors).toEqual([])
})

test('logo can be uploaded and removed', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/admin/settings?tab=business')
  const card = page.locator('.mantine-Card-root').filter({ hasText: 'Logo' }).first()
  if (await card.getByRole('button', { name: 'Remove' }).isVisible()) {
    await card.getByRole('button', { name: 'Remove' }).click()
    await expect(card.getByText('No logo')).toBeVisible()
  }
  await card.locator('input[type=file]').setInputFiles({ name: 'logo.png', mimeType: 'image/png', buffer: PNG })
  await expect(card.getByRole('img', { name: 'Business logo' })).toBeVisible()
  await card.getByRole('button', { name: 'Remove' }).click()
  await expect(card.getByText('No logo')).toBeVisible()
  expect(errors).toEqual([])
})
