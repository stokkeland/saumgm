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

import { e2eVendor, login, screenshot, watchErrors } from './support'

test('a vendor subscription is paid, and a client subscription uses it', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await e2eVendor(page)
  const server = `vps-${Date.now()}`

  await page.goto('/vendor-subscriptions')
  await page.getByRole('button', { name: 'New vendor subscription' }).click()
  let dialog = page.getByRole('dialog')
  await dialog.getByRole('combobox', { name: 'Vendor' }).fill('E2E Hosting')
  await page.getByRole('option', { name: /E2E Hosting Vendor/ }).click()
  await dialog.getByRole('textbox', { name: 'Name' }).fill(server)
  await dialog.getByRole('textbox', { name: 'Amount' }).fill('30')
  await dialog.getByRole('textbox', { name: 'Every (months)' }).fill('1')
  await dialog.getByLabel('Next due').fill('2026-11-15')
  await dialog.getByRole('combobox', { name: 'Expense account' }).click()
  await page.getByRole('option').first().click()
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).toBeHidden()

  await page.getByPlaceholder('Name, server, domain…').fill(server)
  const row = page.getByRole('row', { name: new RegExp(server) })
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: 'Paid…' }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('textbox', { name: 'Amount' })).toHaveValue('30')
  await dialog.getByRole('textbox', { name: 'Reference' }).fill('E2E-1')
  await dialog.getByRole('button', { name: 'Record payment' }).click()
  await expect(dialog).toBeHidden()
  await expect(row.getByRole('cell', { name: /Dec 15, 2026|12\/15\/2026|2026-12-15/ })).toBeVisible()
  await screenshot(page, 'vendor-subscriptions')

  // A client subscription line that uses it shows the cost behind it.
  await page.goto('/subscriptions')
  await page.getByRole('button', { name: 'New subscription' }).click()
  dialog = page.getByRole('dialog')
  await dialog.getByRole('combobox', { name: 'Client' }).fill('Bethel')
  await page.getByRole('option', { name: /Bethel Lutheran Church/ }).click()
  await dialog.getByRole('combobox', { name: 'Item, line 1' }).click()
  await page.getByRole('option', { name: 'Domain Registration', exact: true }).click()
  await dialog.getByRole('combobox', { name: 'Uses, line 1' }).fill(server)
  await page.getByRole('option', { name: new RegExp(server) }).click()
  await dialog.getByLabel('For (domain, account, server…)').fill(`${server}.example`)
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).toBeHidden()

  await page.goto('/vendor-subscriptions')
  await page.getByPlaceholder('Name, server, domain…').fill(server)
  await page.getByRole('row', { name: new RegExp(server) }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog.getByText(`${server}.example`, { exact: false })).toBeVisible()
  await expect(dialog.getByText(/1 payment\(s\) recorded/)).toBeVisible()
  expect(errors).toEqual([])
})

test('a package fills a new subscription', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  const name = `E2E package ${Date.now()}`
  await page.goto('/catalog?tab=packages')
  await page.getByRole('button', { name: 'New package' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: 'Name' }).fill(name)
  await dialog.getByRole('combobox', { name: 'Item 1' }).click()
  await page.getByRole('option', { name: 'Domain Registration', exact: true }).click()
  await dialog.getByRole('combobox', { name: 'Item 2' }).click()
  await page.getByRole('option', { name: 'Domain Registration', exact: true }).click()
  await dialog.getByRole('textbox', { name: 'Price 2' }).fill('1')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('cell', { name }).first()).toBeVisible()

  await page.goto('/subscriptions')
  await page.getByRole('button', { name: 'New subscription' }).click()
  await page.getByRole('dialog').getByRole('combobox', { name: 'Add a package' }).click()
  await page.getByRole('option', { name }).click()
  const form = page.getByRole('dialog')
  await expect(form.getByRole('combobox', { name: 'Item, line 2' })).toHaveValue('Domain Registration')
  await expect(form.getByRole('textbox', { name: 'Price, line 2' })).toHaveValue('1')
  await expect(form.getByRole('combobox', { name: 'Item, line 3' })).toBeHidden()
  expect(errors).toEqual([])
})
