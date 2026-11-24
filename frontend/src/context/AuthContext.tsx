import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { createSession, revokeSession } from '../services/auth'
import { ApiError } from '../services/http'
import type { AccessSession, Credentials } from '../types/cloud'

interface AuthContextValue {
  session: AccessSession | null
  notice: string
  signIn: (credentials: Credentials) => Promise<void>
  signOut: () => Promise<void>
  expireSession: (token: string) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AccessSession | null>(null)
  const [notice, setNotice] = useState('')

  const signIn = useCallback(async (credentials: Credentials) => {
    const next = await createSession(credentials)
    setNotice('')
    setSession(next)
  }, [])

  const expireSession = useCallback((token: string) => {
    setSession((current) => (current?.access_token === token ? null : current))
    setNotice('Your session has expired or been revoked. Please sign in again.')
  }, [])

  const signOut = useCallback(async () => {
    if (!session) return
    try {
      await revokeSession(session.access_token)
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
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('AuthProvider is required')
  return context
}
