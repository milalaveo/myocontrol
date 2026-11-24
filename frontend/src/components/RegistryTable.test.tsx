import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { RegistryRow } from '../types/cloud'
import RegistryTable from './RegistryTable'

const row: RegistryRow = {
  id: '4ef715f3-a86d-4572-b7a2-2016954eaa35',
  family: 'lda',
  condition: 'source_only',
}

describe('RegistryTable', () => {
  it('distinguishes missing rest observations from a measured zero error rate', () => {
    render(
      <RegistryTable
        collection="results"
        onSelect={vi.fn()}
        rows={[
          {
            ...row,
            accuracy: 0.9,
            macro_f1: 0.875,
            rest_false_activation_rate: null,
            rest_missing_reason: 'No rest windows',
          },
          { ...row, id: 'second', accuracy: 1, macro_f1: 1, rest_false_activation_rate: 0 },
        ]}
      />,
    )
    expect(screen.getByText('90.00%')).toBeVisible()
    expect(screen.getByText('87.50%')).toBeVisible()
    expect(screen.getByTitle('No rest windows')).toHaveTextContent('N/A')
    expect(screen.getByText('0.00%')).toBeVisible()
  })

  it('opens a published model by its full identifier', async () => {
    const select = vi.fn()
    const user = userEvent.setup()
    render(
      <RegistryTable
        collection="models"
        rows={[{ ...row, name: 'Source LDA', published_at: '2026-11-24T10:00:00Z' }]}
        onSelect={select}
      />,
    )
    expect(screen.getByText('Source LDA')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'View Source LDA' }))
    expect(select).toHaveBeenCalledExactlyOnceWith(row.id)
  })

  it('shows execution location and run status without implying cloud training', () => {
    render(
      <RegistryTable
        collection="runs"
        rows={[{ ...row, status: 'running', execution_location: 'local_workstation' }]}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText('Running')).toBeVisible()
    expect(screen.getByText('Local workstation')).toBeVisible()
    expect(screen.getByTitle(row.id)).toHaveTextContent('4ef715f3')
  })
})
