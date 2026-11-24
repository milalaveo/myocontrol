import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { RuntimeManager } from './runtime-manager.js'
import { createUpdates } from './updates.js'
import { readSensorSelection, saveSensorSelection } from './sensor-selection.js'
import {
  clearCredentials,
  publicIdentity,
  readCredentials,
  saveCredentials,
  type Credentials,
} from './credentials.js'

const directory = path.dirname(fileURLToPath(import.meta.url))
if (!app.isPackaged) {
  if (process.env.MYOCONTROL_PROFILE)
    app.setPath('userData', path.resolve(process.env.MYOCONTROL_PROFILE))
  else if (process.env.MYOCONTROL_DEV === '1')
    app.setPath('userData', path.join(app.getPath('appData'), 'MyoControl Development'))
}
const single = app.requestSingleInstanceLock()
if (!single) app.quit()

const runtime = new RuntimeManager()
let window: BrowserWindow | null = null
let credentials: Credentials | null = null
let quitting = false
let installingUpdate = false
let stoppedForUpdate = false
let devRestartPending = false
let devRestartChecking = false
function restartDevelopmentWhenIdle() {
  if (!devRestartPending || devRestartChecking || installingUpdate || quitting) return
  devRestartChecking = true
  void runtime
    .call('status')
    .then((value) => {
      if (['idle', 'failed'].includes((value as { state: string }).state)) {
        devRestartPending = false
        process.send?.({ type: 'myocontrol:dev-restarting' })
        app.quit()
      } else {
        process.send?.({ type: 'myocontrol:dev-deferred' })
      }
    })
    .catch(() => {})
    .finally(() => {
      devRestartChecking = false
    })
}
if (!app.isPackaged && process.env.MYOCONTROL_DEV === '1' && process.send) {
  process.on('message', (message) => {
    if (!message || typeof message !== 'object' || !('type' in message)) return
    if (message.type === 'myocontrol:dev-restart') {
      devRestartPending = true
      restartDevelopmentWhenIdle()
    } else if (message.type === 'myocontrol:dev-stop') app.quit()
  })
  process.on('disconnect', () => app.quit())
}
const updates = createUpdates({
  prepareInstall: async () => {
    installingUpdate = true
    const status = (await runtime.call('status')) as { state: string }
    if (!['idle', 'failed'].includes(status.state))
      throw new Error('Stop capture, calibration or replay before installing an update')
  },
  stopRuntime: async () => {
    await runtime.stop()
    stoppedForUpdate = true
    quitting = true
  },
  cancelInstall: () => {
    installingUpdate = false
    quitting = false
    if (stoppedForUpdate) {
      stoppedForUpdate = false
      void runtime
        .start()
        .then(async () => {
          if (credentials) await runtime.call('cloud_restore', { credentials })
        })
        .catch(() => {})
    }
  },
  notify: (status) => {
    if (window && !window.isDestroyed() && !window.webContents.isDestroyed())
      window.webContents.send('updates:status', status)
  },
})

function callRuntime(method: string, params: Record<string, unknown> = {}) {
  if (installingUpdate) throw new Error('The app is restarting to install an update')
  return runtime.call(method, params)
}

runtime.on('runtime-event', (event) => {
  if (event.event === 'status') restartDevelopmentWhenIdle()
  if (event.event === 'cloud' && event.data.state === 'auth_required') {
    credentials = null
    void clearCredentials().catch(() => {})
  }
  if (window && !window.isDestroyed() && !window.webContents.isDestroyed())
    window.webContents.send('runtime:event', event)
})

function trusted(event: Electron.IpcMainInvokeEvent) {
  if (installingUpdate) throw new Error('The app is restarting to install an update')
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
  'sync_status',
  'queue_upload',
  'retry_sync',
  'scan_sensors',
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
  return callRuntime(method, params as Record<string, unknown>)
})
ipcMain.handle('desktop:import', async (event, participantKey: string) => {
  trusted(event)
  const result = await dialog.showOpenDialog(window!, {
    properties: ['openFile'],
    filters: [{ name: 'Signal JSON', extensions: ['json'] }],
  })
  return result.canceled
    ? null
    : callRuntime('import_recording', {
        path: result.filePaths[0],
        participant_key: participantKey || 'local-import',
      })
})
ipcMain.handle('desktop:demo', async (event) => {
  trusted(event)
  const fixture = app.isPackaged
    ? path.join(process.resourcesPath, 'fixtures/synthetic-demo.json')
    : path.resolve(directory, '../../local-runtime/fixtures/synthetic-demo.json')
  return callRuntime('import_recording', { path: fixture, participant_key: 'synthetic-demo' })
})
ipcMain.handle('desktop:model', async (event) => {
  trusted(event)
  const result = await dialog.showOpenDialog(window!, {
    properties: ['openFile'],
    filters: [{ name: 'LDA model JSON', extensions: ['json'] }],
  })
  return result.canceled ? null : callRuntime('load_model', { path: result.filePaths[0] })
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
    : callRuntime('export_recording', { identifier, destination: result.filePath })
})
ipcMain.handle('desktop:restart', async (event) => {
  trusted(event)
  await runtime.stop()
  await runtime.start()
  if (credentials) await callRuntime('cloud_restore', { credentials })
  return callRuntime('status')
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

ipcMain.handle('updates:status', (event) => {
  trusted(event)
  return updates.snapshot()
})
ipcMain.handle('updates:check', (event) => {
  trusted(event)
  return updates.check()
})
ipcMain.handle('updates:install', (event) => {
  trusted(event)
  return updates.install()
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
  credentials = (await callRuntime('cloud_login', value)) as Credentials
  const persisted = await saveCredentials(credentials)
  return publicIdentity(credentials, persisted)
})
ipcMain.handle('cloud:logout', async (event) => {
  trusted(event)
  await callRuntime('cloud_logout')
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
    restartDevelopmentWhenIdle()
    if (credentials) await callRuntime('cloud_restore', { credentials })
  } catch {
    credentials = null
  }
  if (!app.isPackaged && process.env.MYOCONTROL_DEV === '1')
    await window.loadURL('http://127.0.0.1:5174')
  else await window.loadFile(path.join(directory, '../dist/index.html'))
  if (process.env.MYOCONTROL_E2E !== '1') {
    window.show()
    window.focus()
  }
  if (!app.isPackaged && process.env.MYOCONTROL_DEV === '1')
    process.send?.({ type: 'myocontrol:dev-ready', visible: window.isVisible() })
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
