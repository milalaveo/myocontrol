import { spawnSync } from 'node:child_process'
import path from 'node:path'

const root = path.resolve('../local-runtime')
const python = path.join(
  root,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)
const args = [
  '-m',
  'PyInstaller',
  '--noconfirm',
  '--clean',
  '--onedir',
  '--name',
  'myocontrol-runtime',
  '--paths',
  root,
  '--collect-submodules',
  'myocontrol_runtime',
  '--hidden-import',
  'bitalino',
  '--copy-metadata',
  'bitalino',
  '--copy-metadata',
  'pyserial',
  '--distpath',
  'build/runtime',
  '--workpath',
  'build/runtime-work',
  '--specpath',
  'build',
  path.join(root, 'entry.py'),
]
const result = spawnSync(python, args, { stdio: 'inherit', windowsHide: true })
process.exit(result.status ?? 1)
