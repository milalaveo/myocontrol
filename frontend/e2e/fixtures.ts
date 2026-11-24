import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'

export const firstId = '11111111-1111-4111-8111-111111111111'
export const secondId = '22222222-2222-4222-8222-222222222222'
export const modelId = '33333333-3333-4333-8333-333333333333'
export const resultId = '44444444-4444-4444-8444-444444444444'
export const testEmail = 'operator@example.test'
export const testPassword = 'browser-test-password'

export async function mockCloudApi(
  page: Page,
  options: { failFirstRunRead?: boolean; emptyModels?: boolean } = {},
) {
  const state = {
    signedIn: false,
    signedOut: false,
    failRunRead: !!options.failFirstRunRead,
    expireModels: false,
  }
  const model = {
    id: modelId,
    name: 'Source LDA',
    family: 'lda',
    condition: 'source_only',
    published_at: '2026-11-24T10:00:00Z',
  }
  const result = {
    id: resultId,
    model_id: modelId,
    family: 'lda',
    condition: 'source_only',
    accuracy: 0.925,
    macro_f1: 0.9,
    rest_false_activation_rate: null,
    rest_missing_reason: 'No rest windows',
    feature_contract: { version: 'four-channel-v1' },
    confusion_counts: [
      { actual_class: 'rest', predicted_class: 'rest', count: 12 },
      { actual_class: 'fist', predicted_class: 'rest', count: 1 },
    ],
  }

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.pathname === '/api/auth/v1/sessions' && request.method() === 'POST') {
      const credentials = request.postDataJSON()
      if (credentials.email !== testEmail || credentials.password !== testPassword) {
        return route.fulfill({ status: 401, json: { detail: 'Invalid email or password' } })
      }
      state.signedIn = true
      return route.fulfill({
        headers: {
          'Set-Cookie':
            'myocontrol_web_session=synthetic-browser-session-token; Path=/; HttpOnly; SameSite=Strict',
        },
        json: {
          access_token: 'synthetic-browser-session-token',
          operator: { id: 'test-operator', display_name: 'Test operator', role: 'operator' },
        },
      })
    }
    expect(request.headers()['x-myocontrol-web']).toBe('1')
    expect(request.headers().authorization).toBeUndefined()
    if (url.pathname === '/api/auth/v1/me') {
      return state.signedIn
        ? route.fulfill({
            json: {
              operator_id: 'test-operator',
              display_name: 'Test operator',
              role: 'operator',
              scope: 'web',
              expires_at: '2099-01-01T00:00:00Z',
            },
          })
        : route.fulfill({ status: 401, json: { detail: 'Sign in required' } })
    }
    if (url.pathname === '/api/auth/v1/sessions/current' && request.method() === 'DELETE') {
      state.signedOut = true
      state.signedIn = false
      return route.fulfill({
        status: 204,
        headers: { 'Set-Cookie': 'myocontrol_web_session=; Path=/; Max-Age=0' },
      })
    }
    if (url.pathname === '/api/cloud/v1/runs' && state.failRunRead) {
      state.failRunRead = false
      return route.fulfill({ status: 503, json: { detail: 'Registry temporarily unavailable' } })
    }
    if (url.pathname.startsWith('/api/cloud/v1/models') && state.expireModels) {
      state.expireModels = false
      state.signedIn = false
      return route.fulfill({ status: 401, json: { detail: 'Session expired or revoked' } })
    }
    const run = {
      id: firstId,
      family: 'lda',
      condition: 'source_only',
      status: 'queued',
      execution_location: 'local_workstation',
    }
    switch (url.pathname) {
      case '/api/cloud/v1/recordings':
        return route.fulfill({
          json: {
            items: [
              {
                id: '66666666-6666-4666-8666-666666666666',
                local_recording_id: firstId,
                source_participant_key: 'demo-participant',
                source_kind: 'synthetic',
                source_name: 'Synthetic integration fixture',
                source_version: '1',
                sample_count: 2,
                sample_rate_hz: 1000,
                channel_count: 4,
                channel_map: [0, 1, 2, 3],
                units: 'arbitrary',
                original_signal_key: secondId,
                original_start_sample: 0,
                original_end_sample: 2,
                received_at: '2026-11-24T10:00:00Z',
              },
            ],
            next_offset: null,
          },
        })
      case '/api/cloud/v1/recordings/66666666-6666-4666-8666-666666666666/signal':
        return route.fulfill({
          json: {
            sample_rate_hz: 1000,
            channel_map: [0, 1, 2, 3],
            units: 'arbitrary',
            source_kind: 'synthetic',
            source_name: 'Synthetic integration fixture',
            source_version: '1',
            samples: [
              [1, 2, 3, 4],
              [2, 3, 4, 5],
            ],
          },
        })
      case '/api/cloud/v1/runs': {
        const offset = Number(url.searchParams.get('offset'))
        return route.fulfill({
          json: offset
            ? { items: [{ ...run, id: secondId }], next_offset: null }
            : {
                items: Array.from({ length: 25 }, (_, i) => ({
                  ...run,
                  id: i === 0 ? firstId : `55555555-5555-4555-8555-${String(i).padStart(12, '0')}`,
                })),
                next_offset: 25,
              },
        })
      }
      case `/api/cloud/v1/runs/${secondId}`:
        return route.fulfill({
          json: { ...run, id: secondId, feature_contract: { version: 'four-channel-v1' } },
        })
      case '/api/cloud/v1/models':
        return route.fulfill({
          json: { items: options.emptyModels ? [] : [model], next_offset: null },
        })
      case `/api/cloud/v1/models/${modelId}`:
        return route.fulfill({ json: model })
      case '/api/cloud/v1/results':
        return route.fulfill({ json: { items: [result], next_offset: null } })
      case `/api/cloud/v1/results/${resultId}`:
        return route.fulfill({ json: result })
      default:
        return route.fulfill({ status: 404, json: { detail: 'Fixture route not found' } })
    }
  })
  return state
}

export async function signIn(page: Page) {
  await page.getByLabel('Email', { exact: true }).fill(testEmail)
  await page.getByLabel('Password', { exact: true }).fill(testPassword)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
}

export async function navigateTo(page: Page, name: string) {
  const toggle = page.getByRole('button', { name: 'Open navigation', exact: true })
  if (await toggle.isVisible()) await toggle.click()
  await page
    .getByRole('navigation', { name: 'Research navigation' })
    .getByRole('link', { name, exact: true })
    .click()
}

export async function expectNoPageOverflow(page: Page) {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true)
}
