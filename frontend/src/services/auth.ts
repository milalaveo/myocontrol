import type { AccessSession, Credentials } from '../types/cloud'
import { requestJson } from './http'

export function createSession(credentials: Credentials) {
  return requestJson<AccessSession>('auth/v1/sessions', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
}

export function revokeSession(token: string) {
  return requestJson<void>('auth/v1/sessions/current', { method: 'DELETE', token })
}
