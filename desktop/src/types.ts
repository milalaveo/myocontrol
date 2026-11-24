export type Metadata = {
  sample_rate_hz: number
  channel_map: number[]
  source_kind: string
  source_name: string
  units: string
}
export type Recording = {
  id: string
  metadata: Metadata
  participant_key: string
  purpose: string
  gesture: string | null
  created_at: string
  status: string
  sample_count: number
  operator_id: string | null
}
export type SyncEntry = {
  id: string
  recording_id: string
  state: string
  attempts: number
  error: string | null
}
export type SyncStatus = { connected: boolean; operator_id: string | null; entries: SyncEntry[] }
export type Status = {
  state: string
  mode: string | null
  recording_id: string | null
  sample_count: number
  command: string
  message: string
  recognition: string
  metadata?: Metadata
  model: { name: string; sample_rate_hz: number; classes: string[] } | null
  cloud: SyncStatus
}
export type Signal = {
  recording_id: string
  start_sample: number
  sample_stride: number
  sample_rate_hz: number
  channel_map: number[]
  samples: number[][]
  sample_count: number
}
export type Identity = {
  connected: boolean
  operator_id?: string
  display_name?: string
  base?: string
  persisted?: boolean
}
export type RuntimeEvent = { event: string; data: unknown }
export type Library = {
  items: Recording[]
  calibration: {
    participant_key: string
    gesture: string
    sample_rate_hz: number
    channel_map: number[]
    units: string
    repetitions: number
    seconds: number
  }[]
}
declare global {
  interface Window {
    myocontrol: {
      request<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T>
      subscribe(callback: (event: RuntimeEvent) => void): () => void
      importRecording(participantKey: string): Promise<Recording | null>
      importDemo(): Promise<Recording>
      importModel(): Promise<unknown>
      exportRecording(identifier: string): Promise<unknown>
      restart(): Promise<Status>
      identity(): Promise<Identity>
      login(body: { base: string; email: string; password: string }): Promise<Identity>
      logout(): Promise<Identity>
    }
  }
}
