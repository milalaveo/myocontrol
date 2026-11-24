import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Button,
  DataTableSkeleton,
  InlineLoading,
  Pagination,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
  Tile,
} from '@carbon/react'
import { Download, Renew } from '@carbon/icons-react'
import { useAuth } from '../context/AuthContext'
import ErrorNotice from '../components/ErrorNotice'
import { ApiError, errorMessage } from '../services/http'
import { downloadRecording, listRecordings } from '../services/recordings'
import { PAGE_SIZE } from '../services/registry'
import type { RecordingPage } from '../types/cloud'

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; page: RecordingPage }

export default function RecordingsPage() {
  const { session, expireSession } = useAuth()
  const [search, setSearch] = useSearchParams()
  const requested = Number(search.get('page') ?? 1)
  const page =
    Number.isSafeInteger(requested) && requested > 0 && requested <= 1_000_000 ? requested : 1
  const offset = (page - 1) * PAGE_SIZE
  const [refresh, setRefresh] = useState(0)
  const [state, setState] = useState<State>({ status: 'loading' })
  const [downloading, setDownloading] = useState('')
  const [downloadError, setDownloadError] = useState('')
  const downloadController = useRef<AbortController | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    document.title = 'Recordings · MyoControl'
    heading.current?.focus()
    return () => downloadController.current?.abort()
  }, [])

  useEffect(() => {
    if (!session) return
    const controller = new AbortController()
    setState({ status: 'loading' })
    listRecordings(offset, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setState({ status: 'success', page: result })
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) expireSession()
        else setState({ status: 'error', message: errorMessage(error) })
      })
    return () => controller.abort()
  }, [offset, refresh, session, expireSession])

  async function download(id: string) {
    const controller = new AbortController()
    downloadController.current = controller
    setDownloading(id)
    setDownloadError('')
    try {
      await downloadRecording(id, controller.signal)
    } catch (error) {
      if (controller.signal.aborted) return
      if (error instanceof ApiError && error.status === 401) expireSession()
      else setDownloadError(errorMessage(error))
    } finally {
      if (!controller.signal.aborted) setDownloading('')
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">RESEARCH WORKSPACE</span>
          <h1 ref={heading} tabIndex={-1}>
            Recordings
          </h1>
          <p className="supporting-text">Signal recordings synchronized from MyoControl Desktop.</p>
        </div>
        <Button
          kind="tertiary"
          renderIcon={Renew}
          disabled={state.status === 'loading'}
          onClick={() => setRefresh((value) => value + 1)}
        >
          Refresh
        </Button>
      </div>
      <p className="supporting-text recordings-help">
        Capture or import a recording in Electron, sign in with the same operator account, then
        select Sync. Long recordings are uploaded in parts of up to 10,000 samples.
      </p>
      {downloadError && (
        <ErrorNotice title="Could not download recording" message={downloadError} />
      )}
      {downloading && <InlineLoading description="Downloading original samples…" />}
      <section aria-label="Synced recordings" aria-busy={state.status === 'loading'}>
        {state.status === 'loading' ? (
          <div role="status" aria-label="Loading recordings">
            <DataTableSkeleton
              columnCount={6}
              rowCount={5}
              showHeader={false}
              showToolbar={false}
            />
          </div>
        ) : state.status === 'error' ? (
          <>
            <ErrorNotice message={state.message} />
            <Tile className="empty-state">
              <h2>Unable to load recordings</h2>
              <p>Refresh the workspace to try again.</p>
            </Tile>
          </>
        ) : state.page.items.length === 0 ? (
          <Tile className="empty-state">
            <h2>No recordings yet</h2>
            <p>
              Recordings appear here after their upload queue status in Electron becomes synced.
              Local recordings stay on your computer until you select Sync.
            </p>
          </Tile>
        ) : (
          <TableContainer
            title="Synced recording parts"
            description="Original samples and channel mapping saved to your operator account."
          >
            <div className="table-scroll" role="region" aria-label="Recordings table" tabIndex={0}>
              <Table size="lg" aria-label="Synced recordings">
                <TableHead>
                  <TableRow>
                    {[
                      'Participant / ID',
                      'Source',
                      'Channels',
                      'Signal',
                      'Received',
                      'Download',
                    ].map((label) => (
                      <TableHeader key={label}>{label}</TableHeader>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {state.page.items.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>
                        <span>{row.source_participant_key}</span>
                        <span className="recording-secondary identifier" title={row.id}>
                          {row.id.slice(0, 8)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Tag type={row.source_kind === 'synthetic' ? 'purple' : 'gray'} size="sm">
                          {row.source_kind}
                        </Tag>
                        <span className="recording-secondary">{row.source_name}</span>
                      </TableCell>
                      <TableCell>
                        {row.channel_count} ·{' '}
                        {row.channel_map.map((channel) => `A${channel + 1}`).join(', ')}
                        <span className="recording-secondary">{row.units}</span>
                      </TableCell>
                      <TableCell>
                        {(row.sample_count / row.sample_rate_hz).toFixed(2)} s ·{' '}
                        {row.sample_rate_hz} Hz
                        <span className="recording-secondary">
                          {row.sample_count.toLocaleString()} samples · [{row.original_start_sample}
                          , {row.original_end_sample})
                        </span>
                      </TableCell>
                      <TableCell>{new Date(row.received_at).toLocaleString()}</TableCell>
                      <TableCell>
                        <Button
                          kind="ghost"
                          size="sm"
                          renderIcon={Download}
                          disabled={!!downloading}
                          aria-label={`Download recording ${row.id}`}
                          onClick={() => void download(row.id)}
                        >
                          JSON
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </TableContainer>
        )}
        {state.status === 'success' && (state.page.items.length > 0 || offset > 0) && (
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            pageSizes={[PAGE_SIZE]}
            pagesUnknown
            itemText={() =>
              state.page.items.length
                ? `${offset + 1}–${offset + state.page.items.length} items`
                : '0 items'
            }
            isLastPage={state.page.next_offset === null}
            totalItems={offset + state.page.items.length}
            pageSizeInputDisabled
            onChange={({ page }) => setSearch(page > 1 ? { page: String(page) } : {})}
          />
        )}
      </section>
    </>
  )
}
