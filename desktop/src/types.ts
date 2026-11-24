export type CalibrationAssessment = {
  participant_key: string
  class_order: string[]
  confusion_matrix: number[][]
  accuracy: number
  balanced_accuracy: number
  rest_false_activation_rate: number
  train_repetitions: Record<string, number>
  test_repetitions: Record<string, number>
  test_windows: number
  scope: string
}
export type UpdateStatus = import('../electron/update-controller.js').UpdateStatus
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
  model: {
    name: string
    channels: number
    sample_rate_hz: number
    classes: string[]
    calibration?: CalibrationAssessment | null
  } | null
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
      sensorSelection(): Promise<{ address: string; label: string } | null>
      selectSensor(value: { address: string; label: string }): Promise<void>
      openBluetoothSettings(): Promise<void>
      updateStatus(): Promise<UpdateStatus>
      checkUpdates(): Promise<UpdateStatus>
      installUpdate(): Promise<UpdateStatus>
      subscribeUpdates(callback: (status: UpdateStatus) => void): () => void
    }
  }
}
