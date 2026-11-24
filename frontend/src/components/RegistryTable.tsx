import {
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
} from '@carbon/react'
import { ArrowRight } from '@carbon/icons-react'
import { collections } from '../config/collections'
import type { Collection, RegistryRow } from '../types/cloud'
import { percentage, readable, statusColor } from '../utils/format'

export default function RegistryTable({
  collection,
  rows,
  onSelect,
}: {
  collection: Collection
  rows: RegistryRow[]
  onSelect: (id: string) => void
}) {
  const config = collections[collection]
  return (
    <TableContainer title={config.title} description={config.tableDescription}>
      <div className="table-scroll" role="region" aria-label={`${config.name} table`} tabIndex={0}>
        <Table size="lg" aria-label={config.name}>
          <TableHead>
            <TableRow>
              <TableHeader>{collection === 'models' ? 'Model' : 'ID'}</TableHeader>
              <TableHeader>Family</TableHeader>
              <TableHeader>Condition</TableHeader>
              {collection === 'results' ? (
                <>
                  <TableHeader>Accuracy</TableHeader>
                  <TableHeader>Macro F1</TableHeader>
                  <TableHeader>Rest false activation</TableHeader>
                </>
              ) : (
                <>
                  <TableHeader>{collection === 'runs' ? 'Status' : 'Published'}</TableHeader>
                  {collection === 'runs' && <TableHeader>Execution</TableHeader>}
                </>
              )}
              <TableHeader>Details</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell title={row.id}>
                  <span className={collection === 'models' ? undefined : 'identifier'}>
                    {collection === 'models' ? row.name : row.id.slice(0, 8)}
                  </span>
                </TableCell>
                <TableCell>{row.family.toUpperCase()}</TableCell>
                <TableCell>{readable(row.condition)}</TableCell>
                {collection === 'results' ? (
                  <>
                    <TableCell>{percentage(row.accuracy)}</TableCell>
                    <TableCell>{percentage(row.macro_f1)}</TableCell>
                    <TableCell title={row.rest_missing_reason ?? undefined}>
                      {percentage(row.rest_false_activation_rate)}
                    </TableCell>
                  </>
                ) : (
                  <>
                    <TableCell>
                      {collection === 'runs' ? (
                        <Tag type={statusColor(row.status)} size="sm">
                          {readable(row.status ?? 'unknown')}
                        </Tag>
                      ) : row.published_at ? (
                        new Date(row.published_at).toLocaleString()
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    {collection === 'runs' && (
                      <TableCell>{readable(row.execution_location ?? '')}</TableCell>
                    )}
                  </>
                )}
                <TableCell>
                  <Button
                    kind="ghost"
                    size="sm"
                    renderIcon={ArrowRight}
                    aria-label={`View ${collection === 'models' ? row.name : row.id}`}
                    onClick={() => onSelect(row.id)}
                  >
                    View
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </TableContainer>
  )
}
