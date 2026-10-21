import { expect, test } from '@playwright/test'

import { login, screenshot, watchErrors } from './support'

test('an imported invoice shows its lines, totals and payments', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/invoices?view=all&archived=all&q=1364')
  await page.getByRole('cell', { name: '1364', exact: true }).click()
  await expect(page.getByRole('heading', { name: /Invoice 1364/ })).toBeVisible()
  await expect(page.getByText('Insurance Module Development')).toBeVisible()
  await expect(page.getByText('$8,088.63').first()).toBeVisible()
  await screenshot(page, 'invoice-1364')
  expect(errors).toEqual([])
})

test('create, issue and revise an invoice', async ({ page }) => {
  const errors = watchErrors(page)
  await login(page)
  await page.goto('/invoices')
  await screenshot(page, 'invoices-open')
  await page.getByRole('link', { name: 'New invoice' }).click()

  await page.getByRole('combobox', { name: 'Client' }).fill('Bethel')
  await page.getByRole('option', { name: /Bethel Lutheran Church/ }).click()
  await page.getByRole('combobox', { name: 'Catalog item' }).first().click()
  await page.getByRole('option', { name: /Domain Registration/ }).first().click()
  await page.getByRole('textbox', { name: 'Quantity' }).first().fill('2')
  await page.getByRole('button', { name: 'Add line' }).click()
  await page.getByRole('textbox', { name: 'Description' }).nth(1).fill('On-site setup')
  await page.getByRole('textbox', { name: 'Unit price' }).nth(1).fill('150')
  await expect(page.getByText('$190.00').first()).toBeVisible() // 2 x 20 + 150, live from the server
  await screenshot(page, 'invoice-editor')

  await page.getByRole('button', { name: 'Save & issue' }).click()
  await expect(page.getByRole('heading', { name: /Invoice \d+/ })).toBeVisible()
  await expect(page.getByText('Unpaid')).toBeVisible()

  await page.getByRole('button', { name: 'Revise' }).click()
  await page.getByRole('textbox', { name: 'Unit price' }).nth(1).fill('120')
  await page.getByLabel('Reason for this revision').fill('Agreed lower setup price')
  await page.getByRole('button', { name: 'Save revision' }).click()
  await expect(page.getByText('$160.00').first()).toBeVisible()
  await page.getByRole('tab', { name: /Revisions/ }).click()
  await expect(page.getByText('Agreed lower setup price')).toBeVisible()
  await page.getByRole('button', { name: 'Show earlier version' }).click()
  await expect(page.getByRole('dialog').getByText('$190.00')).toBeVisible()
  await screenshot(page, 'invoice-revision')
  expect(errors).toEqual([])
})
