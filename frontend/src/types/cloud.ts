export type Collection = 'runs' | 'models' | 'results'
export type ModelFamily = 'lda' | 'svm' | 'mlp'
export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'interrupted'

export interface RegistryRow {
  id: string
  family: ModelFamily
  condition: string
  status?: RunStatus
  name?: string
  published_at?: string
  accuracy?: number
  macro_f1?: number
  rest_false_activation_rate?: number | null
  rest_missing_reason?: string | null
  execution_location?: string
}

export interface RegistryPage {
  items: RegistryRow[]
  next_offset: number | null
}

export interface ConfusionCount {
  actual_class: string
  predicted_class: string
  count: number
}

export type RegistryDetail = Record<string, unknown> & { confusion_counts?: ConfusionCount[] }

export interface AccessSession {
  operator: { id: string; display_name: string; role: string }
}

export interface CurrentOperator {
  operator_id: string
  display_name: string
  role: string
  scope: 'web' | 'desktop' | 'training_worker'
  expires_at: string
}

export interface Recording {
  id: string
  local_recording_id: string
  source_participant_key: string
  source_kind: 'synthetic' | 'dataset' | 'device'
  source_name: string
  sample_count: number
  sample_rate_hz: number
  channel_count: number
  channel_map: number[]
  units: string
  original_signal_key: string
  original_start_sample: number
  original_end_sample: number
  received_at: string
}

export interface RecordingPage {
  items: Recording[]
  next_offset: number | null
}

export interface Credentials {
  email: string
  password: string
}
