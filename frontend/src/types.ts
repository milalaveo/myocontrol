export type Participant = { id: string; pseudonym: string }
export type Recording = { id: string; participant_id: string; sample_rate_hz: number; sample_count: number; artifact_sha256: string }
export type Signal = { sample_rate_hz: number; samples: number[][] }
export type Prediction = { start_sample: number; gesture: string; command: string }
export type Replay = { id: string; status: string; error: string | null; result: { predictions?: Prediction[]; processing_p95_ms?: number } | null }
export type Experiment = { id: string; status: string; error: string | null; metrics: Record<string, unknown> | null }
export const gestures = [
  { id: 'rest', name: 'Rest', detail: 'Relaxed neutral position' },
  { id: 'fist', name: 'Fist', detail: 'Close all fingers' },
  { id: 'finger_spread', name: 'Finger spread', detail: 'Extend and spread fingers' },
  { id: 'wrist_flexion', name: 'Wrist flexion', detail: 'Bend the wrist forward' },
  { id: 'wrist_extension', name: 'Wrist extension', detail: 'Extend the wrist back' },
]
export const gestureName = (id: string) => gestures.find(g => g.id === id)?.name ?? id
