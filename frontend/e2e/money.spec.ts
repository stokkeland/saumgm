import { expect, test } from '@playwright/test'

import { login, screenshot, watchErrors } from './support'

test('invoice -> payment -> deposit', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)

  // An invoice to pay
  await page.goto('/invoices/new')
  await page.getByRole('combobox', { name: 'Client' }).fill('Bethel')
  await page.getByRole('option', { name: /Bethel Lutheran Church/ }).click()
  await page.getByRole('textbox', { name: 'Description' }).first().fill('Support call')
  await page.getByRole('textbox', { name: 'Unit price' }).first().fill('75')
  await expect(page.getByText('$75.00').first()).toBeVisible()
  await page.getByRole('button', { name: 'Save & issue' }).click()
  const heading = page.getByRole('heading', { name: /Invoice \d+/ })
  await expect(heading).toBeVisible()
  const number = (await heading.textContent())!.match(/Invoice (\d+)/)![1]

  // Record payment from the invoice: amount and invoice are filled in
  await page.getByRole('link', { name: 'Record payment' }).click()
  await expect(page.getByRole('textbox', { name: 'Amount', exact: true })).toHaveValue('75')
  await expect(page.getByRole('textbox', { name: `Amount for invoice ${number}` })).toHaveValue('75')
  await page.getByLabel('Reference').fill('CHK-501')
  await screenshot(page, 'receive-payment')
  await page.getByRole('button', { name: 'Record payment' }).click()
  await expect(page.getByText(`Invoice ${number}`)).toBeVisible()
  await expect(page.getByText('Not deposited')).toBeVisible()

  await page.getByRole('link', { name: `Invoice ${number}` }).click()
  await expect(page.getByText('Paid', { exact: true }).first()).toBeVisible()

  // Deposit it
  await page.goto('/deposits/new')
  await page.getByRole('checkbox', { name: /Deposit payment from Bethel/ }).first().check()
  await screenshot(page, 'new-deposit')
  await page.getByRole('button', { name: 'Record deposit' }).click()
  await expect(page.getByRole('heading', { name: /Deposit/ })).toBeVisible()
  await expect(page.getByText('CHK-501')).toBeVisible()
  expect(errors).toEqual([])
})

test('enter an expense split over two accounts', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/expenses/new')
  await page.getByRole('combobox', { name: 'Vendor' }).fill('Amazon')
  await page.getByRole('option', { name: /Amazon/ }).first().click()
  await page.getByLabel('Description').fill('Cables and a router')
  await page.getByRole('combobox', { name: 'Account' }).first().click()
  await page.getByRole('option', { name: /Office Supplies/ }).click()
  await page.getByRole('textbox', { name: 'Amount' }).first().fill('12.50')
  await page.getByRole('button', { name: 'Add account' }).click()
  await page.getByRole('combobox', { name: 'Account' }).nth(1).click()
  await page.getByRole('option', { name: /Hardware for resale/ }).click()
  await page.getByRole('textbox', { name: 'Amount' }).nth(1).fill('89')
  await expect(page.getByText('$101.50')).toBeVisible()
  await screenshot(page, 'expense-editor')
  await page.getByRole('button', { name: 'Save expense' }).click()
  await expect(page.getByRole('heading', { name: /Expense \$101\.50/ })).toBeVisible()
  await expect(page.getByRole('main').getByText('Sauen.Com')).toBeVisible() // "for" defaults to the business
  expect(errors).toEqual([])
})
