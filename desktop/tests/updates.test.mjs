import test from 'node:test'
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { UpdateController } from '../dist-electron/update-controller.js'
function fixture(overrides = {}) {
  const events = [],
    log = []
  const updater = new EventEmitter()
  updater.checkForUpdates = async () => events.push('check')
  updater.quitAndInstall = () => events.push('install')
  const dependencies = {
    prepareInstall: async () => events.push('gate'),
    stopRuntime: async () => events.push('stop'),
    cancelInstall: () => events.push('cancel'),
    notify: () => {},
    log: (...entry) => log.push(entry),
    ...overrides,
  }
  return {
    updater,
    events,
    log,
    dependencies,
    controller: new UpdateController(updater, '0.1.0', dependencies),
  }
}
test('uninstalled builds never check or install', async () => {
  const { dependencies, events } = fixture()
  const disabled = new UpdateController(null, '0.1.0', dependencies)
  assert.equal((await disabled.check()).phase, 'disabled')
  await assert.rejects(disabled.install())
  assert.deepEqual(events, [])
})
test('downloads never interrupt work or install automatically', async () => {
  const { updater, controller, events } = fixture()
  await controller.check()
  updater.emit('update-available', { version: '0.2.4' })
  updater.emit('download-progress', { percent: 35 })
  assert.equal(controller.snapshot().phase, 'downloading')
  await assert.rejects(controller.install())
  assert.deepEqual(events, ['check'])
})
test('busy runtime keeps the download ready and prevents installation', async () => {
  const { updater, controller, events } = fixture({
    prepareInstall: async () => {
      throw new Error('capture active')
    },
  })
  updater.emit('update-downloaded', { version: '0.2.4' })
  await assert.rejects(controller.install(), /capture active/)
  assert.deepEqual(events, ['cancel'])
  assert.equal(controller.snapshot().phase, 'ready')
})
test('installer waits for shutdown; duplicate installation is rejected', async () => {
  let release
  const stopped = new Promise((resolve) => {
    release = resolve
  })
  const { updater, controller, events } = fixture({
    stopRuntime: async () => {
      events.push('stop')
      await stopped
    },
  })
  updater.emit('update-downloaded', { version: '0.2.4' })
  const installing = controller.install()
  await new Promise((resolve) => setImmediate(resolve))
  assert.deepEqual(events, ['gate', 'stop'])
  await assert.rejects(controller.install())
  release()
  await installing
  assert.deepEqual(events, ['gate', 'stop', 'install'])
})
test('failed shutdown unlocks work without running the installer', async () => {
  const { updater, controller, events } = fixture({
    stopRuntime: async () => {
      throw new Error('cannot close runtime')
    },
  })
  updater.emit('update-downloaded', { version: '0.2.4' })
  await assert.rejects(controller.install(), /cannot close runtime/)
  assert.deepEqual(events, ['gate', 'cancel'])
})
test('installer error events release the application action gate', async () => {
  const { updater, controller, events } = fixture()
  updater.quitAndInstall = () => updater.emit('error', { code: 'INSTALL_FAILED' })
  updater.emit('update-downloaded', { version: '0.2.4' })
  await controller.install()
  assert.deepEqual(events, ['gate', 'stop', 'cancel'])
  assert.equal(controller.snapshot().phase, 'error')
})
test('network failure preserves the current app and never logs exception secrets', async () => {
  const { updater, controller, events, log } = fixture()
  updater.checkForUpdates = async () => {
    throw new Error('secret=password token=123')
  }
  assert.equal((await controller.check()).phase, 'error')
  assert.deepEqual(events, [])
  assert.doesNotMatch(JSON.stringify(log), /password|token=123/)
})
