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

import { csrfHeader, isoInDays, login, screenshot, watchErrors } from './support'

test('a client asset with extra fields, a file, and its warranty on the to-do list', async ({ page }) => {
  test.setTimeout(60_000)
  const errors = watchErrors(page)
  await login(page)
  const headers = await csrfHeader(page)
  const name = `E2E switch ${Date.now() % 1000000}`
  const ip = `10.${Date.now() % 250}.8.7`
  let assetUrl = ''

  try {
    await page.getByRole('link', { name: 'Assets', exact: true }).click()
    await page.getByRole('link', { name: 'New asset' }).click()
    await expect(page.getByRole('heading', { name: 'New asset' })).toBeVisible()
    await page.getByRole('textbox', { name: 'Name' }).fill(name)
    await page.getByRole('combobox', { name: 'Category' }).click()
    await page.getByRole('option', { name: 'Network' }).click()
    await page.getByRole('textbox', { name: 'IP address' }).fill(ip)
    await page.getByRole('textbox', { name: 'Manufacturer' }).fill('Netgear')
    await page.getByRole('combobox', { name: 'Owner' }).fill('Seneca')
    await page.getByRole('option', { name: /Seneca Advantage/ }).click()
    await page.getByLabel('Warranty expires').fill(isoInDays(10))
    await page.getByRole('button', { name: 'Add asset' }).click()
    await expect(page).toHaveURL(/\/assets\/\d+$/)
    assetUrl = page.url()
    await expect(page.getByRole('heading', { name: new RegExp(`A-\\d+ ${name}`) })).toBeVisible()

    // a configuration backup
    await page.locator('input[type=file]').setInputFiles({ name: 'switch-config.txt', mimeType: 'text/plain', buffer: Buffer.from('hostname e2e') })
    await expect(page.getByRole('link', { name: 'switch-config.txt' })).toBeVisible()
    await screenshot(page, 'asset')

    // the extra field is searchable
    await page.getByRole('link', { name: 'Assets', exact: true }).click()
    await page.getByPlaceholder('Tag, name, serial, IP, person…').fill(ip)
    await expect(page).toHaveURL(/q=/)
    await expect(page.getByRole('row', { name: /E2E switch/ })).toHaveCount(1)
    await expect(page.getByRole('row', { name: new RegExp(name) })).toBeVisible()
    await screenshot(page, 'assets')

    // the client's Assets tab, and the warranty on the to-do list
    await page.goto('/contacts?q=Seneca')
    await page.getByRole('cell', { name: /Seneca Advantage/ }).click()
    await page.getByRole('tab', { name: 'Assets' }).click()
    await expect(page.getByRole('row', { name: new RegExp(name) })).toBeVisible()
    await page.getByRole('link', { name: 'To do' }).click()
    const row = page.getByRole('row', { name: new RegExp(name) })
    await expect(row.getByText('warranty ends')).toBeVisible()
  } finally {
    // disposed, so it leaves the e2e database's lists and to-do list alone
    if (assetUrl) {
      const id = assetUrl.split('/').pop()
      await page.request.patch(`/api/assets/${id}`, { headers, data: { status: 'disposed' } })
    }
  }
  expect(errors).toEqual([])
})
