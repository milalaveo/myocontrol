import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { Signal } from '../types'

const colors = ['#0f62fe', '#009d9a', '#8a3ffc', '#da1e28', '#b28600', '#198038']

export default function SignalChart({ signal }: { signal: Signal | null }) {
  const host = useRef<HTMLDivElement>(null)
  const plot = useRef<uPlot | null>(null)
  const points = useRef<number[][]>([])
  const identifier = useRef('')
  const mapping = signal?.channel_map.join(',') ?? '0,1,2,3'
  useEffect(() => {
    if (!host.current) return
    const container = host.current
    const channels = mapping.split(',').map(Number)
    points.current = Array.from({ length: channels.length + 1 }, () => [])
    identifier.current = ''
    const chart = new uPlot(
      {
        width: Math.max(300, container.clientWidth),
        height: 280,
        scales: { x: { time: false } },
        cursor: { show: false },
        axes: [
          {
            stroke: '#525252',
            grid: { stroke: '#e0e0e0' },
            values: (_, values) => values.map((v) => `${v.toFixed(1)}s`),
          },
          { stroke: '#525252', grid: { stroke: '#e0e0e0' }, size: 65 },
        ],
        series: [
          { label: 'Time' },
          ...channels.map((channel, index) => ({
            label: `A${channel + 1}`,
            stroke: colors[index],
            width: 1,
          })),
        ],
      },
      points.current as uPlot.AlignedData,
      container,
    )
    plot.current = chart
    const observer = new ResizeObserver(([entry]) =>
      chart.setSize({ width: Math.max(300, entry.contentRect.width), height: 280 }),
    )
    observer.observe(container)
    return () => {
      observer.disconnect()
      chart.destroy()
      plot.current = null
    }
  }, [mapping])
  useEffect(() => {
    if (!signal || !plot.current) return
    if (identifier.current !== signal.recording_id || signal.start_sample === 0) {
      points.current = Array.from({ length: signal.channel_map.length + 1 }, () => [])
      identifier.current = signal.recording_id
    }
    signal.samples.forEach((sample, index) => {
      points.current[0].push(
        (signal.start_sample + index * signal.sample_stride) / signal.sample_rate_hz,
      )
      sample.forEach((value, channel) => points.current[channel + 1].push(value))
    })
    points.current = points.current.map((series) => series.slice(-3000))
    plot.current.setData(points.current as uPlot.AlignedData)
  }, [signal])
  return (
    <div
      ref={host}
      className="signal-chart"
      role="img"
      aria-label={`${mapping.split(',').length}-channel signal waveform`}
    />
  )
}
