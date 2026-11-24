import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'
import { currentSession, revokeSession } from '../services/auth'
import { ApiError } from '../services/http'
import type { AccessSession } from '../types/cloud'

vi.mock('../services/auth', () => ({
  currentSession: vi.fn(),
  revokeSession: vi.fn(),
  createSession: vi.fn(),
}))
const session: AccessSession = {
  operator: { id: 'operator-1', display_name: 'Test operator', role: 'operator' },
}

function Probe() {
  const { session, signOut } = useAuth()
  return (
    <>
      <p>{session?.operator.display_name ?? 'Signed out'}</p>
      <button onClick={() => void signOut()}>Sign out</button>
    </>
  )
}

beforeEach(() => vi.resetAllMocks())

describe('Browser session restoration', () => {
  it('waits for the server before rendering protected content and restores without browser storage', async () => {
    let resolve!: (session: AccessSession) => void
    vi.mocked(currentSession).mockReturnValue(
      new Promise((complete) => {
        resolve = complete
      }),
    )
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    expect(screen.getByText('Restoring your session…')).toBeVisible()
    expect(screen.queryByText('Signed out')).not.toBeInTheDocument()
    await act(async () => resolve(session))
    expect(await screen.findByText('Test operator')).toBeVisible()
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('shows the signed-out view when the server rejects an expired cookie', async () => {
    vi.mocked(currentSession).mockRejectedValue(new ApiError('Session expired', 401))
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    expect(await screen.findByText('Signed out')).toBeVisible()
  })

  it('allows retry after an outage without prematurely displaying the login view', async () => {
    vi.mocked(currentSession)
      .mockRejectedValueOnce(new ApiError('Operator access unavailable', 503))
      .mockResolvedValueOnce(session)
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    expect(await screen.findByText('Operator access unavailable')).toBeVisible()
    expect(screen.queryByText('Signed out')).not.toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Test operator')).toBeVisible()
  })

  it('revokes the server session when signing out', async () => {
    vi.mocked(currentSession).mockResolvedValue(session)
    vi.mocked(revokeSession).mockResolvedValue(undefined)
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await screen.findByText('Test operator')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByText('Signed out')).toBeVisible()
    expect(revokeSession).toHaveBeenCalledExactlyOnceWith()
  })
})
