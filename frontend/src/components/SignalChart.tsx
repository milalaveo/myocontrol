import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { Signal } from '../types'

export const colors = ['#b6ee9d', '#8ea9ff', '#efbc7c', '#c89ef0']

export default function SignalChart({ signal, enabled }: { signal: Signal; enabled: boolean[] }) {
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!host.current) return
    const container = host.current
    // A bounded display projection keeps the original API signal intact.
    const stride = Math.max(1, Math.ceil(signal.samples.length / 3000))
    const rows = signal.samples.filter((_, i) => i % stride === 0)
    const data: uPlot.AlignedData = [rows.map((_, i) => i * stride / signal.sample_rate_hz), ...[0, 1, 2, 3].map(c => rows.map(r => r[c]))]
    const chart = new uPlot({
      width: Math.max(250, container.clientWidth), height: 265,
      scales: { x: { time: false } },
      legend: { show: false },
      cursor: { drag: { x: true, y: false }, points: { size: 4 } },
      axes: [
        { stroke: '#8b94a5', grid: { stroke: '#252c39', width: 1 }, ticks: { show: false }, values: (_, values) => values.map(v => `${v.toFixed(2)}s`), font: '11px system-ui' },
        { stroke: '#8b94a5', size: 65, grid: { stroke: '#252c39', width: 1 }, ticks: { show: false }, font: '11px system-ui' },
      ],
      series: [{}, ...colors.map((color, c) => ({ label: `Channel ${c + 1}`, stroke: color, width: 1, show: enabled[c] }))],
    }, data, container)
    const observer = new ResizeObserver(entries => chart.setSize({ width: Math.max(250, entries[0].contentRect.width), height: 265 }))
    observer.observe(container)
    return () => { observer.disconnect(); chart.destroy() }
  }, [signal, enabled])
  return <div ref={host} className="signal-chart" role="img" aria-label={`Four-channel EMG recording, ${signal.samples.length} samples at ${signal.sample_rate_hz} Hz. Drag horizontally to zoom; double-click to reset.`} />
}
