import {
  Accordion,
  AccordionItem,
  CodeSnippet,
  StructuredListBody,
  StructuredListCell,
  StructuredListRow,
  StructuredListWrapper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
} from '@carbon/react'
import type { RegistryDetail } from '../types/cloud'
import { percentage, readable } from '../utils/format'

export default function RegistryDetails({ detail }: { detail: RegistryDetail }) {
  if (!detail || typeof detail !== 'object') return null
  const entries = Object.entries(detail)
  const fields = entries.filter(
    ([key, value]) => key !== 'confusion_counts' && (value === null || typeof value !== 'object'),
  )
  const objects = entries.filter(
    ([key, value]) => key !== 'confusion_counts' && value !== null && typeof value === 'object',
  )
  const counts = detail.confusion_counts
  return (
    <>
      <StructuredListWrapper aria-label="Registry metadata">
        <StructuredListBody>
          {fields.map(([key, value]) => (
            <StructuredListRow key={key}>
              <StructuredListCell className="detail-label">{readable(key)}</StructuredListCell>
              <StructuredListCell className="detail-value">
                {value == null
                  ? 'N/A'
                  : ['accuracy', 'macro_f1', 'rest_false_activation_rate'].includes(key) &&
                      typeof value === 'number'
                    ? percentage(value)
                    : typeof value === 'boolean'
                      ? value
                        ? 'Yes'
                        : 'No'
                      : String(value)}
              </StructuredListCell>
            </StructuredListRow>
          ))}
        </StructuredListBody>
      </StructuredListWrapper>
      {objects.length > 0 && (
        <Accordion>
          {objects.map(([key, value]) => (
            <AccordionItem key={key} title={readable(key)}>
              <CodeSnippet type="multi" feedback="Copied" wrapText>
                {JSON.stringify(value, null, 2)}
              </CodeSnippet>
            </AccordionItem>
          ))}
        </Accordion>
      )}
      {counts && (
        <TableContainer
          title="Confusion counts"
          description="Observed windows for each actual and predicted class pair."
        >
          <div
            className="table-scroll"
            role="region"
            aria-label="Confusion counts table"
            tabIndex={0}
          >
            <Table size="md" aria-label="Evaluation confusion counts">
              <TableHead>
                <TableRow>
                  <TableHeader>Actual class</TableHeader>
                  <TableHeader>Predicted class</TableHeader>
                  <TableHeader>Count</TableHeader>
                </TableRow>
              </TableHead>
              <TableBody>
                {counts.map((row) => (
                  <TableRow key={`${row.actual_class}-${row.predicted_class}`}>
                    <TableCell>{readable(row.actual_class)}</TableCell>
                    <TableCell>{readable(row.predicted_class)}</TableCell>
                    <TableCell>{row.count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TableContainer>
      )}
    </>
  )
}
