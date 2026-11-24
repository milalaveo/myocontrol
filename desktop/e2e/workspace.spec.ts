import { test, expect, _electron as electron, type ElectronApplication } from '@playwright/test'
import fs from 'node:fs/promises'
import { execFileSync } from 'node:child_process'
import os from 'node:os'
import path from 'node:path'

test('four-channel defaults, offline replay, persistence and renderer isolation', async () => {
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'myocontrol-e2e-'))
  const env: Record<string, string> = {
    ...Object.fromEntries(
      Object.entries(process.env).filter(
        (entry): entry is [string, string] => entry[1] !== undefined,
      ),
    ),
    MYOCONTROL_PROFILE: profile,
    MYOCONTROL_E2E: '1',
  }
  delete env.ELECTRON_RUN_AS_NODE
  const launch = () =>
    electron.launch(
      process.env.MYOCONTROL_TEST_EXECUTABLE
        ? {
            executablePath: process.env.MYOCONTROL_TEST_EXECUTABLE,
            args: [`--user-data-dir=${profile}`],
            env,
          }
        : { args: ['.'], env },
    )
  let application: ElectronApplication = await launch()
  try {
    let page = await application.firstWindow()
    await expect(page.getByText('Runtime connected', { exact: true })).toBeVisible()
    await expect(page.getByLabel('Channels', { exact: true })).toHaveValue('4')
    await expect(page.getByLabel('Sample rate', { exact: true })).toHaveValue('1000')
    expect(
      await page.evaluate(() => ({
        require: typeof (window as unknown as { require?: unknown }).require,
        storage: Object.keys(localStorage),
      })),
    ).toEqual({ require: 'undefined', storage: [] })
    await expect(page.getByRole('button', { name: 'Start capture', exact: true })).toBeDisabled()
    await page.getByRole('button', { name: 'Import demo recording', exact: true }).click()
    await page.getByRole('button', { name: 'Recordings', exact: true }).click()
    await expect(page.getByText('synthetic', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Replay', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Pause', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Resume', exact: true })).toBeEnabled()
    await expect(page.getByText('Neutral', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Stop', exact: true }).click()
    await page.screenshot({ path: 'test-results/workspace.png' })
    await application.close()
    application = await launch()
    page = await application.firstWindow()
    await expect(page.getByText('Runtime connected', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Recordings', exact: true }).click()
    await expect(page.getByRole('caption')).toHaveText('Local recordings (1)')
    await expect(page.getByText('synthetic', { exact: true })).toBeVisible()
  } finally {
    await application.close()
  }
})

test('sensor selector rescans without fake ports and remembers the explicit choice', async () => {
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'myocontrol-sensor-e2e-'))
  const env = {
    ...Object.fromEntries(
      Object.entries(process.env).filter(
        (entry): entry is [string, string] => entry[1] !== undefined,
      ),
    ),
    MYOCONTROL_PROFILE: profile,
    MYOCONTROL_E2E: '1',
  }
  delete (env as Record<string, string>).ELECTRON_RUN_AS_NODE
  const launch = () =>
    electron.launch(
      process.env.MYOCONTROL_TEST_EXECUTABLE
        ? {
            executablePath: process.env.MYOCONTROL_TEST_EXECUTABLE,
            args: [`--user-data-dir=${profile}`],
            env,
          }
        : { args: ['.'], env },
    )
  let application = await launch()
  try {
    let page = await application.firstWindow()
    await expect(page.getByText('Runtime connected', { exact: true })).toBeVisible()
    await expect(page.getByText('Turn on your BITalino and keep it nearby.')).not.toBeVisible()
    await expect(page.getByLabel('Bluetooth serial port or manual address')).not.toBeVisible()
    await page.getByRole('button', { name: 'How to connect BITalino', exact: true }).click()
    await expect(page.getByText('Turn on your BITalino and keep it nearby.')).toBeVisible()
    await page.getByRole('button', { name: 'How to connect BITalino', exact: true }).click()
    await page.getByRole('button', { name: 'Enter port manually', exact: true }).click()
    await expect(page.getByLabel('Bluetooth serial port or manual address')).toHaveValue('')
    // A controlled OS-discovery boundary; no real radio, pairing or port is opened in this UI test.
    await application.evaluate(({ ipcMain }) => {
      let scans = 0
      ipcMain.removeHandler('runtime:request')
      ipcMain.handle('runtime:request', (_event, method: string) => {
        if (method !== 'scan_sensors') throw new Error('Unexpected test command')
        scans += 1
        return {
          devices:
            scans <= 2
              ? [
                  {
                    id: 'serial:COM254',
                    address: 'COM254',
                    name: 'BITalino fixture',
                    transport: 'bluetooth-serial',
                    selectable: true,
                    paired: true,
                    likely_sensor: true,
                  },
                  {
                    id: 'serial:COM253',
                    address: 'COM253',
                    name: 'Incoming fixture',
                    transport: 'bluetooth-serial',
                    selectable: false,
                    paired: true,
                    likely_sensor: false,
                  },
                ]
              : [],
          warnings: [],
          scope: 'test fixture',
        }
      })
    })
    await page.getByRole('button', { name: 'Scan sensors', exact: true }).click()
    await expect(page.getByRole('option', { name: /Incoming fixture/ })).toBeDisabled()
    await expect(page.getByLabel('Bluetooth serial port or manual address')).toHaveValue('')
    await page.getByLabel('Discovered sensor or serial port').selectOption('serial:COM254')
    await expect
      .poll(() => page.evaluate(() => window.myocontrol.sensorSelection()))
      .toEqual({ address: 'COM254', label: 'BITalino fixture' })
    const sensorOptions = page.getByRole('option', {
      name: 'BITalino fixture - COM254',
      exact: true,
    })
    await expect(sensorOptions).toHaveCount(1)
    await page.getByRole('button', { name: 'Rescan sensors', exact: true }).click()
    await expect(sensorOptions).toHaveCount(1)
    await expect(page.getByLabel('Discovered sensor or serial port')).toHaveValue('serial:COM254')
    await page.getByRole('button', { name: 'Rescan sensors', exact: true }).click()
    await expect(sensorOptions).toHaveCount(1)
    await expect(
      page.getByText(
        'No sensors or serial ports found. Pair the sensor in Bluetooth settings and rescan.',
      ),
    ).toBeVisible()
    await expect(page.getByLabel('Bluetooth serial port or manual address')).toHaveValue('COM254')
    await application.close()
    application = await launch()
    page = await application.firstWindow()
    await expect(page.getByText('Runtime connected', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Enter port manually', exact: true }).click()
    await expect(page.getByLabel('Bluetooth serial port or manual address')).toHaveValue('COM254')
    expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([])
  } finally {
    await application.close()
  }
})

test('personal calibration trains selected repetitions and restores the model after restart', async () => {
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'myocontrol-personal-e2e-'))
  const runtimeRoot = path.resolve('../local-runtime')
  const python =
    process.env.MYOCONTROL_PYTHON ||
    path.join(
      runtimeRoot,
      '.venv',
      process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
    )
  execFileSync(
    python,
    [
      '-c',
      `
import sys
from pathlib import Path
import numpy as np
from myocontrol_runtime.storage.store import Store
store = Store(Path(sys.argv[1]) / 'local')
meta = {'sample_rate_hz':1000, 'channel_map':[0,1], 'source_kind':'device', 'source_name':'BITalino', 'source_version':'e2e-fixture', 'units':'ADC counts'}
rng = np.random.default_rng(22)
for gesture, amplitude in [('rest',[1.5,1.5]),('fist',[6,8]),('finger_spread',[3,24])]:
    for repetition in range(5):
        identifier = store.create(meta, 'fixture-participant', 'calibration', gesture)
        samples = np.rint(512 + rng.normal(size=(4000,2))*amplitude).tolist()
        store.append(identifier, 0, samples)
        store.finish(identifier, 'completed', 'Synthetic UI test fixture')
`,
      profile,
    ],
    { env: { ...process.env, PYTHONPATH: runtimeRoot }, windowsHide: true },
  )
  const env: Record<string, string> = {
    ...Object.fromEntries(
      Object.entries(process.env).filter(
        (entry): entry is [string, string] => entry[1] !== undefined,
      ),
    ),
    MYOCONTROL_PROFILE: profile,
    MYOCONTROL_E2E: '1',
  }
  delete env.ELECTRON_RUN_AS_NODE
  const launch = () =>
    electron.launch(
      process.env.MYOCONTROL_TEST_EXECUTABLE
        ? {
            executablePath: process.env.MYOCONTROL_TEST_EXECUTABLE,
            args: [`--user-data-dir=${profile}`],
            env,
          }
        : { args: ['.'], env },
    )
  let application = await launch()
  try {
    let page = await application.firstWindow()
    await expect(page.getByText('Runtime connected', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Recordings', exact: true }).click()
    const train = page.getByRole('button', { name: 'Train and use personal model', exact: true })
    await expect(train).toBeDisabled()
    await page.getByRole('button', { name: 'Select latest 10 per gesture', exact: true }).click()
    await expect(train).toBeEnabled()
    await train.click()
    await expect(page.getByLabel('Personal model evaluation')).toContainText(
      '4 train / 1 test repetitions',
    )
    const initial = await page.evaluate(
      async () => (await window.myocontrol.request<import('../src/types').Status>('status')).model,
    )
    expect(initial?.channels).toBe(2)
    expect(initial?.calibration?.test_repetitions).toEqual({ rest: 1, fist: 1, finger_spread: 1 })
    await application.close()
    application = await launch()
    page = await application.firstWindow()
    await expect(page.getByText('Runtime connected', { exact: true })).toBeVisible()
    const restored = await page.evaluate(
      async () => (await window.myocontrol.request<import('../src/types').Status>('status')).model,
    )
    expect(restored).toEqual(initial)
    await page.getByRole('button', { name: 'Clear model', exact: true }).click()
    await expect
      .poll(() =>
        page.evaluate(
          async () =>
            (await window.myocontrol.request<import('../src/types').Status>('status')).model,
        ),
      )
      .toBeNull()
  } finally {
    await application.close()
  }
})
