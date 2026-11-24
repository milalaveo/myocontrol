import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { EventEmitter } from 'node:events'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { app } from 'electron'

export class RuntimeManager extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null
  private pending = new Map<
    string,
    { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: NodeJS.Timeout }
  >()
  private starting: Promise<unknown> | null = null
  private stopping = false

  start() {
    if (this.starting) return this.starting
    this.stopping = false
    const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
    const directory = app.isPackaged
      ? path.join(process.resourcesPath, 'runtime')
      : path.join(root, 'local-runtime')
    const executable = app.isPackaged
      ? path.join(
          directory,
          process.platform === 'win32' ? 'myocontrol-runtime.exe' : 'myocontrol-runtime',
        )
      : process.env.MYOCONTROL_PYTHON ||
        path.join(
          directory,
          '.venv',
          process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
        )
    const args = app.isPackaged ? [] : ['-u', '-m', 'myocontrol_runtime']
    args.push('--data-dir', path.join(app.getPath('userData'), 'local'))
    const env: NodeJS.ProcessEnv = { ...process.env, PYTHONUNBUFFERED: '1' }
    delete env.PYTHONPATH
    this.child = spawn(executable, args, {
      cwd: directory,
      env,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    let buffer = ''
    this.child.stdout.setEncoding('utf8')
    this.child.stdout.on('data', (data: string) => {
      buffer += data
      if (buffer.length > 4 * 1024 * 1024) {
        this.fail('Local runtime exceeded the message size limit')
        this.child?.kill()
        return
      }
      for (;;) {
        const newline = buffer.indexOf('\n')
        if (newline < 0) break
        const line = buffer.slice(0, newline)
        buffer = buffer.slice(newline + 1)
        try {
          const message = JSON.parse(line)
          if (message.event) this.emit('runtime-event', message)
          else if (typeof message.id === 'string') {
            const pending = this.pending.get(message.id)
            if (!pending) continue
            clearTimeout(pending.timer)
            this.pending.delete(message.id)
            if (message.error) pending.reject(new Error(String(message.error.message)))
            else pending.resolve(message.result)
          }
        } catch {
          this.fail('Local runtime sent an invalid message')
        }
      }
    })
    this.child.stderr.resume()
    this.child.on('error', () =>
      this.fail(
        'Cannot start the Python runtime. Run the runtime setup command or reinstall the application.',
      ),
    )
    this.child.on('exit', () => {
      this.child = null
      this.starting = null
      if (!this.stopping)
        this.fail('Local runtime stopped. Outputs are neutral; restart the runtime explicitly.')
    })
    this.starting = this.call('status')
    return this.starting
  }

  private fail(message: string) {
    for (const request of this.pending.values()) {
      clearTimeout(request.timer)
      request.reject(new Error(message))
    }
    this.pending.clear()
    this.emit('runtime-event', { event: 'runtime-error', data: { message } })
  }

  call(method: string, params: Record<string, unknown> = {}, timeout = 20000): Promise<unknown> {
    if (!this.child || this.child.killed || !this.child.stdin.writable)
      return Promise.reject(new Error('Local runtime is not running'))
    const id = randomUUID()
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error('Local operation timed out. Stop or restart the runtime.'))
      }, timeout)
      this.pending.set(id, { resolve, reject, timer })
      this.child!.stdin.write(JSON.stringify({ id, method, params }) + '\n', (error) => {
        if (error) {
          clearTimeout(timer)
          this.pending.delete(id)
          reject(new Error('Local runtime connection closed'))
        }
      })
    })
  }

  async stop() {
    this.stopping = true
    const child = this.child
    if (!child) {
      this.starting = null
      return
    }
    try {
      await this.call('shutdown', {}, 12000)
    } catch {
      child.kill()
    }
    child.stdin.end()
    await new Promise<void>((resolve) => {
      if (child.exitCode !== null) {
        resolve()
        return
      }
      const timer = setTimeout(() => {
        child.kill()
        resolve()
      }, 2000)
      child.once('exit', () => {
        clearTimeout(timer)
        resolve()
      })
    })
    this.child = null
    this.starting = null
  }
}
