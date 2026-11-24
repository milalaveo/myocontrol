export function readable(value: string) {
  const labels: Record<string, string> = {
    id: 'ID',
    run_id: 'Run ID',
    model_id: 'Model ID',
    manifest_id: 'Manifest ID',
    macro_f1: 'Macro F1',
    manifest_sha256: 'Manifest SHA-256',
    sha256: 'SHA-256',
  }
  return labels[value] ?? value.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())
}

export function percentage(value?: number | null) {
  return value == null ? 'N/A' : `${(value * 100).toFixed(2)}%`
}

export function statusColor(status?: string) {
  switch (status) {
    case 'succeeded':
      return 'green' as const
    case 'running':
      return 'blue' as const
    case 'failed':
      return 'red' as const
    case 'interrupted':
      return 'warm-gray' as const
    default:
      return 'gray' as const
  }
}
