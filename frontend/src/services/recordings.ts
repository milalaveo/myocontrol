import { requestJson } from './http'
import type { RecordingPage } from '../types/cloud'
import { PAGE_SIZE } from './registry'

export function listRecordings(offset: number, signal: AbortSignal) {
  return requestJson<RecordingPage>(`cloud/v1/recordings?limit=${PAGE_SIZE}&offset=${offset}`, {
    signal,
  })
}

export async function downloadRecording(id: string, signal: AbortSignal) {
  const recording = await requestJson<unknown>(
    `cloud/v1/recordings/${encodeURIComponent(id)}/signal`,
    { signal },
  )
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(recording)], { type: 'application/json' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `recording-${id}.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
