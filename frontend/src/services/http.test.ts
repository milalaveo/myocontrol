import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, requestJson } from './http'

afterEach(() => vi.unstubAllGlobals())

describe('HTTP client', () => {
  it('adds the bearer token and returns decoded data', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] })))
    vi.stubGlobal('fetch', fetch)
    expect(await requestJson('cloud/v1/runs', { token: 'test-token' })).toEqual({ items: [] })
    expect(fetch.mock.calls[0][1].headers.get('Authorization')).toBe('Bearer test-token')
  })

  it('preserves HTTP status for centralized expired-session handling', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: 'Session expired' }), { status: 401 }),
        ),
    )
    await expect(requestJson('auth/v1/me')).rejects.toMatchObject({
      status: 401,
      message: 'Session expired',
    })
  })

  it('handles empty logout responses and malformed upstream errors', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response('<html>Unavailable</html>', { status: 502 }))
      .mockResolvedValueOnce(new Response('not json'))
    vi.stubGlobal('fetch', fetch)
    expect(await requestJson('auth/v1/sessions/current', { method: 'DELETE' })).toBeUndefined()
    await expect(requestJson('cloud/v1/runs')).rejects.toMatchObject({ status: 502 })
    await expect(requestJson('cloud/v1/runs')).rejects.toThrow('invalid response')
  })

  it('reports connection failures and preserves caller cancellations', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network failed')))
    await expect(requestJson('cloud/v1/runs')).rejects.toBeInstanceOf(ApiError)
    const controller = new AbortController()
    controller.abort()
    await expect(
      requestJson('cloud/v1/runs', { signal: controller.signal }),
    ).rejects.toBeInstanceOf(TypeError)
  })
})
