import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { ApiError, errorMessage } from '../services/http'
import { getRegistryDetail, listRegistry } from '../services/registry'
import type { Collection, RegistryDetail, RegistryPage } from '../types/cloud'

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; page: RegistryPage; detail: RegistryDetail | null }

export function useRegistry(
  collection: Collection,
  offset: number,
  id: string | undefined,
  refresh: number,
) {
  const { session, expireSession } = useAuth()
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    if (!session) return
    const controller = new AbortController()
    setState({ status: 'loading' })

    async function load() {
      try {
        const result = id
          ? {
              page: { items: [], next_offset: null },
              detail: await getRegistryDetail(collection, id, controller.signal),
            }
          : {
              page: await listRegistry(collection, offset, controller.signal),
              detail: null,
            }
        if (!controller.signal.aborted) setState({ status: 'success', ...result })
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) expireSession()
        else setState({ status: 'error', message: errorMessage(error) })
      }
    }

    void load()
    return () => controller.abort()
  }, [collection, offset, id, refresh, session, expireSession])

  return state
}
