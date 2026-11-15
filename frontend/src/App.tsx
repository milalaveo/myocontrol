import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Activity, ArrowDownToLine, ArrowRight, Box, Check, ChevronRight, CircleHelp, Database, FlaskConical, Layers, Link2, LoaderCircle, LogOut, Pause, Play, Radio, RefreshCw, Settings2, ShieldCheck, Square, Waves, X } from 'lucide-react'
import SignalChart, { colors } from './components/SignalChart'
import { gestures, gestureName } from './types'
import type { Experiment, Participant, Prediction, Recording, Replay, Signal } from './types'

const HandScene = lazy(() => import('./components/HandScene'))
const tabs = [{ id: 'workspace', name: 'Workspace', icon: Layers }, { id: 'recordings', name: 'Recordings', icon: Database }, { id: 'experiments', name: 'Experiments', icon: FlaskConical }, { id: 'replay', name: 'Replay', icon: Play }]
const demoSignal: Signal = { sample_rate_hz: 1000, samples: Array.from({ length: 3000 }, (_, i) => [0, 1, 2, 3].map(c => {
  const envelope = .15 + .8 * Math.exp(-(((i - 1450 - c * 100) / 550) ** 2))
  return envelope * (Math.sin(i * (.31 + c * .05)) * .45 + Math.sin(i * .79 + c) * .28 + Math.sin(i * 1.83) * .16) + c * 1.6
})) }
const demoPredictions: Prediction[] = Array.from({ length: 29 }, (_, i) => ({ start_sample: i * 100, gesture: i < 6 || i > 22 ? 'rest' : 'fist', command: i < 6 || i > 22 ? 'neutral' : 'fist' }))
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export default function App() {
  const [tab, setTab] = useState('workspace')
  const [auth, setAuth] = useState<{ user: string; password: string } | null>(null)
  const [login, setLogin] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [participants, setParticipants] = useState<Participant[]>([])
  const [participant, setParticipant] = useState('')
  const [recordings, setRecordings] = useState<Recording[]>([])
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [selected, setSelected] = useState<Recording | null>(null)
  const [signal, setSignal] = useState<Signal>(demoSignal)
  const [enabled, setEnabled] = useState([true, true, true, true])
  const [gesture, setGesture] = useState('rest')
  const [playing, setPlaying] = useState(false)
  const [position, setPosition] = useState(0)
  const [predictions, setPredictions] = useState<Prediction[]>(demoPredictions)
  const [replay, setReplay] = useState<Replay | null>(null)
  const [experiment, setExperiment] = useState<Experiment | null>(null)
  const [modelId, setModelId] = useState('')
  const [help, setHelp] = useState(false)
  const generation = useRef(0)
  const duration = signal.samples.length / signal.sample_rate_hz

  useEffect(() => {
    if (!login && !help) return
    const previous = document.activeElement as HTMLElement | null
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, a[href]') ?? [])
    focusable()[0]?.focus()
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') { setLogin(false); setHelp(false) }
      if (event.key !== 'Tab') return
      const items = focusable(), first = items[0], last = items.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', handleKey)
    return () => { document.removeEventListener('keydown', handleKey); previous?.focus() }
  }, [login, help])

  const request = useCallback(async <T,>(path: string, body?: unknown, credentials = auth): Promise<T> => {
    if (!credentials) throw new Error('Connect to the local gateway first.')
    const bytes = new TextEncoder().encode(`${credentials.user}:${credentials.password}`)
    const response = await fetch(`/api/${path}`, { method: body === undefined ? 'GET' : 'POST', signal: AbortSignal.timeout(45000),
      headers: { Authorization: `Basic ${btoa(Array.from(bytes, b => String.fromCharCode(b)).join(''))}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
    const result = await response.json().catch(() => null)
    if (!response.ok) {
      const detail = typeof result?.detail === 'string' ? result.detail : response.status === 422 ? 'Please check the input values.' : 'The service could not complete this request.'
      throw new Error(`${response.status}: ${detail}${response.headers.get('x-correlation-id') ? ` · Reference ${response.headers.get('x-correlation-id')}` : ''}`)
    }
    return result as T
  }, [auth])

  async function perform(action: () => Promise<void>) {
    setError(''); setNotice(''); setBusy(true)
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : 'Request failed.'); setPlaying(false); setGesture('rest') }
    finally { setBusy(false) }
  }

  async function loadRecordings(person = participant, nextOffset = 0, credentials = auth) {
    const rows = await request<Recording[]>(`data/v1/recordings?limit=20&offset=${nextOffset}${person ? `&participant_id=${person}` : ''}`, undefined, credentials)
    setRecordings(rows); setOffset(nextOffset); setHasMore(rows.length === 20)
  }

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const credentials = { user: String(form.get('username')), password: String(form.get('password')) }
    await perform(async () => {
      const people = await request<Participant[]>('data/v1/participants?limit=100', undefined, credentials)
      await loadRecordings('', 0, credentials)
      generation.current++; setAuth(credentials); setParticipants(people); setParticipant(''); setLogin(false)
      stop(); setSelected(null); setSignal({ sample_rate_hz: 1000, samples: [] }); setPredictions([]); setReplay(null)
      setNotice('Connected. Choose a recording to inspect the real signal.')
    })
  }

  function stop() { setPlaying(false); setPosition(0); setGesture('rest') }
  function disconnect() {
    generation.current++; setAuth(null); setParticipants([]); setRecordings([]); setSelected(null); setParticipant(''); setOffset(0); setHasMore(false)
    setSignal(demoSignal); setPredictions(demoPredictions); setReplay(null); setExperiment(null); setModelId(''); setError(''); setNotice(''); stop()
  }

  async function chooseRecording(row: Recording) {
    await perform(async () => {
      const loaded = await request<Signal>(`data/v1/recordings/${row.id}/signal`)
      stop(); setSelected(row); setSignal(loaded); setPredictions([]); setReplay(null); setTab('workspace')
    })
  }

  useEffect(() => {
    if (!playing) return
    const started = performance.now() - position * 1000
    const timer = window.setInterval(() => {
      const next = Math.min((performance.now() - started) / 1000, duration)
      setPosition(next)
      if (next >= duration) { setPlaying(false); setGesture('rest'); return }
      const prediction = [...predictions].reverse().find(p => p.start_sample / signal.sample_rate_hz <= next)
      setGesture(prediction?.command === 'neutral' ? 'rest' : prediction?.gesture ?? 'rest')
    }, 40)
    return () => window.clearInterval(timer)
    // Position is captured when playback starts; the timer owns subsequent progress.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, duration, predictions, signal.sample_rate_hz])

  useEffect(() => {
    if (!experiment || !['queued', 'running'].includes(experiment.status) || !auth) return
    const run = experiment.id, token = generation.current
    let cancelled = false, polling = false
    const started = Date.now()
    const timer = window.setInterval(async () => {
      if (polling) return
      if (Date.now() - started > 120000) { window.clearInterval(timer); setNotice('Polling paused after two minutes. Use Refresh run to check again.'); return }
      polling = true
      try {
        const result = await request<Experiment>(`experiments/v1/source-lda-experiments/${run}`)
        if (!cancelled && token === generation.current) { setExperiment(result); if (!['queued', 'running'].includes(result.status)) window.clearInterval(timer) }
      } catch (e) { if (!cancelled) { setError(e instanceof Error ? e.message : 'Polling failed'); window.clearInterval(timer) } }
      finally { polling = false }
    }, 2000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [experiment?.id, auth, request])

  async function runReplay(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected || !uuidPattern.test(modelId)) { setError('Choose a recording and enter a valid model run UUID.'); return }
    await perform(async () => {
      stop()
      const result = await request<Replay>('recognition/v1/replay-sessions', { model_run_id: modelId, recording_id: selected.id })
      setReplay(result)
      if (result.status !== 'succeeded' || !result.result?.predictions?.length) { setPredictions([]); throw new Error(result.error ?? 'No predictions were returned.') }
      setPredictions(result.result.predictions); setNotice('Replay computed. Press Play to inspect the predictions.'); setTab('workspace')
    })
  }

  async function submitExperiment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget), manifest = String(form.get('manifest')), target = String(form.get('target'))
    if (!uuidPattern.test(manifest) || !uuidPattern.test(target)) { setError('Enter valid manifest and target participant UUIDs.'); return }
    await perform(async () => { setExperiment(await request<Experiment>('experiments/v1/source-lda-experiments', { manifest_id: manifest, target_participant_id: target })); setNotice('Experiment queued. Its status will update automatically.') })
  }

  function exportSignal() {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ ...signal, recording_id: selected?.id ?? null, kind: auth ? 'recorded' : 'synthetic_demo' })], { type: 'application/json' }))
    const link = document.createElement('a'); link.href = url; link.download = `myocontrol-${selected?.id ?? 'demo'}.json`; link.click(); URL.revokeObjectURL(url)
  }

  const name = tabs.find(t => t.id === tab)?.name ?? 'Workspace'
  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#workspace" onClick={() => setTab('workspace')} aria-label="Myocontrol home"><span className="brand-symbol"><Waves size={25} /></span><span>myocontrol<span className="brand-sub">RESEARCH STUDIO</span></span></a>
      <div className="nav-label">WORKBENCH</div>
      <nav aria-label="Main navigation">{tabs.map(t => <button key={t.id} className={tab === t.id ? 'nav-item active' : 'nav-item'} aria-current={tab === t.id ? 'page' : undefined} onClick={() => setTab(t.id)}><t.icon size={18} />{t.name}{tab === t.id && <span className="nav-dot" />}</button>)}</nav>
      <div className="sidebar-note"><span className="small-tag">RESEARCH PROTOTYPE</span><h4>From muscle to motion.</h4><p>Explore signals. Understand gestures. Build better control.</p><div className="mini-wave">∿∿∿∿∿∿</div></div>
      <button className="nav-item help-button" onClick={() => setHelp(true)}><CircleHelp size={18} />Workspace guide</button>
      <div className="sidebar-footer"><span className="avatar">M</span><span>Local workspace<small>Myocontrol · v0.1</small></span></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb">Research studio <ChevronRight size={14} /><strong>{name}</strong></div><div className="top-actions"><span className={`connection ${auth ? 'online' : ''}`}><i />{auth ? 'Gateway connected' : 'Demo workspace'}</span><button className="button subtle" onClick={() => auth ? disconnect() : setLogin(true)}>{auth ? <LogOut size={15} /> : <Link2 size={15} />}{auth ? 'Disconnect' : 'Connect API'}</button></div></header>
      <main id="workspace">
        <div className="page-heading"><div><div className="eyebrow">sEMG EXPLORATION / {auth ? 'LOCAL DATA' : 'INTERACTIVE DEMO'}</div><h1>{tab === 'workspace' ? 'Signal to motion' : name}<span className="heading-dot">.</span></h1><p>{tab === 'workspace' ? 'A closer look at the signal behind every gesture.' : tab === 'recordings' ? 'Browse participants and inspect their recorded signals.' : tab === 'experiments' ? 'Train a source-only LDA on a frozen research manifest.' : 'Apply a published model to a recorded signal.'}</p></div><span className="mode-label"><Box size={15} />{auth ? 'Local session' : 'Synthetic preview'}</span></div>
        <div aria-live="polite">{error && <div role="alert" className="message error">{error}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={16} /></button></div>}{notice && <div className="message success"><Check size={16} />{notice}<button aria-label="Dismiss message" onClick={() => setNotice('')}><X size={16} /></button></div>}</div>
        {tab === 'recordings' ? <section className="panel recordings-panel"><div className="panel-heading"><div><span className="eyebrow">DATA LIBRARY</span><h2>Recordings</h2></div><button className="button" disabled={!auth || busy} onClick={() => perform(() => loadRecordings())}><RefreshCw size={15} />Refresh</button></div>
          {!auth ? <Empty title="Your recordings, in one place" description="Connect to your local gateway to browse real data. Demo signals are available in Workspace." action={() => setLogin(true)} /> : <><label className="field filter">Participant<select value={participant} disabled={busy} onChange={e => { const id = e.target.value; setParticipant(id); perform(() => loadRecordings(id)) }}><option value="">All participants</option>{participants.map(p => <option key={p.id} value={p.id}>{p.pseudonym}</option>)}</select></label>
            <div className="table-scroll"><table><thead><tr><th>RECORDING</th><th>PARTICIPANT</th><th>SAMPLE RATE</th><th>DURATION</th><th /></tr></thead><tbody>{recordings.map(row => <tr key={row.id}><td><span className="record-icon"><Waves size={17} /></span><span className="mono" title={row.id}>{row.id.slice(0, 8)}…</span></td><td>{participants.find(p => p.id === row.participant_id)?.pseudonym ?? row.participant_id.slice(0, 8)}</td><td>{row.sample_rate_hz.toLocaleString()} Hz</td><td>{(row.sample_count / row.sample_rate_hz).toFixed(2)} s</td><td><button className="button subtle" disabled={busy} onClick={() => chooseRecording(row)}>Inspect <ArrowRight size={15} /></button></td></tr>)}</tbody></table></div>{!recordings.length && <p className="empty-copy">No recordings found for this selection.</p>}<div className="pagination"><button className="button" disabled={busy || offset === 0} onClick={() => perform(() => loadRecordings(participant, offset - 20))}>Previous</button><span>Page {offset / 20 + 1}</span><button className="button" disabled={busy || !hasMore} onClick={() => perform(() => loadRecordings(participant, offset + 20))}>Next</button></div></>}
        </section> : tab === 'experiments' ? <div className="form-grid"><section className="panel"><div className="panel-heading"><div><span className="eyebrow">EXPERIMENT SETUP</span><h2>Train a baseline</h2></div><FlaskConical size={21} /></div><form className="form-body" onSubmit={submitExperiment}><p className="muted">Select an existing frozen manifest. Source training and target test membership are validated by the services.</p><label className="field">Frozen manifest UUID<input name="manifest" required placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" /></label><label className="field">Target participant<select name="target" required><option value="">Choose a participant</option>{participants.map(p => <option key={p.id} value={p.id}>{p.pseudonym}</option>)}</select></label><div className="config-row"><span>Shrinkage LDA</span><span>200 ms window</span><span>20 features</span></div><button className="button primary" disabled={!auth || busy}><Play size={15} />Queue experiment</button>{!auth && <p className="muted">Connect API to submit an experiment.</p>}</form></section><section className="panel"><div className="panel-heading"><div><span className="eyebrow">RUN DETAILS</span><h2>{experiment ? experiment.status : 'No run selected'}</h2></div><Activity size={20} /></div><div className="form-body"><form onSubmit={e => { e.preventDefault(); const id = String(new FormData(e.currentTarget).get('run')); if (!uuidPattern.test(id)) { setError('Enter a valid experiment UUID.'); return } perform(async () => setExperiment(await request<Experiment>(`experiments/v1/source-lda-experiments/${id}`))) }}><label className="field">Look up an existing run<input name="run" placeholder="Experiment UUID" required /></label><button className="button" disabled={!auth || busy}>Load run</button></form>{experiment && <><p className="mono run-id">{experiment.id}</p><button className="button" disabled={busy} onClick={() => perform(async () => setExperiment(await request<Experiment>(`experiments/v1/source-lda-experiments/${experiment.id}`)))}><RefreshCw size={14} />Refresh run</button>{experiment.error && <p className="error-text">{experiment.error}</p>}{experiment.metrics && <pre className="result-json">{JSON.stringify(experiment.metrics, null, 2)}</pre>}{experiment.status === 'succeeded' && <button className="button primary" onClick={() => { setModelId(experiment.id); setTab('replay') }}>Use for replay <ArrowRight size={15} /></button>}</>}</div></section></div> : tab === 'replay' ? <section className="panel replay-setup"><div className="panel-heading"><div><span className="eyebrow">RECOGNITION</span><h2>Prepare a replay</h2></div><Play size={21} /></div><form className="form-body" onSubmit={runReplay}><label className="field">Published model run UUID<input value={modelId} onChange={e => setModelId(e.target.value)} placeholder="Model run UUID" required /></label><label className="field">Selected recording<input readOnly value={selected?.id ?? ''} placeholder="Choose a recording in the library first" /></label><button type="button" className="button" onClick={() => setTab('recordings')}>Choose recording <ArrowRight size={15} /></button><p className="muted">Replay is computed by the Recognition service. Playback then animates its saved window predictions; confidence scores are not available.</p><button className="button primary" disabled={!auth || busy || !selected || !modelId}><Play size={15} />Compute replay</button></form></section> : <>
          <div className="stat-grid"><Stat icon={Waves} label="SIGNAL SOURCE" value={selected ? 'Recorded signal' : auth ? 'No recording' : 'Demo signal'} detail={selected ? `ID ${selected.id.slice(0, 8)}` : auth ? 'Select from the data library' : 'Generated locally · not measured EMG'} /><Stat icon={Radio} label="CHANNELS" value="4 channels" detail={auth ? 'Source electrode mapping not exposed by API' : 'Illustrative waveforms · vertically offset'} /><Stat icon={Activity} label="SAMPLE RATE" value={signal.samples.length ? `${signal.sample_rate_hz.toLocaleString()} Hz` : '—'} detail={signal.samples.length ? `${signal.samples.length.toLocaleString()} samples loaded` : 'Awaiting a recording'} /><Stat icon={Box} label="RECOGNITION" value={replay?.status === 'succeeded' ? 'Replay ready' : auth ? 'Not computed' : 'Demo sequence'} detail={replay?.result?.processing_p95_ms !== undefined ? `${replay.result.processing_p95_ms.toFixed(2)} ms processing p95` : 'Choose a pose or load model predictions'} /></div>
          <div className="workspace-grid"><section className="panel signal-panel"><div className="panel-heading"><div><span className="eyebrow">SIGNAL EXPLORER</span><h2>Muscle activity <span className="small-tag">sEMG</span></h2></div><button className="icon-button" aria-label="Download loaded signal as JSON" title="Download signal JSON" disabled={!signal.samples.length} onClick={exportSignal}><ArrowDownToLine size={17} /></button></div><div className="chart-toolbar"><span><i className={`status-dot ${playing ? 'live' : ''}`} />{playing ? 'Playing recording' : 'Recorded / static preview'}</span><span>{duration.toFixed(2)} s <span className="separator">/</span> {auth ? 'Source values · units unspecified' : 'Illustrative amplitude'}</span></div>{signal.samples.length ? <SignalChart signal={signal} enabled={enabled} /> : <Empty title="Ready for your first signal" description="Open the recording library to inspect a real four-channel recording." action={() => setTab('recordings')} button="Browse recordings" />}<div className="channel-controls">{colors.map((color, i) => <button key={color} aria-pressed={enabled[i]} onClick={() => setEnabled(old => old.map((v, c) => c === i ? !v : v))} className={!enabled[i] ? 'channel muted-channel' : 'channel'}><i style={{ background: color }} />Channel {i + 1}{enabled[i] && <Check size={12} />}</button>)}</div><div className="chart-footnote">Drag to zoom · Double-click to reset. The chart shows the complete loaded excerpt.</div></section>
          <section className="panel hand-panel"><div className="panel-heading"><div><span className="eyebrow">VIRTUAL HAND</span><h2>Gesture preview</h2></div><span className="small-tag">3D</span></div><div className="hand-stage"><div className="stage-corner">RIGHT HAND<span>Conceptual visualization</span></div><Suspense fallback={<div className="hand-loading"><LoaderCircle className="spin" />Loading hand…</div>}><HandScene gesture={gesture} /></Suspense><span className="stage-axis">X <span>Y</span> Z</span></div><div className="pose-caption"><span className="pose-indicator" /><div><small>{playing ? auth ? 'MODEL PREDICTION' : 'SCRIPTED DEMO' : 'MANUAL POSE PREVIEW'}</small><strong>{gestureName(gesture)}</strong></div><span className="pose-state">{playing ? 'Playback' : 'Preview'}</span></div></section></div>
          <section className="panel transport"><div className="transport-buttons"><button className="play-button" aria-label={playing ? 'Pause and return hand to neutral' : 'Play predictions'} disabled={!predictions.length} onClick={() => { if (playing) { setPlaying(false); setGesture('rest') } else { if (position >= duration) setPosition(0); setPlaying(true) } }}>{playing ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}</button><button className="icon-button" aria-label="Stop and reset replay" onClick={stop}><Square size={15} /></button></div><div className="timeline"><div><span>{auth ? replay ? 'Model prediction replay' : 'Load a model to enable playback' : 'Synthetic gesture sequence'}</span><span className="mono">{position.toFixed(2)} / {duration.toFixed(2)} s</span></div><progress aria-label="Replay progress" value={position} max={duration || 1} /></div><span className="playback-speed">1×</span></section>
          <section className="panel gesture-panel"><div className="panel-heading"><div><span className="eyebrow">MOVEMENT VOCABULARY</span><h2>Explore the gestures</h2></div><span className="muted small">Manual visualization · no classification</span></div><div className="gesture-grid">{gestures.map((g, i) => <button key={g.id} className={`gesture-card ${gesture === g.id ? 'selected' : ''}`} aria-pressed={gesture === g.id} onClick={() => { setPlaying(false); setGesture(g.id) }}><span className="gesture-number">0{i + 1}</span><strong>{g.name}</strong><span>{g.detail}</span><span className="gesture-check">{gesture === g.id ? <Check size={15} /> : <ArrowRight size={15} />}</span></button>)}</div></section>
          <div className="workspace-bottom"><span><ShieldCheck size={14} />{auth ? 'Credentials stay in memory for this session' : 'Demo runs locally · no backend connection required'}</span><button onClick={() => setTab('recordings')}>Open recording library <ArrowRight size={14} /></button></div>
        </>}
        {busy && <div className="busy-indicator" role="status"><LoaderCircle size={16} className="spin" />Working…</div>}
      </main>
    </div>
    {login && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="connect-title"><button className="modal-close icon-button" aria-label="Close connection dialog" onClick={() => setLogin(false)}><X size={20} /></button><Link2 className="modal-symbol" /><h2 id="connect-title">Connect your workspace</h2><p className="muted">Use the gateway credentials from your local .env file. They are kept in memory and cleared on disconnect or reload.</p><form onSubmit={connect}><label className="field">Username<input autoFocus name="username" autoComplete="username" defaultValue="operator" required /></label><label className="field">Password<input name="password" type="password" autoComplete="current-password" required /></label>{error && <p role="alert" className="error-text">{error}</p>}<button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <Link2 size={16} />}Connect local API</button></form><button className="text-button" onClick={() => setLogin(false)}>Continue with interactive demo</button></section></div>}
    {help && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="guide-title"><button className="modal-close icon-button" aria-label="Close guide" onClick={() => setHelp(false)}><X size={20} /></button><Settings2 className="modal-symbol" /><h2 id="guide-title">Your research workbench</h2><p>Explore the synthetic demo immediately. Connect API to inspect recordings already stored in your database.</p><ol className="guide-list"><li>Choose a participant and recording in Recordings.</li><li>Inspect its four source channels in Workspace.</li><li>Train or look up an experiment using an existing frozen manifest.</li><li>Compute replay with a compatible model, then press Play.</li></ol><p className="muted">The hand is a simplified visual model. Manual gestures are previews. Playback uses saved predictions; pause and stop return the hand to neutral. Live acquisition, dataset import and split editing remain outside this first UI.</p><button className="button primary" onClick={() => setHelp(false)}>Got it</button></section></div>}
  </div>
}

function Empty({ title, description, action, button = 'Connect API' }: { title: string; description: string; action: () => void; button?: string }) {
  return <div className="empty-state"><Waves size={32} /><h3>{title}</h3><p>{description}</p><button className="button" onClick={action}>{button}<ArrowRight size={15} /></button></div>
}
function Stat({ icon: Icon, label, value, detail }: { icon: typeof Waves; label: string; value: string; detail: string }) {
  return <div className="stat"><div className="stat-label"><span>{label}</span><Icon size={16} /></div><strong>{value}</strong><small>{detail}</small></div>
}
