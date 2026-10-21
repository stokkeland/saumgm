import { expect, test } from '@playwright/test'

import { login, screenshot, watchErrors } from './support'

const PAGES = [
  ['/', 'dashboard'],
  ['/contacts', 'contacts'],
  ['/invoices', 'invoices'],
  ['/payments', 'payments'],
  ['/deposits', 'deposits'],
  ['/expenses', 'expenses'],
  ['/subscriptions', 'subscriptions'],
  ['/catalog', 'catalog'],
  ['/settings', 'settings'],
  ['/audit', 'audit'],
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
