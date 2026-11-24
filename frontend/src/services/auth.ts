import type { AccessSession, Credentials, CurrentOperator } from '../types/cloud'
import { requestJson } from './http'

export async function createSession(credentials: Credentials): Promise<AccessSession> {
  const response = await requestJson<AccessSession>('auth/v1/sessions', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
  return { operator: response.operator }
}

export async function currentSession(signal: AbortSignal): Promise<AccessSession> {
  const current = await requestJson<CurrentOperator>('auth/v1/me', { signal })
  return {
    operator: { id: current.operator_id, display_name: current.display_name, role: current.role },
  }
}

export function revokeSession() {
  return requestJson<void>('auth/v1/sessions/current', { method: 'DELETE' })
}
