import fs from 'node:fs/promises'
import path from 'node:path'
import { app, safeStorage } from 'electron'

export interface Credentials {
  base: string
  token: string
  operator_id: string
  display_name: string
  client_id: string
  expires_at: string
}

function available() {
  return (
    safeStorage.isEncryptionAvailable() &&
    !(process.platform === 'linux' && safeStorage.getSelectedStorageBackend() === 'basic_text')
  )
}

function location() {
  return path.join(app.getPath('userData'), 'cloud-session.enc')
}

export async function readCredentials(): Promise<Credentials | null> {
  if (!available()) return null
  try {
    const body = JSON.parse(safeStorage.decryptString(await fs.readFile(location())))
    if (
      !body ||
      typeof body.token !== 'string' ||
      typeof body.base !== 'string' ||
      typeof body.operator_id !== 'string' ||
      !Number.isFinite(Date.parse(body.expires_at)) ||
      Date.parse(body.expires_at) <= Date.now()
    )
      return null
    return body as Credentials
  } catch {
    return null
  }
}

export async function saveCredentials(credentials: Credentials) {
  if (!available()) return false
  const temporary = location() + '.tmp'
  try {
    await fs.writeFile(temporary, safeStorage.encryptString(JSON.stringify(credentials)), {
      mode: 0o600,
    })
    await fs.rename(temporary, location())
    return true
  } catch {
    return false
  }
}

export async function clearCredentials() {
  await fs.rm(location(), { force: true })
}

export function publicIdentity(credentials: Credentials | null, persisted = available()) {
  return credentials
    ? {
        connected: true,
        operator_id: credentials.operator_id,
        display_name: credentials.display_name,
        base: credentials.base,
        expires_at: credentials.expires_at,
        persisted,
      }
    : { connected: false, persisted }
}
