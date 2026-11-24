import fs from 'node:fs'
import path from 'node:path'
import { app } from 'electron'
import electronUpdater from 'electron-updater'
import { UpdateController, type UpdateStatus } from './update-controller.js'

export function createUpdates(dependencies: {
  prepareInstall(): Promise<void>
  stopRuntime(): Promise<void>
  cancelInstall(): void
  notify(status: UpdateStatus): void
}) {
  const logDirectory = path.join(app.getPath('userData'), 'logs')
  const log = (event: string, code?: string) => {
    try {
      fs.mkdirSync(logDirectory, { recursive: true })
      const target = path.join(logDirectory, 'updates.log')
      if (fs.existsSync(target) && fs.statSync(target).size > 1024 * 1024) {
        fs.rmSync(target + '.1', { force: true })
        fs.renameSync(target, target + '.1')
      }
      // Never log credentials, arbitrary exception messages or request/response bodies.
      fs.appendFileSync(
        target,
        JSON.stringify({ time: new Date().toISOString(), event, code }) + '\n',
      )
    } catch {
      // An unwritable diagnostic log must not interrupt acquisition or replay.
    }
  }
  const installed =
    app.isPackaged &&
    process.platform === 'win32' &&
    process.env.MYOCONTROL_E2E !== '1' &&
    fs.existsSync(path.join(process.resourcesPath, 'myocontrol-installed'))
  let updater = null
  if (installed) {
    const { autoUpdater } = electronUpdater
    autoUpdater.autoDownload = true
    autoUpdater.autoInstallOnAppQuit = false
    autoUpdater.allowDowngrade = false
    autoUpdater.allowPrerelease = false
    autoUpdater.logger = null
    updater = autoUpdater
  }
  const controller = new UpdateController(updater, app.getVersion(), { ...dependencies, log })
  if (installed) {
    const startup = setTimeout(() => void controller.check(), 10_000)
    const timer = setInterval(() => void controller.check(), 30 * 60_000)
    startup.unref()
    timer.unref()
    app.once('will-quit', () => {
      clearTimeout(startup)
      clearInterval(timer)
    })
  }
  return controller
}
