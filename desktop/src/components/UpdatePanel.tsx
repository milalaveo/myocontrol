import { useEffect, useState } from 'react'
import { Button } from '@carbon/react'
import type { UpdateStatus } from '../types'

export default function UpdatePanel({ active }: { active: boolean }) {
  const [update, setUpdate] = useState<UpdateStatus | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const unsubscribe = window.myocontrol.subscribeUpdates(setUpdate)
    void window.myocontrol
      .updateStatus()
      .then(setUpdate)
      .catch(() => {})
    return unsubscribe
  }, [])
  if (!update) return null
  const working = ['checking', 'available', 'downloading', 'installing'].includes(update.phase)
  return (
    <div className="update-panel" aria-label="Application updates">
      <p>App {update.version}</p>
      <p role="status" aria-live="polite">
        {update.message}
        {update.phase === 'downloading' && ` ${Math.floor(update.progress ?? 0)}%`}
      </p>
      {update.phase === 'ready' ? (
        <Button
          size="sm"
          kind="secondary"
          disabled={active}
          onClick={() => {
            setError('')
            void window.myocontrol
              .installUpdate()
              .catch((failure: unknown) =>
                setError(
                  failure instanceof Error ? failure.message : 'Could not install the update',
                ),
              )
          }}
        >
          Restart and update
        </Button>
      ) : update.phase !== 'disabled' ? (
        <Button
          size="sm"
          kind="ghost"
          disabled={working}
          onClick={() => {
            setError('')
            void window.myocontrol
              .checkUpdates()
              .then(setUpdate)
              .catch(() => setError('Could not check for updates'))
          }}
        >
          Check for updates
        </Button>
      ) : null}
      {update.phase === 'ready' && active && <p>Finish capture or replay before restarting.</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
