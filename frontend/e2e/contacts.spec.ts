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
