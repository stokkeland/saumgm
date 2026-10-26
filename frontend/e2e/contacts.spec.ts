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

test('find a contact and look at its details', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.getByRole('link', { name: 'Contacts' }).click()
  await page.getByPlaceholder('Name, code, number, email').fill('Seneca')
  await expect(page).toHaveURL(/q=Seneca/)
  await page.getByRole('cell', { name: /Seneca Advantage/ }).click()

  await expect(page.getByRole('heading', { name: /Seneca Advantage/ })).toBeVisible()
  await expect(page.getByText('Balance')).toBeVisible()
  await screenshot(page, 'contact-detail')

  await page.getByRole('tab', { name: 'Tax' }).click()
  await expect(page.getByRole('cell', { name: 'Native American' })).toBeVisible()
  await page.getByRole('tab', { name: 'Invoices' }).click()
  await expect(page.getByRole('cell', { name: '1366' })).toBeVisible()
  await screenshot(page, 'contact-invoices')
  expect(errors).toEqual([])
})

test('create and edit a contact', async ({ page }) => {
  const errors = watchErrors(page)
  const code = `E2E${Date.now() % 100000}`
  await login(page)
  await page.goto('/contacts')
  await page.getByRole('button', { name: 'New contact' }).click()
  await page.getByLabel('Short code').fill(code)
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(`${code} Testing LLC`)
  await page.getByLabel('Email').fill('test@example.com')
  await page.getByRole('button', { name: 'Create' }).click()

  await expect(page.getByRole('heading', { name: `${code} Testing LLC` })).toBeVisible()
  await page.getByRole('button', { name: 'Edit' }).click()
  await page.getByLabel('Phone').fill('555-0199')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('555-0199')).toBeVisible()

  await page.getByRole('button', { name: 'Add' }).first().click()
  await page.getByLabel('Address line 1').fill('1 Test Street')
  await page.getByLabel('City').fill('Olean')
  await page.getByLabel('State / province').fill('NY')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('1 Test Street')).toBeVisible()

  await page.getByRole('tab', { name: 'History' }).click()
  await expect(page.getByText('party address').first()).toBeVisible()
  await screenshot(page, 'contact-history')
  expect(errors).toEqual([])
})
