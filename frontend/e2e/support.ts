import { expect, type Page } from '@playwright/test'

export const SCREENS = process.env.E2E_SCREENS ?? '../tmp/screens'

export function credentials(): { email: string; password: string } {
  const email = process.env.E2E_EMAIL
  const password = process.env.E2E_PASSWORD
  if (!email || !password) throw new Error('Set E2E_EMAIL and E2E_PASSWORD')
  return { email, password }
}

/** Fail the test on any uncaught error in the page. */
export function watchErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (msg) => {
    // The 'am I signed in?' check answers 401 before login; that is expected.
    if (msg.type() === 'error' && !msg.text().includes('status of 401')) errors.push(msg.text())
  })
  return errors
}

export async function login(page: Page) {
  const { email, password } = credentials()
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByRole('textbox', { name: 'Password' }).fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
}

export async function screenshot(page: Page, name: string) {
  await page.waitForLoadState('networkidle')
  await page.screenshot({ path: `${SCREENS}/${name}.png`, fullPage: true })
}
