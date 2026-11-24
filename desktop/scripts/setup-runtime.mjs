import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve('../local-runtime')
const python = path.join(
  root,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)
function run(executable, args) {
  const result = spawnSync(executable, args, { stdio: 'inherit', windowsHide: true })
  if (result.status !== 0) process.exit(result.status ?? 1)
}
if (!fs.existsSync(python))
  run(
    process.env.MYOCONTROL_BOOTSTRAP_PYTHON ||
      (process.platform === 'win32' ? 'python' : 'python3'),
    ['-m', 'venv', path.join(root, '.venv')],
  )
run(python, ['-m', 'ensurepip', '--upgrade'])
run(python, ['-m', 'pip', 'install', '-r', path.join(root, 'requirements-build.txt')])
run(python, ['-m', 'pip', 'install', '--no-deps', 'bitalino==1.2.6'])
console.log(
  'Local runtime dependencies installed. Paired Bluetooth serial ports require no PyBluez package.',
)
