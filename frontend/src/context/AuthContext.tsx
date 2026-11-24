import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Button, InlineLoading } from '@carbon/react'
import { createSession, currentSession, revokeSession } from '../services/auth'
import { ApiError, errorMessage } from '../services/http'
import ErrorNotice from '../components/ErrorNotice'
import type { AccessSession, Credentials } from '../types/cloud'

interface AuthContextValue {
  session: AccessSession | null
  notice: string
  signIn: (credentials: Credentials) => Promise<void>
  signOut: () => Promise<void>
  expireSession: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AccessSession | null>(null)
  const [notice, setNotice] = useState('')
  const [restoring, setRestoring] = useState(true)
  const [restoreError, setRestoreError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setRestoring(true)
    setRestoreError('')
    currentSession(controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) setSession(next)
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) setSession(null)
        else setRestoreError(errorMessage(error))
      })
      .finally(() => {
        if (!controller.signal.aborted) setRestoring(false)
      })
    return () => controller.abort()
  }, [attempt])

  const signIn = useCallback(async (credentials: Credentials) => {
    const next = await createSession(credentials)
    setNotice('')
    setSession(next)
  }, [])

  const expireSession = useCallback(() => {
    setSession(null)
    setNotice('Your session has expired or been revoked. Please sign in again.')
  }, [])

  const signOut = useCallback(async () => {
    if (!session) return
    try {
      await revokeSession()
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) throw error
    }
    setNotice('')
    setSession(null)
  }, [session])

  const value = useMemo(
    () => ({ session, notice, signIn, signOut, expireSession }),
    [session, notice, signIn, signOut, expireSession],
  )
  return (
    <AuthContext.Provider value={value}>
      {restoring ? (
        <main className="session-check">
          <InlineLoading description="Restoring your session…" />
        </main>
      ) : restoreError ? (
        <main className="session-check">
          <ErrorNotice title="Could not restore your session" message={restoreError} />
          <Button onClick={() => setAttempt((value) => value + 1)}>Try again</Button>
        </main>
      ) : (
        children
      )}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('AuthProvider is required')
  return context
}
