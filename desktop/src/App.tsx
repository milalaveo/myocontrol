import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import {
  Button,
  Form,
  Header,
  HeaderName,
  InlineLoading,
  InlineNotification,
  NumberInput,
  PasswordInput,
  Select,
  SelectItem,
  Tag,
  TextInput,
  Tile,
} from '@carbon/react'
import { Cloud, DataBase, Play, Recording as RecordingIcon, Stop } from '@carbon/icons-react'
import SignalChart from './components/SignalChart'
import type { Identity, Library, Signal, Status, SyncStatus } from './types'

const emptyLibrary: Library = { items: [], calibration: [] }
const HandScene = lazy(() => import('./components/HandScene'))
const gestures = ['rest', 'fist', 'finger_spread', 'wrist_flexion', 'wrist_extension']
const message = (error: unknown) =>
  error instanceof Error
    ? error.message.replace(/^Error invoking remote method '[^']+': Error: /, '')
    : 'The local operation failed'

export default function App() {
  const [page, setPage] = useState('Acquisition')
  const [status, setStatus] = useState<Status | null>(null)
  const [library, setLibrary] = useState<Library>(emptyLibrary)
  const [signal, setSignal] = useState<Signal | null>(null)
  const [prediction, setPrediction] = useState<{ gesture: string; processing_ms: number } | null>(
    null,
  )
  const [sync, setSync] = useState<SyncStatus>({ connected: false, operator_id: null, entries: [] })
  const [identity, setIdentity] = useState<Identity>({ connected: false })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [participant, setParticipant] = useState('participant-001')
  const [address, setAddress] = useState('')
  const [channels, setChannels] = useState(4)
  const [duration, setDuration] = useState(10)
  const [rate, setRate] = useState('1000')
  const [purpose, setPurpose] = useState('research')
  const [gesture, setGesture] = useState('rest')
  const [base, setBase] = useState('http://localhost:8000')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const active = !!status && ['connecting', 'running', 'paused', 'stopping'].includes(status.state)
  const refresh = useCallback(async () => {
    const [nextStatus, nextLibrary, nextIdentity] = await Promise.all([
      window.myocontrol.request<Status>('status'),
      window.myocontrol.request<Library>('recordings'),
      window.myocontrol.identity(),
    ])
    setStatus(nextStatus)
    setLibrary(nextLibrary)
    setSync(nextStatus.cloud)
    setIdentity(nextIdentity)
  }, [])
  const act = async (operation: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await operation()
      await refresh()
    } catch (failure) {
      setError(message(failure))
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => {
    void refresh().catch((failure) => setError(message(failure)))
    return window.myocontrol.subscribe((event) => {
      if (event.event === 'status') {
        const next = event.data as Status
        setStatus(next)
        if (next.state !== 'running') setPrediction(null)
      }
      if (event.event === 'signal') setSignal(event.data as Signal)
      if (event.event === 'prediction')
        setPrediction(event.data as { gesture: string; processing_ms: number })
      if (event.event === 'sync') setSync(event.data as SyncStatus)
      if (event.event === 'recordings' || event.event === 'cloud')
        void refresh().catch((failure) => setError(message(failure)))
      if (event.event === 'runtime-error') {
        setError('Local runtime stopped. Restart it to recover saved recordings.')
        setStatus(null)
        setPrediction(null)
      }
    })
  }, [refresh])
  const startCapture = () =>
    act(() =>
      window.myocontrol.request('start_capture', {
        address,
        participant_key: participant,
        sample_rate_hz: Number(rate),
        channels: Array.from({ length: channels }, (_, index) => index),
        duration_seconds: duration,
        purpose,
        gesture: purpose === 'calibration' ? gesture : null,
      }),
    )
  return (
    <>
      <Header aria-label="MyoControl">
        <HeaderName prefix="MyoControl">Desktop</HeaderName>
        <div className="header-meta">Local signal workspace</div>
      </Header>
      <aside className="navigation" aria-label="Workspace navigation">
        <p className="nav-label">WORKSPACE</p>
        {[
          ['Acquisition', RecordingIcon],
          ['Recordings', DataBase],
          ['Cloud sync', Cloud],
        ].map(([label, Icon]) => {
          const name = label as string
          const Symbol = Icon as typeof Cloud
          return (
            <button
              className={page === name ? 'selected' : ''}
              key={name}
              onClick={() => setPage(name)}
              aria-current={page === name ? 'page' : undefined}
            >
              <Symbol size={20} />
              {name}
            </button>
          )
        })}
        <div className="nav-footer">
          <Tag type={status ? 'green' : 'red'}>
            {status ? 'Runtime connected' : 'Runtime unavailable'}
          </Tag>
          <p>Capture and recognition run on this computer.</p>
        </div>
      </aside>
      <main>
        <div className="page-heading">
          <div>
            <p className="eyebrow">MyoControl / {page}</p>
            <h1>{page}</h1>
          </div>
          <Tag type={active ? 'blue' : 'gray'}>{status?.state ?? 'offline'}</Tag>
        </div>
        {error && (
          <InlineNotification
            kind="error"
            title="Operation failed"
            subtitle={error}
            onCloseButtonClick={() => setError('')}
          />
        )}
        {!status && (
          <Button
            kind="secondary"
            onClick={() => void act(() => window.myocontrol.restart())}
            disabled={busy}
          >
            Restart local runtime
          </Button>
        )}
        {busy && <InlineLoading description="Processing…" />}
        {page === 'Acquisition' && (
          <>
            <div className="workspace-grid">
              <Tile>
                <h2>Signal source</h2>
                <p className="description">
                  BITalino over Bluetooth. Pair the device in your operating system before
                  connecting.
                </p>
                <Form
                  onSubmit={(event) => {
                    event.preventDefault()
                    void startCapture()
                  }}
                >
                  <TextInput
                    id="participant"
                    labelText="Participant pseudonym"
                    value={participant}
                    onChange={(event) => setParticipant(event.target.value)}
                    required
                    maxLength={100}
                    disabled={active}
                    helperText="Use a research identifier without personal details."
                  />
                  <TextInput
                    id="device"
                    labelText="Bluetooth address or paired serial port"
                    placeholder="COM5, /dev/… or device MAC address"
                    value={address}
                    onChange={(event) => setAddress(event.target.value)}
                    required
                    maxLength={200}
                    disabled={active}
                    helperText="On macOS use the paired Bluetooth serial port."
                  />
                  <div className="form-row">
                    <Select
                      id="channels"
                      labelText="Channels"
                      value={channels}
                      onChange={(event) => setChannels(Number(event.target.value))}
                      disabled={active}
                    >
                      {[1, 2, 3, 4, 5, 6].map((count) => (
                        <SelectItem
                          key={count}
                          value={count}
                          text={`${count} · A1${count > 1 ? `–A${count}` : ''}`}
                        />
                      ))}
                    </Select>
                    <Select
                      id="rate"
                      labelText="Sample rate"
                      value={rate}
                      onChange={(event) => setRate(event.target.value)}
                      disabled={active}
                    >
                      {[1, 10, 100, 1000].map((value) => (
                        <SelectItem key={value} value={value} text={`${value} Hz`} />
                      ))}
                    </Select>
                  </div>
                  <NumberInput
                    id="duration"
                    label="Duration (seconds)"
                    min={1}
                    max={1800}
                    value={duration}
                    onChange={(_, state) => setDuration(Number(state.value))}
                    disabled={active}
                  />
                  <Select
                    id="purpose"
                    labelText="Recording purpose"
                    value={purpose}
                    onChange={(event) => setPurpose(event.target.value)}
                    disabled={active}
                  >
                    <SelectItem value="research" text="Research recording" />
                    <SelectItem value="calibration" text="Calibration repetition" />
                  </Select>
                  {purpose === 'calibration' && (
                    <Select
                      id="gesture"
                      labelText="Gesture label"
                      value={gesture}
                      onChange={(event) => setGesture(event.target.value)}
                      disabled={active}
                    >
                      {gestures.map((code) => (
                        <SelectItem key={code} value={code} text={code.replaceAll('_', ' ')} />
                      ))}
                    </Select>
                  )}
                  <Button
                    type="submit"
                    renderIcon={RecordingIcon}
                    disabled={active || busy || !status || !address.trim() || !participant.trim()}
                  >
                    Start capture
                  </Button>
                </Form>
              </Tile>
              <div className="signal-column">
                <Tile>
                  <div className="section-heading">
                    <div>
                      <h2>Signal monitor</h2>
                      <p className="description">
                        {signal
                          ? `${signal.channel_map.length} channels · ${signal.sample_rate_hz} Hz · ${status?.metadata?.units ?? 'source units'}`
                          : '4 channels · A1–A4 · 1000 Hz default'}
                      </p>
                    </div>
                    <Tag type={status?.metadata?.source_kind === 'synthetic' ? 'purple' : 'gray'}>
                      {status?.metadata?.source_kind ?? 'No source'}
                    </Tag>
                  </div>
                  <SignalChart signal={signal} />
                  <div className="session-bar">
                    <span>{status?.message ?? 'Waiting for runtime'}</span>
                    <span>
                      {(signal?.sample_count ?? status?.sample_count ?? 0).toLocaleString()} samples
                    </span>
                  </div>
                  <div className="actions">
                    <Button
                      kind="danger"
                      renderIcon={Stop}
                      disabled={!active || busy || status?.state === 'stopping'}
                      onClick={() => void act(() => window.myocontrol.request('stop'))}
                    >
                      Stop
                    </Button>
                    {status?.mode === 'replay' && (
                      <Button
                        kind="secondary"
                        disabled={!active || busy}
                        onClick={() =>
                          void act(() =>
                            window.myocontrol.request(
                              status.state === 'paused' ? 'resume' : 'pause',
                            ),
                          )
                        }
                      >
                        {status.state === 'paused' ? 'Resume' : 'Pause'}
                      </Button>
                    )}
                    <Button
                      kind="tertiary"
                      disabled={active || busy}
                      onClick={() => void act(() => window.myocontrol.importDemo())}
                    >
                      Import demo recording
                    </Button>
                  </div>
                  <p className="caption">
                    The demo is a synthetic waveform for testing replay. Open Recordings to play it.
                  </p>
                </Tile>
                <Tile>
                  <div className="section-heading">
                    <h2>Live recognition</h2>
                    <Tag type="blue">Local inference</Tag>
                  </div>
                  <p className="recognition" aria-live="polite">
                    {status?.state === 'running' && prediction
                      ? prediction.gesture.replaceAll('_', ' ')
                      : 'Neutral'}
                  </p>
                  <Suspense fallback={<InlineLoading description="Loading hand preview…" />}>
                    <HandScene
                      gesture={
                        status?.state === 'running' && prediction ? prediction.gesture : 'rest'
                      }
                    />
                  </Suspense>
                  <p>{status?.model?.name ?? 'Select an exported LDA model JSON'}</p>
                  <p className="description">
                    {status?.recognition ?? 'No model selected'}
                    {prediction ? ` · ${prediction.processing_ms.toFixed(2)} ms processing` : ''}
                  </p>
                  <div className="actions">
                    <Button
                      kind="tertiary"
                      disabled={active || busy}
                      onClick={() => void act(() => window.myocontrol.importModel())}
                    >
                      Import model
                    </Button>
                    <Button
                      kind="ghost"
                      disabled={active || busy || !status?.model}
                      onClick={() => void act(() => window.myocontrol.request('clear_model'))}
                    >
                      Clear model
                    </Button>
                  </div>
                  <p className="caption">
                    Calibration capture collects labelled repetitions. Model adaptation requires an
                    adaptation artifact and is not available in this build.
                  </p>
                </Tile>
              </div>
            </div>
          </>
        )}
        {page === 'Recordings' && (
          <>
            <div className="actions">
              <Button
                disabled={active || busy}
                onClick={() => void act(() => window.myocontrol.importRecording(participant))}
              >
                Import signal JSON
              </Button>
              <Button
                kind="tertiary"
                disabled={active || busy}
                onClick={() => void act(() => window.myocontrol.importDemo())}
              >
                Import demo recording
              </Button>
            </div>
            <p className="description">
              Recordings are saved in this computer’s application profile. Originals retain their
              sample rate, channel count and source identity.
            </p>
            <div className="table-wrap">
              <table>
                <caption>Local recordings ({library.items.length})</caption>
                <thead>
                  <tr>
                    {['Created / participant', 'Source', 'Signal', 'Status', 'Actions'].map(
                      (label) => (
                        <th key={label}>{label}</th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {library.items.map((row) => (
                    <tr key={row.id}>
                      <td>
                        {new Date(row.created_at).toLocaleString()}
                        <small>
                          {row.participant_key} · {row.purpose}
                          {row.gesture ? ` / ${row.gesture}` : ''}
                        </small>
                      </td>
                      <td>
                        <Tag type={row.metadata.source_kind === 'synthetic' ? 'purple' : 'gray'}>
                          {row.metadata.source_kind}
                        </Tag>
                      </td>
                      <td>
                        {row.metadata.channel_map.length} channels · {row.metadata.sample_rate_hz}{' '}
                        Hz
                        <small>
                          {(row.sample_count / row.metadata.sample_rate_hz).toFixed(2)} s ·{' '}
                          {row.sample_count.toLocaleString()} samples
                        </small>
                      </td>
                      <td>{row.status}</td>
                      <td>
                        <div className="row-actions">
                          <Button
                            size="sm"
                            kind="ghost"
                            renderIcon={Play}
                            disabled={active || busy || !row.sample_count}
                            onClick={() => {
                              setSignal(null)
                              setPrediction(null)
                              setPage('Acquisition')
                              void act(() =>
                                window.myocontrol.request('start_replay', { recording_id: row.id }),
                              )
                            }}
                          >
                            Replay
                          </Button>
                          <Button
                            size="sm"
                            kind="ghost"
                            disabled={busy || row.status === 'recording'}
                            onClick={() =>
                              void act(() => window.myocontrol.exportRecording(row.id))
                            }
                          >
                            Export
                          </Button>
                          <Button
                            size="sm"
                            kind="ghost"
                            disabled={
                              busy ||
                              !sync.connected ||
                              !['completed', 'stopped'].includes(row.status) ||
                              !row.sample_count ||
                              (!!row.operator_id && row.operator_id !== sync.operator_id)
                            }
                            onClick={() =>
                              void act(() =>
                                window.myocontrol.request('queue_upload', { recording_id: row.id }),
                              )
                            }
                          >
                            Sync
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!library.items.length && (
                <p className="empty">
                  No recordings yet. Capture a signal or import the synthetic demo.
                </p>
              )}
            </div>
            <Tile>
              <h2>Calibration data collected</h2>
              {library.calibration.length ? (
                library.calibration.map((item) => (
                  <p
                    key={`${item.participant_key}:${item.gesture}:${item.sample_rate_hz}:${item.channel_map}:${item.units}`}
                  >
                    {item.participant_key} · {item.gesture.replaceAll('_', ' ')} ·{' '}
                    {item.channel_map.length} channels / {item.sample_rate_hz} Hz ·{' '}
                    {item.repetitions} repetitions · {item.seconds.toFixed(1)} seconds
                  </p>
                ))
              ) : (
                <p className="description">No labelled calibration repetitions yet.</p>
              )}
            </Tile>
          </>
        )}
        {page === 'Cloud sync' && (
          <div className="cloud-grid">
            <Tile>
              <h2>Operator account</h2>
              <p className="description">
                Cloud stores published recordings and research metadata. Capture and replay continue
                offline.
              </p>
              {identity.connected ? (
                <>
                  <p>{identity.display_name}</p>
                  <p className="description">{identity.base}</p>
                  <Button
                    kind="tertiary"
                    disabled={busy}
                    onClick={() => void act(() => window.myocontrol.logout())}
                  >
                    Sign out
                  </Button>
                </>
              ) : (
                <Form
                  onSubmit={(event) => {
                    event.preventDefault()
                    void act(async () => {
                      try {
                        await window.myocontrol.login({ base, email, password })
                      } finally {
                        setPassword('')
                      }
                    })
                  }}
                >
                  <TextInput
                    id="cloud-url"
                    labelText="Cloud URL"
                    value={base}
                    onChange={(event) => setBase(event.target.value)}
                    type="url"
                    required
                  />
                  <TextInput
                    id="email"
                    labelText="Email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    type="email"
                    autoComplete="username"
                    required
                  />
                  <PasswordInput
                    id="password"
                    labelText="Password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="current-password"
                    required
                  />
                  <Button type="submit" disabled={busy || !status}>
                    Sign in
                  </Button>
                </Form>
              )}
            </Tile>
            <Tile>
              <div className="section-heading">
                <h2>Upload queue</h2>
                <Button
                  kind="ghost"
                  disabled={busy || !sync.connected}
                  onClick={() => void act(() => window.myocontrol.request('retry_sync'))}
                >
                  Retry pending
                </Button>
              </div>
              <p className="description">
                Select Sync on a recording to bind it to the signed-in operator. Uploads resume
                after reconnecting.
              </p>
              {sync.entries.length ? (
                sync.entries.map((entry) => (
                  <div className="sync-entry" key={entry.id}>
                    <Tag
                      type={
                        entry.state === 'synced'
                          ? 'green'
                          : entry.state === 'pending'
                            ? 'blue'
                            : 'red'
                      }
                    >
                      {entry.state}
                    </Tag>
                    <code>{entry.recording_id.slice(0, 8)}</code>
                    <span>{entry.attempts} attempts</span>
                    {entry.error && <p>{entry.error}</p>}
                  </div>
                ))
              ) : (
                <p className="empty">No uploads for this operator.</p>
              )}
            </Tile>
          </div>
        )}
      </main>
    </>
  )
}
