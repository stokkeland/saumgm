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

import { isoInDays, login, screenshot, watchErrors } from './support'

test('record a W-9 and an expiring certificate on a contact', async ({ page }) => {
  const errors = watchErrors(page)
  const tag = `E2E ${Date.now() % 100000}`
  await login(page)
  await page.goto('/contacts?q=Seneca')
  await page.getByRole('cell', { name: /Seneca Advantage/ }).click()
  await page.getByRole('tab', { name: 'Documents' }).click()
  await expect(page).toHaveURL(/tab=documents/)

  // a W-9 with its PDF
  await page.getByRole('button', { name: 'Add document' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add document' })
  await dialog.getByLabel('Title').fill(`W-9 ${tag}`)
  await dialog.locator('input[type=file]').setInputFiles({
    name: 'w9-signed.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 e2e'),
  })
  await dialog.getByLabel('Signed / issued').fill(isoInDays(-3))
  await dialog.getByRole('button', { name: 'Save' }).click()
  const w9 = page.getByRole('link', { name: `W-9 ${tag}` })
  await expect(w9).toBeVisible()
  const file = await page.request.get((await w9.getAttribute('href'))!)
  expect(file.headers()['content-type']).toBe('application/pdf')

  // an insurance certificate on paper that expires in 10 days
  await page.getByRole('button', { name: 'Add document' }).click()
  await dialog.getByRole('combobox', { name: 'Type' }).click()
  await page.getByRole('option', { name: 'Certificate of insurance' }).click()
  await dialog.getByLabel('Title').fill(`COI ${tag}`)
  await dialog.getByLabel('Expires').fill(isoInDays(10))
  await dialog.getByRole('button', { name: 'Save' }).click()
  const row = page.getByRole('row', { name: new RegExp(`COI ${tag}`) })
  await expect(row.getByText('Expires in 10 days')).toBeVisible()
  await expect(row.getByText('No file (paper copy)')).toBeVisible()
  await screenshot(page, 'contact-documents')

  // the to-do list has it under Documents
  await page.getByRole('link', { name: 'To do' }).click()
  const item = page.getByRole('row', { name: new RegExp(`COI ${tag}`) })
  await expect(item).toBeVisible()
  await expect(item.getByText('expires soon')).toBeVisible()

  // from there to the contact's documents; archiving it (replaced) takes it off the list
  await item.getByRole('link').click()
  await expect(page).toHaveURL(/tab=documents/)
  await page.getByRole('button', { name: `Actions for COI ${tag}` }).click()
  await page.getByRole('menuitem', { name: 'Archive (replaced)' }).click()
  await expect(page.getByRole('row', { name: new RegExp(`COI ${tag}`) })).toBeHidden()
  await page.getByRole('link', { name: 'To do' }).click()
  await expect(page.getByRole('heading', { name: 'To do' })).toBeVisible()
  await expect(page.getByRole('row', { name: new RegExp(`COI ${tag}`) })).toBeHidden()
  expect(errors).toEqual([])
})
