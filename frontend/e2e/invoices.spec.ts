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

test('an imported invoice shows its lines, totals and payments', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/invoices?view=all&archived=all&q=1364')
  await page.getByRole('cell', { name: '1364', exact: true }).click()
  await expect(page.getByRole('heading', { name: /Invoice 1364/ })).toBeVisible()
  await expect(page.getByText('Insurance Module Development')).toBeVisible()
  await expect(page.getByText('$8,088.63').first()).toBeVisible()
  await screenshot(page, 'invoice-1364')
  expect(errors).toEqual([])
})

test('create, issue and revise an invoice', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/invoices')
  await screenshot(page, 'invoices-open')
  await page.getByRole('link', { name: 'New invoice' }).click()

  await page.getByRole('combobox', { name: 'Client' }).fill('Petrela')
  await page.getByRole('option', { name: /Petrela Westmount/ }).click()
  await page.getByRole('combobox', { name: 'Catalog item' }).first().click()
  await page.getByRole('option', { name: /Domain Registration/ }).first().click()
  await page.getByRole('textbox', { name: 'Quantity' }).first().fill('2')
  await page.getByRole('button', { name: 'Add line' }).click()
  await page.getByRole('textbox', { name: 'Description' }).nth(1).fill('On-site setup')
  await page.getByRole('textbox', { name: 'Unit price' }).nth(1).fill('150')
  await expect(page.getByText('$190.00').first()).toBeVisible() // 2 x 20 + 150, live from the server
  await screenshot(page, 'invoice-editor')

  await page.getByRole('button', { name: 'Save & issue' }).click()
  await expect(page.getByRole('heading', { name: /Invoice \d+/ })).toBeVisible()
  await expect(page.getByText('Unpaid')).toBeVisible()

  await page.getByRole('button', { name: 'Revise' }).click()
  await page.getByRole('textbox', { name: 'Unit price' }).nth(1).fill('120')
  await page.getByLabel('Reason for this revision').fill('Agreed lower setup price')
  await page.getByRole('button', { name: 'Save revision' }).click()
  await expect(page.getByText('$160.00').first()).toBeVisible()
  await page.getByRole('tab', { name: /Revisions/ }).click()
  await expect(page.getByText('Agreed lower setup price')).toBeVisible()
  await page.getByRole('button', { name: 'Show earlier version' }).click()
  await expect(page.getByRole('dialog').getByText('$190.00')).toBeVisible()
  await screenshot(page, 'invoice-revision')
  expect(errors).toEqual([])
})
