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

const PAGES = [
  ['/', 'dashboard'],
  ['/todo', 'todo-page'],
  ['/contacts', 'contacts'],
  ['/invoices', 'invoices'],
  ['/payments', 'payments'],
  ['/deposits', 'deposits'],
  ['/expenses', 'expenses'],
  ['/subscriptions', 'subscriptions'],
  ['/vendor-subscriptions', 'vendor-subscriptions'],
  ['/banking', 'banking'],
  ['/assets', 'assets-list'],
  ['/kb', 'knowledge-base-list'],
  ['/kb/categories', 'kb-categories'],
  ['/catalog', 'catalog'],
  ['/catalog?tab=packages', 'catalog-packages'],
  ['/reports', 'reports'],
  ['/admin/settings', 'settings'],
  ['/admin/users', 'users'],
  ['/admin/reminders', 'reminders'],
  ['/admin/asset-categories', 'asset-categories'],
  ['/admin/audit', 'audit'],
  ['/admin/about', 'about'],
  ['/account', 'account'],
] as const

test('redirects to the login page when signed out', async ({ page }) => {
  await page.goto('/invoices')
  await expect(page).toHaveURL(/\/login\?next=%2Finvoices/)
  await screenshot(page, 'login')
})

test('every page opens without errors', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  for (const [path, name] of PAGES) {
    await page.goto(path)
    await expect(page.locator('h2').first()).toBeVisible()
    await screenshot(page, name)
  }
  expect(errors).toEqual([])
})

test('addresses from 1.0 lead to their new place', async ({ page }) => {
  await login(page)
  await page.goto('/settings?tab=tax')
  await expect(page).toHaveURL(/\/admin\/settings\?tab=tax$/)
  await page.goto('/settings?tab=users')
  await expect(page).toHaveURL(/\/admin\/users$/)
  await page.goto('/audit')
  await expect(page).toHaveURL(/\/admin\/audit$/)
})

test('menu sections fold, except the one holding the open page', async ({ page }) => {
  await login(page)
  await page.goto('/')
  const nav = page.getByRole('navigation')
  await expect(nav.getByRole('link', { name: 'Deposits' })).toBeVisible()
  await nav.getByRole('button', { name: 'Money' }).click()
  await expect(nav.getByRole('link', { name: 'Deposits' })).toBeHidden()
  await page.reload()
  await expect(nav.getByRole('link', { name: 'Deposits' })).toBeHidden()
  await page.goto('/expenses')
  await expect(nav.getByRole('link', { name: 'Deposits' })).toBeVisible()
  await page.goto('/')
  await nav.getByRole('button', { name: 'Money' }).click()
  await expect(nav.getByRole('link', { name: 'Deposits' })).toBeVisible()
})
