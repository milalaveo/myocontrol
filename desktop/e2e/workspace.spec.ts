import { test, expect, _electron as electron, type ElectronApplication } from '@playwright/test'
import fs from 'node:fs/promises'
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
