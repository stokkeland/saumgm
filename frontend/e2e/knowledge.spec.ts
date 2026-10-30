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

import { csrfHeader, login, screenshot, watchErrors } from './support'

// A 1x1 PNG.
const PIXEL = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
)

test('an article: write with preview, attach an image, find it, send it to a client', async ({ page }) => {
  test.setTimeout(90_000)
  const errors = watchErrors(page)
  await login(page)
  const headers = await csrfHeader(page)
  const n = Date.now() % 1000000
  const folder = `E2E folder ${n}`
  const title = `E2E printer setup ${n}`
  const word = `zebra${n}`
  let articleId = ''
  let categoryId = ''

  try {
    await page.getByRole('link', { name: 'Knowledge base', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Knowledge base' })).toBeVisible()

    // a category
    await page.getByRole('link', { name: 'Categories', exact: true }).click()
    await page.getByRole('button', { name: 'New category' }).click()
    await page.getByRole('textbox', { name: 'Name' }).fill(folder)
    const created = page.waitForResponse((r) => r.url().endsWith('/api/kb/categories') && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Save' }).click()
    categoryId = String((await (await created).json()).id)
    await expect(page.getByRole('cell', { name: folder })).toBeVisible()

    // write it, with the preview beside the text
    await page.goto('/kb/new')
    await expect(page.getByRole('heading', { name: 'New article' })).toBeVisible()
    await page.getByRole('textbox', { name: 'Title' }).fill(title)
    await page.getByRole('combobox', { name: 'Category' }).click()
    await page.getByRole('option', { name: folder }).click()
    await page.getByRole('combobox', { name: 'Tags' }).fill('printer,')
    await page.getByRole('combobox', { name: 'About a contact' }).fill('Seneca')
    await page.getByRole('option', { name: /Seneca Advantage/ }).click()
    const text = page.getByRole('textbox', { name: 'Text' })
    await text.fill(`Install the driver; the code word is ${word}.\n\n`)
    await page.getByRole('button', { name: 'Bold' }).click()
    await expect(page.getByLabel('Preview').locator('strong')).toHaveText('bold text')
    await page.getByText('Published', { exact: true }).click()
    await page.getByText('Shareable', { exact: true }).click()
    const saved = page.waitForResponse((r) => r.url().endsWith('/api/kb/articles') && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Save article' }).click()
    articleId = String((await (await saved).json()).id)
    await expect(page).toHaveURL(new RegExp(`/kb/${articleId}/edit$`))

    // an image, put into the text where the cursor is
    await page.locator('input[type=file]').setInputFiles({ name: 'tray.png', mimeType: 'image/png', buffer: PIXEL })
    await expect(page.getByRole('link', { name: 'tray.png' })).toBeVisible()
    // at the end: the cursor has not been put anywhere since the page opened
    await expect(text).toHaveValue(/\*\*bold text\*\*\n+!\[tray\.png\]\(\/api\/files\/\d+\)\n$/)
    await expect(page.getByLabel('Preview').locator('img[alt="tray.png"]')).toBeVisible()
    await screenshot(page, 'article-editor')
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`/kb/${articleId}$`))
    await expect(page.locator('img[alt="tray.png"]')).toBeVisible()
    await screenshot(page, 'article')
    await page.getByRole('tab', { name: /Versions/ }).click()
    await expect(page.getByRole('row', { name: /2 \(current\)/ })).toBeVisible()

    // found by a word of its text, with the matching part shown
    await page.goto('/kb')
    await page.getByPlaceholder('Search titles, tags and text…').fill(word)
    await expect(page).toHaveURL(/q=/)
    await expect(page.getByRole('link', { name: title })).toBeVisible()
    await expect(page.locator('mark', { hasText: word })).toBeVisible()
    await screenshot(page, 'knowledge-base')

    // the client's Articles tab
    await page.goto('/contacts?q=Seneca')
    await page.getByRole('cell', { name: /Seneca Advantage/ }).click()
    await page.getByRole('tab', { name: 'Articles' }).click()
    await page.getByRole('row', { name: new RegExp(title) }).click()

    // sent with a PDF copy (EMAIL_REDIRECT_TO keeps it away from the client)
    await page.getByRole('button', { name: 'Email to…' }).click()
    const dialog = page.getByRole('dialog', { name: 'Send by email' })
    await expect(dialog.getByRole('textbox', { name: 'Subject' })).toHaveValue(title)
    await expect(dialog.getByText('tray.png')).toBeVisible()
    await dialog.getByRole('checkbox', { name: 'Attach a PDF copy' }).check()
    await expect(dialog.getByText(/e2e-printer-setup-\d+\.pdf/)).toBeVisible()
    const sent = page.waitForResponse((r) => /\/api\/kb\/articles\/\d+\/email\?pdf=true$/.test(r.url()))
    await dialog.getByRole('button', { name: 'Send' }).click()
    expect((await sent).status()).toBe(200)
    await expect(page.getByText(/redirected/)).toBeVisible()
  } finally {
    if (articleId) await page.request.delete(`/api/kb/articles/${articleId}`, { headers })
    if (categoryId) await page.request.delete(`/api/kb/categories/${categoryId}`, { headers })
  }
  expect(errors).toEqual([])
})
