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

test('a register: entry, card payment by transfer, reconciling with a statement', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  const headers = await csrfHeader(page)
  const tag = `${Date.now() % 1000000}`
  const checkingName = `E2E checking ${tag}`
  const cardName = `E2E card ${tag}`
  const card = await page.request.post('/api/bank-accounts', {
    headers,
    data: { name: cardName, kind: 'credit_card', opening_date: isoInDays(-40), opening_balance: '-100' },
  })
  expect(card.status()).toBe(201)
  const cardId: number = (await card.json()).id
  let checkingId = 0

  try {
    // a new account opens its (empty) register
    await page.getByRole('link', { name: 'Bank accounts' }).click()
    await page.getByRole('button', { name: 'New account' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('textbox', { name: 'Name' }).fill(checkingName)
    await dialog.getByLabel('Register starts on').fill(isoInDays(-40))
    await dialog.getByRole('textbox', { name: 'Opening balance' }).fill('1000')
    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByRole('heading', { name: checkingName })).toBeVisible()
    checkingId = Number(page.url().split('/').pop())

    // a bank fee
    await page.getByRole('button', { name: 'New entry' }).click()
    const entry = page.getByRole('dialog')
    await entry.getByRole('textbox', { name: 'Amount' }).fill('25')
    await entry.getByRole('textbox', { name: 'Payee' }).fill('E2E bank fee')
    await entry.getByLabel('Date').fill(isoInDays(-3))
    await entry.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByRole('row', { name: /E2E bank fee/ }).getByRole('cell', { name: '$975.00' })).toBeVisible()

    // paying the card is a transfer; the card's register gets the other side
    await page.getByRole('button', { name: 'Transfer' }).click()
    const transfer = page.getByRole('dialog')
    await transfer.getByRole('combobox', { name: 'To' }).click()
    await page.getByRole('option', { name: cardName }).click()
    await transfer.getByRole('button', { name: /Pay what is owed/ }).click()
    await transfer.getByRole('button', { name: 'Transfer' }).click()
    await expect(transfer).toBeHidden()
    await expect(page.getByRole('row', { name: new RegExp(`Transfer to ${cardName}`) })).toBeVisible()

    // the statement shows both lines and ends at 875
    await page.getByRole('button', { name: 'Reconcile' }).click()
    const rec = page.getByRole('dialog')
    await rec.getByLabel('Statement date').fill(isoInDays(0))
    await rec.getByRole('textbox', { name: 'Ending balance' }).fill('875')
    await rec.getByRole('checkbox', { name: /On the statement: E2E bank fee/ }).check()
    await expect(rec.getByText(/Difference:/)).not.toHaveText(/\$0\.00/)
    await rec.getByRole('checkbox', { name: new RegExp(`On the statement: Transfer to ${cardName}`) }).check()
    await expect(rec.getByText(/Difference:/)).toHaveText(/\$0\.00/)
    await screenshot(page, 'bank-reconcile')
    await rec.getByRole('button', { name: 'Reconcile', exact: true }).click()
    await expect(rec).toBeHidden()
    await expect(page.getByRole('row', { name: /E2E bank fee/ }).getByText('Reconciled')).toBeVisible()
    await screenshot(page, 'bank-register')

    await page.getByRole('link', { name: 'Bank accounts' }).click()
    const cardRow = page.getByRole('row', { name: new RegExp(cardName) })
    await expect(cardRow.getByText('$0.00').first()).toBeVisible()
    await screenshot(page, 'bank-accounts')
  } finally {
    // closed, so they leave the e2e database's lists and reminders alone
    for (const id of [checkingId, cardId]) {
      if (id) await page.request.patch(`/api/bank-accounts/${id}`, { headers, data: { is_active: false } })
    }
  }
  expect(errors).toEqual([])
})
