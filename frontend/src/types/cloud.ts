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
  access_token: string
  operator: { id: string; display_name: string; role: string }
}

export interface Credentials {
  email: string
  password: string
}
