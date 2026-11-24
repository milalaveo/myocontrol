export type UpdateStatus = {
  phase:
    | 'disabled'
    | 'idle'
    | 'checking'
    | 'available'
    | 'downloading'
    | 'ready'
    | 'installing'
    | 'error'
  version: string
  nextVersion?: string
  progress?: number
  message: string
}

type Updater = {
  on(event: string, listener: (...args: any[]) => void): unknown
  checkForUpdates(): Promise<unknown>
  quitAndInstall(silent?: boolean, runAfter?: boolean): void
}

type Dependencies = {
  prepareInstall(): Promise<void>
  stopRuntime(): Promise<void>
  cancelInstall(): void
  notify(status: UpdateStatus): void
  log(event: string, code?: string): void
}

export class UpdateController {
  private status: UpdateStatus
  private installing = false

  constructor(
    private updater: Updater | null,
    version: string,
    private dependencies: Dependencies,
    disabledMessage = 'Automatic updates are available in the installed Windows app.',
  ) {
    this.status = {
      phase: updater ? 'idle' : 'disabled',
      version,
      message: updater ? 'Updates are checked automatically.' : disabledMessage,
    }
    if (!updater) return
    updater.on('checking-for-update', () => this.set('checking', 'Checking for updates...'))
    updater.on('update-not-available', () => this.set('idle', 'You have the latest version.'))
    updater.on('update-available', (info: { version: string }) => {
      this.status.nextVersion = info.version
      this.set('available', 'A new version is being downloaded.')
    })
    updater.on('download-progress', (progress: { percent: number }) => {
      this.status.progress = Math.max(0, Math.min(100, Number(progress.percent) || 0))
      this.set('downloading', 'Downloading update in the background...')
    })
    updater.on('update-downloaded', (info: { version: string }) => {
      this.status.nextVersion = info.version
      this.status.progress = 100
      this.set('ready', 'Update ready. Restart when your local work is finished.')
    })
    updater.on('error', (error: unknown) => this.failed(error))
  }

  snapshot(): UpdateStatus {
    return { ...this.status }
  }

  private set(phase: UpdateStatus['phase'], message: string) {
    this.status = { ...this.status, phase, message }
    this.dependencies.log(phase)
    this.dependencies.notify(this.snapshot())
  }

  private failed(error: unknown) {
    if (this.installing) {
      this.installing = false
      this.dependencies.cancelInstall()
    }
    const code =
      error && typeof error === 'object' && 'code' in error
        ? String(error.code)
            .replace(/[^A-Za-z0-9_-]/g, '')
            .slice(0, 80)
        : 'UPDATE_ERROR'
    this.dependencies.log('error', code)
    this.set(
      'error',
      'Update check or download failed. Your current app is unchanged; try again later.',
    )
  }

  async check() {
    if (
      !this.updater ||
      ['checking', 'available', 'downloading', 'ready', 'installing'].includes(this.status.phase)
    )
      return this.snapshot()
    try {
      this.set('checking', 'Checking for updates...')
      await this.updater.checkForUpdates()
    } catch (error) {
      this.failed(error)
    }
    return this.snapshot()
  }

  async install() {
    if (!this.updater || this.status.phase !== 'ready' || this.installing)
      throw new Error('No downloaded update is ready to install')
    this.installing = true
    try {
      // The main process closes the action gate before checking the real runtime state.
      await this.dependencies.prepareInstall()
      this.set('installing', 'Closing the local runtime and restarting...')
      await this.dependencies.stopRuntime()
      this.updater.quitAndInstall(true, true)
    } catch (error) {
      this.installing = false
      this.dependencies.cancelInstall()
      this.set(
        'ready',
        'Update is ready. Stop capture or replay before restarting; your work is preserved.',
      )
      throw error
    }
    return this.snapshot()
  }
}
