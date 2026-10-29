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

import { expect, type Page, test } from '@playwright/test'

import { login, screenshot, watchErrors } from './support'

async function issueOldInvoice(page: Page, amount: string): Promise<string> {
  await page.goto('/invoices/new')
  await page.getByRole('combobox', { name: 'Client' }).fill('Petrela')
  await page.getByRole('option', { name: /Petrela Westmount/ }).click()
  await page.getByLabel('Invoice date').fill('2020-01-15')
  await page.getByRole('textbox', { name: 'Description' }).first().fill('Never paid')
  await page.getByRole('textbox', { name: 'Unit price' }).first().fill(amount)
  await expect(page.getByText(`$${amount}.00`).first()).toBeVisible()
  await page.getByRole('button', { name: 'Save & issue' }).click()
  const heading = page.getByRole('heading', { name: /Invoice \d+/ })
  await expect(heading).toBeVisible()
  return (await heading.textContent())!.match(/Invoice (\d+)/)![1]
}

test('write off an uncollectible invoice and find it again', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  const number = await issueOldInvoice(page, '333')
  await expect(page.getByText('Overdue')).toBeVisible()

  await page.getByRole('button', { name: 'More actions' }).click()
  await page.getByRole('menuitem', { name: 'Write off as uncollectible…' }).click()
  await page.getByLabel('Reason').fill('Client stopped answering; gave up collecting')
  await page.getByRole('button', { name: 'Write off', exact: true }).click()
  await expect(page.getByText('Written off as uncollectible')).toBeVisible()
  await expect(page.getByText('Client stopped answering')).toBeVisible()
  await screenshot(page, 'invoice-written-off')

  await page.goto('/invoices?view=written_off')
  await expect(page.getByRole('cell', { name: number, exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('write off several invoices from the list', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  const number = await issueOldInvoice(page, '44')
  await page.goto(`/invoices?view=overdue&q=${number}`)
  const row = page.getByRole('row', { name: new RegExp(`\\b${number}\\b`) })
  await row.getByRole('checkbox', { name: 'Select row' }).check()
  await page.getByRole('button', { name: /Write off 1 selected/ }).click()
  await page.getByLabel('Reason').fill('Bad debt clean-up')
  await page.getByRole('button', { name: 'Write off', exact: true }).click()
  await expect(page.getByText(/1 invoice\(s\) written off/)).toBeVisible()
  await expect(page.getByRole('cell', { name: number, exact: true })).toBeHidden()
  expect(errors).toEqual([])
})

test('sales-tax periods can be marked filed', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/admin/settings?tab=tax')
  await page.getByRole('button', { name: 'Periods' }).first().click()
  await page.getByRole('combobox', { name: 'Year', exact: true }).click()
  await page.getByRole('option', { name: '2025' }).click()
  const firstPeriod = page.getByRole('row').filter({ hasText: /Not filed|Filed/ }).first()
  if (await firstPeriod.getByRole('button', { name: 'Unmark' }).isVisible()) {
    await firstPeriod.getByRole('button', { name: 'Unmark' }).click()
  }
  await firstPeriod.getByRole('button', { name: 'Mark filed' }).click()
  await page.getByLabel('Confirmation / reference').fill('E2E-CONF')
  await page.getByRole('dialog').getByRole('button', { name: 'Mark filed' }).click()
  await expect(firstPeriod.getByText(/Filed .* E2E-CONF/)).toBeVisible()
  await screenshot(page, 'tax-periods')
  expect(errors).toEqual([])
})
