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

test('set up NY sales tax and see it on a new invoice', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/admin/settings?tab=tax')

  // Register in New York (once; the test database keeps it between runs)
  const registered = page.getByRole('cell', { name: 'New York', exact: true }).first()
  if (!(await registered.isVisible())) {
    await page.getByRole('combobox', { name: 'Jurisdiction', exact: true }).first().click()
    await page.getByRole('option', { name: 'US-NY — New York' }).click()
    await page.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(registered).toBeVisible()
  }

  // A 4% state rate, and hosting not taxable in NY
  const stateRate = page.getByRole('cell', { name: '4%' }).first()
  if (!(await stateRate.isVisible())) {
    await page.getByLabel('Rate %').fill('4')
    await page.getByRole('button', { name: 'Add rate' }).click()
    await expect(stateRate).toBeVisible()
  }
  const hosting = page.getByRole('row', { name: /Hosting and digital services/ })
  await hosting.getByText('Not taxable').click()
  await screenshot(page, 'settings-tax')

  // An invoice for a client in NY: goods taxed, hosting not
  await page.goto('/invoices/new')
  await page.getByRole('combobox', { name: 'Client' }).fill('Bethel')
  await page.getByRole('option', { name: /Bethel Lutheran Church/ }).click()
  await page.getByRole('textbox', { name: 'Description' }).first().fill('Network switch')
  await page.getByRole('textbox', { name: 'Unit price' }).first().fill('100')
  await page.getByRole('button', { name: 'Add line' }).click()
  await page.getByRole('textbox', { name: 'Description' }).nth(1).fill('Hosting')
  await page.getByRole('textbox', { name: 'Unit price' }).nth(1).fill('50')
  await page.getByRole('combobox', { name: 'Tax category' }).nth(1).click()
  await page.getByRole('option', { name: 'Hosting and digital services' }).click()
  await expect(page.getByText(/New York 4%/)).toBeVisible()
  await expect(page.getByText('$154.00')).toBeVisible() // 150 + 4% of 100
  await screenshot(page, 'invoice-with-tax')
  expect(errors).toEqual([])
})

test('subscriptions and the billing run', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/subscriptions')
  await page.getByRole('button', { name: 'New subscription' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('combobox', { name: 'Client' }).fill('Bethel')
  await page.getByRole('option', { name: /Bethel Lutheran Church/ }).click()
  const domain = `e2e-${Date.now()}.example`
  await dialog.getByRole('combobox', { name: 'Item, line 1' }).click()
  await page.getByRole('option', { name: 'Domain Registration', exact: true }).click()
  await expect(dialog.getByRole('textbox', { name: 'Description, line 1' })).toHaveValue('Domain Registration')
  await dialog.getByRole('button', { name: 'Add line' }).click()
  await dialog.getByRole('combobox', { name: 'Item, line 2' }).click()
  await page.getByRole('option', { name: 'Domain Registration', exact: true }).click()
  await dialog.getByRole('textbox', { name: 'Description, line 2' }).fill('Second domain')
  await dialog.getByRole('textbox', { name: 'Price, line 2' }).fill('5')
  await dialog.getByLabel('For (domain, account, server…)').fill(domain)
  await screenshot(page, 'subscription-form')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).toBeHidden()
  await page.getByPlaceholder('Domain, account, item…').fill(domain)
  await expect(page).toHaveURL(/q=e2e-/)
  await expect(page.getByRole('cell', { name: 'Domain Registration, Second domain' })).toHaveCount(1)

  await page.getByRole('button', { name: 'Bill subscriptions' }).click()
  await page.getByRole('button', { name: 'Preview' }).click()
  const preview = page.getByRole('dialog')
  await expect(preview.getByRole('cell', { name: 'Bethel Lutheran Church' }).first()).toBeVisible()
  await expect(preview.getByText(new RegExp(`Second domain - ${domain.replace('.', '\\.')}`))).toBeVisible()
  await screenshot(page, 'billing-run')
  await page.getByRole('button', { name: 'Create draft invoices' }).click()
  await expect(page).toHaveURL(/view=draft/)
  await expect(page.getByRole('cell', { name: 'Bethel Lutheran Church' }).first()).toBeVisible()
  expect(errors).toEqual([])
})

test('dashboard and audit log', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await expect(page.getByText('Owed to you')).toBeVisible()
  await screenshot(page, 'dashboard')
  await page.getByRole('link', { name: 'Audit log' }).click()
  await expect(page.getByRole('cell', { name: 'E2E Tester' }).first()).toBeVisible()
  await screenshot(page, 'audit')
  expect(errors).toEqual([])
})
