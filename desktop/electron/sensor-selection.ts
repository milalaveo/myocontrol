import fs from 'node:fs/promises'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import { app } from 'electron'

export type SensorSelection = { address: string; label: string }

function validate(value: unknown): SensorSelection {
  if (!value || typeof value !== 'object') throw new Error('Invalid sensor selection')
  const item = value as Record<string, unknown>
  if (
    typeof item.address !== 'string' ||
    typeof item.label !== 'string' ||
    item.address.length > 200 ||
    item.label.length > 200 ||
    /[\x00-\x1f\x7f]/.test(item.address + item.label)
  )
    throw new Error('Invalid sensor selection')
  return { address: item.address.trim(), label: item.label.trim() }
}

function location() {
  return path.join(app.getPath('userData'), 'sensor-selection.json')
}

export async function readSensorSelection(): Promise<SensorSelection | null> {
  try {
    const item = validate(JSON.parse(await fs.readFile(location(), 'utf8')))
    return item.address ? item : null
  } catch {
    return null
  }
}

async function writeSelection(selection: SensorSelection): Promise<void> {
  const file = location()
  await fs.mkdir(path.dirname(file), { recursive: true })
  const temporary = `${file}.${randomUUID()}.tmp`
  try {
    await fs.writeFile(temporary, JSON.stringify(selection), { mode: 0o600 })
    await fs.rename(temporary, file)
  } finally {
    await fs.rm(temporary, { force: true })
  }
}

// Preserve the order of rapid manual edits/selector changes across async writes.
let pending: Promise<void> = Promise.resolve()
export function saveSensorSelection(value: unknown): Promise<void> {
  const selection = validate(value)
  pending = pending.catch(() => {}).then(() => writeSelection(selection))
  return pending
}
