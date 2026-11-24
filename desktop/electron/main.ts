import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { RuntimeManager } from './runtime-manager.js'
import { readSensorSelection, saveSensorSelection } from './sensor-selection.js'
import {
  clearCredentials,
  publicIdentity,
  readCredentials,
  saveCredentials,
  type Credentials,
} from './credentials.js'

const directory = path.dirname(fileURLToPath(import.meta.url))
if (!app.isPackaged && process.env.MYOCONTROL_PROFILE)
  app.setPath('userData', path.resolve(process.env.MYOCONTROL_PROFILE))
const single = app.requestSingleInstanceLock()
if (!single) app.quit()

const runtime = new RuntimeManager()
let window: BrowserWindow | null = null
let credentials: Credentials | null = null
let quitting = false

runtime.on('runtime-event', (event) => {
  if (event.event === 'cloud' && event.data.state === 'auth_required') {
    credentials = null
    void clearCredentials().catch(() => {})
  }
  if (window && !window.isDestroyed() && !window.webContents.isDestroyed())
    window.webContents.send('runtime:event', event)
})

function trusted(event: Electron.IpcMainInvokeEvent) {
  if (
    !window ||
    event.sender !== window.webContents ||
    event.senderFrame !== window.webContents.mainFrame
  )
    throw new Error('Untrusted desktop caller')
}

const commands = new Set([
  'status',
  'recordings',
  'start_capture',
  'start_replay',
  'stop',
  'pause',
  'resume',
  'clear_model',
  'train_personal_model',
  'scan_sensors',
  'sync_status',
  'queue_upload',
  'retry_sync',
])

ipcMain.handle('runtime:request', async (event, method: unknown, params: unknown) => {
  trusted(event)
  if (
    typeof method !== 'string' ||
    !commands.has(method) ||
    !params ||
    typeof params !== 'object' ||
    Array.isArray(params) ||
    JSON.stringify(params).length > 8192
  )
    throw new Error('Invalid desktop command')
  return runtime.call(method, params as Record<string, unknown>)
})
ipcMain.handle('desktop:import', async (event, participantKey: string) => {
  trusted(event)
  const result = await dialog.showOpenDialog(window!, {
    properties: ['openFile'],
    filters: [{ name: 'Signal JSON', extensions: ['json'] }],
  })
  return result.canceled
    ? null
    : runtime.call('import_recording', {
        path: result.filePaths[0],
        participant_key: participantKey || 'local-import',
      })
})
ipcMain.handle('desktop:demo', async (event) => {
  trusted(event)
  const fixture = app.isPackaged
    ? path.join(process.resourcesPath, 'fixtures/synthetic-demo.json')
    : path.resolve(directory, '../../local-runtime/fixtures/synthetic-demo.json')
  return runtime.call('import_recording', { path: fixture, participant_key: 'synthetic-demo' })
})
ipcMain.handle('desktop:model', async (event) => {
  trusted(event)
  const result = await dialog.showOpenDialog(window!, {
    properties: ['openFile'],
    filters: [{ name: 'LDA model JSON', extensions: ['json'] }],
  })
  return result.canceled ? null : runtime.call('load_model', { path: result.filePaths[0] })
})
ipcMain.handle('desktop:export', async (event, identifier: unknown) => {
  trusted(event)
  if (typeof identifier !== 'string' || !/^[0-9a-f-]{36}$/.test(identifier))
    throw new Error('Invalid recording identifier')
  const result = await dialog.showSaveDialog(window!, {
    defaultPath: `recording-${identifier}.json`,
    filters: [{ name: 'Signal JSON', extensions: ['json'] }],
  })
  return result.canceled
    ? null
    : runtime.call('export_recording', { identifier, destination: result.filePath })
})
ipcMain.handle('desktop:restart', async (event) => {
  trusted(event)
  await runtime.stop()
  await runtime.start()
  if (credentials) await runtime.call('cloud_restore', { credentials })
  return runtime.call('status')
})
ipcMain.handle('sensor:selection', (event) => {
  trusted(event)
  return readSensorSelection()
})
ipcMain.handle('sensor:select', (event, value: unknown) => {
  trusted(event)
  return saveSensorSelection(value)
})
ipcMain.handle('sensor:bluetooth-settings', async (event) => {
  trusted(event)
  if (process.platform === 'win32') return shell.openExternal('ms-settings:bluetooth')
  if (process.platform === 'darwin')
    return shell.openExternal('x-apple.systempreferences:com.apple.Bluetooth')
  throw new Error('Open Bluetooth pairing from your operating system settings')
})

ipcMain.handle('cloud:identity', (event) => {
  trusted(event)
  return publicIdentity(credentials)
})
ipcMain.handle('cloud:login', async (event, body: unknown) => {
  trusted(event)
  if (!body || typeof body !== 'object' || Array.isArray(body))
    throw new Error('Invalid credentials')
  const value = body as Record<string, unknown>
  if (
    typeof value.base !== 'string' ||
    typeof value.email !== 'string' ||
    typeof value.password !== 'string'
  )
    throw new Error('Enter the cloud URL, email and password')
  if (credentials) throw new Error('Sign out before switching operator accounts')
  credentials = (await runtime.call('cloud_login', value)) as Credentials
  const persisted = await saveCredentials(credentials)
  return publicIdentity(credentials, persisted)
})
ipcMain.handle('cloud:logout', async (event) => {
  trusted(event)
  await runtime.call('cloud_logout')
  credentials = null
  await clearCredentials()
  return publicIdentity(null)
})

async function launch() {
  window = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 900,
    minHeight: 680,
    title: 'MyoControl Desktop',
    show: process.env.MYOCONTROL_E2E !== '1',
    webPreferences: {
      preload: path.join(directory, 'preload.cjs'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  })
  window.removeMenu()
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  window.webContents.on('will-navigate', (event) => event.preventDefault())
  window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) =>
    callback(false),
  )
  credentials = await readCredentials()
  try {
    await runtime.start()
    if (credentials) await runtime.call('cloud_restore', { credentials })
  } catch {
    credentials = null
  }
  if (!app.isPackaged && process.env.MYOCONTROL_DEV === '1')
    await window.loadURL('http://127.0.0.1:5174')
  else await window.loadFile(path.join(directory, '../dist/index.html'))
  window.on('closed', () => {
    window = null
    app.quit()
  })
}

app.on('second-instance', () => {
  window?.show()
  window?.focus()
})
app.on('before-quit', (event) => {
  if (quitting) return
  event.preventDefault()
  quitting = true
  void runtime.stop().finally(() => app.quit())
})
if (single) void app.whenReady().then(launch)
