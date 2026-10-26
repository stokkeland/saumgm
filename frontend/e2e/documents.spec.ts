import { expect, test } from '@playwright/test'

import { login, screenshot, watchErrors } from './support'

/** A local date (like the business's own time zone; not UTC, which may already be tomorrow). */
function isoInDays(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

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

  // the dashboard lists it
  await page.getByRole('link', { name: 'Dashboard' }).click()
  await expect(page.getByText('Documents expired or expiring soon')).toBeVisible()
  await expect(page.getByRole('cell', { name: new RegExp(`COI ${tag}`) })).toBeVisible()

  // from the dashboard to the contact's documents; archiving it (replaced) takes it off the list
  await page.getByRole('row', { name: new RegExp(`COI ${tag}`) }).getByRole('link', { name: 'Seneca Advantage' }).click()
  await expect(page).toHaveURL(/tab=documents/)
  await page.getByRole('button', { name: `Actions for COI ${tag}` }).click()
  await page.getByRole('menuitem', { name: 'Archive (replaced)' }).click()
  await expect(page.getByRole('row', { name: new RegExp(`COI ${tag}`) })).toBeHidden()
  await page.getByRole('link', { name: 'Dashboard' }).click()
  await expect(page.getByRole('cell', { name: new RegExp(`COI ${tag}`) })).toBeHidden()
  expect(errors).toEqual([])
})
