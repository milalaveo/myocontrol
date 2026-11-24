import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Breadcrumb,
  BreadcrumbItem,
  Button,
  DataTableSkeleton,
  InlineLoading,
  Pagination,
  Tile,
} from '@carbon/react'
import { ArrowLeft, Renew } from '@carbon/icons-react'
import { collections } from '../config/collections'
import { useRegistry } from '../hooks/useRegistry'
import { PAGE_SIZE } from '../services/registry'
import type { Collection } from '../types/cloud'
import ErrorNotice from '../components/ErrorNotice'
import RegistryDetails from '../components/RegistryDetails'
import RegistryTable from '../components/RegistryTable'

export default function RegistryPage({ collection }: { collection: Collection }) {
  const config = collections[collection]
  const { id } = useParams()
  const [search, setSearch] = useSearchParams()
  const requestedPage = Number(search.get('page') ?? '1')
  const pageNumber =
    Number.isSafeInteger(requestedPage) && requestedPage > 0 && requestedPage <= 1_000_000
      ? requestedPage
      : 1
  const offset = (pageNumber - 1) * PAGE_SIZE
  const [refresh, setRefresh] = useState(0)
  const state = useRegistry(collection, offset, id, refresh)
  const navigate = useNavigate()
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    document.title = `${id ? 'Registry details' : config.name} · MyoControl`
    heading.current?.focus()
  }, [collection, id, config.name])

  return (
    <>
      <Breadcrumb noTrailingSlash>
        <BreadcrumbItem>
          <Link to="/experiments">Cloud</Link>
        </BreadcrumbItem>
        <BreadcrumbItem isCurrentPage>{config.name}</BreadcrumbItem>
      </Breadcrumb>
      <div className="page-heading">
        <div>
          <span className="eyebrow">RESEARCH WORKSPACE</span>
          <h1 ref={heading} tabIndex={-1}>
            {config.name}
          </h1>
          <p className="supporting-text">{config.description}</p>
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
      {state.status === 'error' && <ErrorNotice message={state.message} />}
      {id ? (
        <section aria-busy={state.status === 'loading'} className="details-section">
          <Button
            kind="ghost"
            renderIcon={ArrowLeft}
            onClick={() => navigate(config.path + locationSearch(search))}
          >
            Back to {config.name.toLowerCase()}
          </Button>
          <Tile className="details-panel">
            <h2>Registry details</h2>
            {state.status === 'loading' ? (
              <InlineLoading description="Loading details…" />
            ) : (
              state.status === 'success' &&
              state.detail && <RegistryDetails detail={state.detail} />
            )}
          </Tile>
        </section>
      ) : (
        <section aria-label={config.name} aria-busy={state.status === 'loading'}>
          {state.status === 'loading' ? (
            <div role="status" aria-label="Loading registry">
              <DataTableSkeleton
                columnCount={collection === 'results' ? 7 : 6}
                rowCount={5}
                showHeader={false}
                showToolbar={false}
              />
            </div>
          ) : state.status === 'error' ? (
            <Tile className="empty-state">
              <h2>Unable to load {config.name.toLowerCase()}</h2>
              <p>Refresh the workspace to try again.</p>
            </Tile>
          ) : state.page.items.length === 0 ? (
            <Tile className="empty-state">
              <config.icon size={48} />
              <h2>No {config.name.toLowerCase()} yet</h2>
              <p>{config.empty}</p>
            </Tile>
          ) : (
            <RegistryTable
              collection={collection}
              rows={state.page.items}
              onSelect={(itemId) => navigate(`${config.path}/${itemId}${locationSearch(search)}`)}
            />
          )}
          {state.status === 'success' && (state.page.items.length > 0 || offset > 0) && (
            <Pagination
              page={pageNumber}
              pageSize={PAGE_SIZE}
              pageSizes={[PAGE_SIZE]}
              pagesUnknown
              itemText={() =>
                state.page.items.length
                  ? `${offset + 1}–${offset + state.page.items.length} items`
                  : '0 items'
              }
              isLastPage={state.page.next_offset == null}
              totalItems={offset + state.page.items.length}
              pageSizeInputDisabled
              onChange={({ page }) => setSearch(page > 1 ? { page: String(page) } : {})}
            />
          )}
        </section>
      )}
    </>
  )
}

function locationSearch(search: URLSearchParams) {
  return search.size ? `?${search}` : ''
}
