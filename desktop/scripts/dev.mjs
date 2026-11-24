import { spawn } from 'node:child_process'
import electron from 'electron'

const env = { ...process.env, MYOCONTROL_DEV: '1' }
delete env.ELECTRON_RUN_AS_NODE
const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js'], {
  env,
  stdio: 'inherit',
  windowsHide: true,
})
let app
function close() {
  app?.kill()
  vite.kill()
}
process.on('SIGINT', close)
process.on('SIGTERM', close)
for (let i = 0; i < 100; i++) {
  try {
    if ((await fetch('http://127.0.0.1:5174')).ok) break
  } catch {}
  await new Promise((resolve) => setTimeout(resolve, 100))
}
app = spawn(electron, ['.'], { env, stdio: 'inherit', windowsHide: true })
app.on('exit', (code) => {
  vite.kill()
  process.exit(code ?? 0)
})
