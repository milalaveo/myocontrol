import { expect, test } from '@playwright/test'
import {
  expectNoPageOverflow,
  mockCloudApi,
  navigateTo,
  resultId,
  secondId,
  signIn,
  testEmail,
} from './fixtures'

test('operator signs in, browses paginated registries, inspects details and signs out', async ({
  page,
}) => {
  const state = await mockCloudApi(page)
  await page.goto('/')
  await expect(page).toHaveURL(/\/login$/)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('Enter a valid email address.')).toBeVisible()
  await page.getByLabel('Email', { exact: true }).fill(testEmail)
  await page.getByLabel('Password', { exact: true }).fill('incorrect-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('Invalid email or password')).toBeVisible()
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('')

  await signIn(page)
  await expect(page.getByRole('table', { name: 'Experiment history', exact: true })).toBeVisible()
  await expectNoPageOverflow(page)
  await page.getByRole('button', { name: 'Next page', exact: true }).click()
  await expect(page).toHaveURL(/\/experiments\?page=2$/)
  await page.getByRole('button', { name: `View ${secondId}`, exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/experiments/${secondId}\\?page=2$`))
  await expect(page.getByText(secondId, { exact: true })).toBeVisible()
  await page.goBack()
  await expect(page).toHaveURL(/\/experiments\?page=2$/)
  await expect(page.getByRole('button', { name: 'Next page', exact: true })).toBeDisabled()

  await navigateTo(page, 'Models')
  await expect(page.getByText('Source LDA', { exact: true })).toBeVisible()
  await navigateTo(page, 'Results')
  await expect(page.getByText('92.50%', { exact: true })).toBeVisible()
  await expect(page.getByTitle('No rest windows')).toHaveText('N/A')
  await page.getByRole('button', { name: `View ${resultId}`, exact: true }).click()
  await expect(page.getByRole('table', { name: 'Confusion counts' })).toBeVisible()
  await expectNoPageOverflow(page)
  expect(
    await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length })),
  ).toEqual({ local: 0, session: 0 })
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  expect(state.signedOut).toBe(true)
})

test('protected deep links, retryable failures, empty lists and expired sessions recover correctly', async ({
  page,
}) => {
  const state = await mockCloudApi(page, { failFirstRunRead: true, emptyModels: true })
  await page.goto(`/results/${resultId}`)
  await expect(page).toHaveURL(/\/login$/)
  await signIn(page)
  await expect(page).toHaveURL(new RegExp(`/results/${resultId}$`))
  await expect(page.getByRole('heading', { name: 'Registry details' })).toBeVisible()

  await navigateTo(page, 'Experiments')
  await expect(page.getByText('Registry temporarily unavailable', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect(page.getByRole('table', { name: 'Experiment history', exact: true })).toBeVisible()
  await navigateTo(page, 'Models')
  await expect(page.getByRole('heading', { name: 'No models yet' })).toBeVisible()
  state.expireModels = true
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(
    page.getByText('Your session has expired or been revoked. Please sign in again.'),
  ).toBeVisible()
  await signIn(page)
  await expect(page).toHaveURL(/\/models$/)
  await expect(page.getByRole('heading', { name: 'No models yet' })).toBeVisible()
  await expectNoPageOverflow(page)
})
