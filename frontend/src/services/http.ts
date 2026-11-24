export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status = 0,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface RequestOptions extends RequestInit {
  token?: string
}

export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { token, signal, ...init } = options
  const timeout = AbortSignal.timeout(20_000)
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  headers.set('X-MyoControl-Web', '1')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body) headers.set('Content-Type', 'application/json')

  let response: Response
  try {
    response = await fetch(`/api/${path}`, {
      ...init,
      credentials: 'same-origin',
      headers,
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError(
      timeout.aborted
        ? 'The request timed out. Please try again.'
        : 'Unable to reach the server. Check your connection and try again.',
    )
  }

  if (response.status === 204) return undefined as T
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null
    throw new ApiError(
      typeof detail === 'string'
        ? detail
        : `Request failed (${response.status}). Please try again.`,
      response.status,
    )
  }
  if (body === null)
    throw new ApiError(
      'The server returned an invalid response. Please try again.',
      response.status,
    )
  return body as T
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}
