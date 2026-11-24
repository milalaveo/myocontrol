import { spawn } from 'node:child_process'
import { watch } from 'node:fs'
import path from 'node:path'
import { createServer } from 'vite'
import electron from 'electron'

const env = { ...process.env, MYOCONTROL_DEV: '1' }
delete env.ELECTRON_RUN_AS_NODE
const vite = await createServer({ configFile: path.resolve('vite.config.ts') })
await vite.listen()
vite.printUrls()
let application
let stopping = false
let restarting = false
let applicationReady = false
let generation = 0
let launchedGeneration = 0
let restartTimer
let pythonWatcher
const compiler = spawn(
  process.execPath,
  [
    'node_modules/typescript/bin/tsc',
    '-p',
    'tsconfig.electron.json',
    '--watch',
    '--preserveWatchOutput',
    '--pretty',
    'false',
  ],
  { env, stdio: ['ignore', 'pipe', 'inherit'], windowsHide: true },
)

async function close(code = 0) {
  if (stopping) return
  stopping = true
  clearTimeout(restartTimer)
  pythonWatcher?.close()
  if (application?.connected) {
    const closed = new Promise((resolve) => application.once('exit', resolve))
    application.send({ type: 'myocontrol:dev-stop' })
    let timer
    await Promise.race([
      closed,
      new Promise((resolve) => {
        timer = setTimeout(resolve, 20_000)
      }),
    ])
    clearTimeout(timer)
    if (application.exitCode === null) application.kill()
  }
  compiler.kill()
  await vite.close()
  process.exit(code)
}
function requestRestart() {
  clearTimeout(restartTimer)
  restartTimer = setTimeout(() => {
    if (applicationReady && generation > launchedGeneration && application?.connected)
      application.send({ type: 'myocontrol:dev-restart' })
  }, 150)
}
function launch() {
  if (stopping) return
  restarting = false
  applicationReady = false
  launchedGeneration = generation
  application = spawn(electron, ['.', ...process.argv.slice(2)], {
    env,
    stdio: ['inherit', 'inherit', 'inherit', 'ipc'],
    windowsHide: true,
  })
  application.on('message', (message) => {
    if (message?.type === 'myocontrol:dev-ready') {
      applicationReady = true
      console.log(`[dev] Electron window ready: ${message.visible ? 'visible' : 'hidden'}`)
      requestRestart()
    } else if (message?.type === 'myocontrol:dev-restarting') {
      restarting = true
      console.log('[dev] Restarting Electron after a successful build; local work is idle.')
    } else if (message?.type === 'myocontrol:dev-deferred') {
      console.log('[dev] Restart deferred until capture/replay finishes. UI HMR remains available.')
    }
  })
  application.once('error', (error) => {
    console.error(error.message)
    void close(1)
  })
  application.once('exit', (code) => {
    if (restarting && !stopping) launch()
    else if (!stopping) void close(code ?? 0)
  })
}
let output = ''
compiler.stdout.on('data', (chunk) => {
  process.stdout.write(chunk)
  output += chunk.toString()
  const lines = output.split(/\r?\n/)
  output = lines.pop() ?? ''
  for (const line of lines) {
    if (line.includes('Found 0 errors. Watching for file changes.')) {
      generation += 1
      if (application) requestRestart()
      else launch()
    }
  }
})
compiler.once('error', (error) => {
  console.error(error.message)
  void close(1)
})
compiler.once('exit', (code) => {
  if (!stopping) void close(code ?? 1)
})
pythonWatcher = watch(
  '../local-runtime/myocontrol_runtime',
  { recursive: true },
  (_event, filename) => {
    if (filename?.endsWith('.py') && !filename.includes('__pycache__')) {
      generation += 1
      requestRestart()
    }
  },
)
process.on('SIGINT', () => void close())
process.on('SIGTERM', () => void close())
console.log(
  '[dev] UI: Vite HMR. Main/preload/Python: restart when idle. Close the app to stop development.',
)
