import { useState } from 'react'
import { Button, Checkbox, Select, SelectItem, Tile } from '@carbon/react'
import type { CalibrationAssessment, Recording } from '../types'

const classes = ['rest', 'fist', 'finger_spread']
const label = (code: string) => code.replaceAll('_', ' ')

type Props = {
  recordings: Recording[]
  disabled: boolean
  assessment?: CalibrationAssessment | null
  onTrain: (ids: string[]) => void
  onPrepare: (channels: number) => void
}

export default function PersonalCalibration({
  recordings,
  disabled,
  assessment,
  onTrain,
  onPrepare,
}: Props) {
  const [group, setGroup] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const eligible = recordings.filter(
    (row) =>
      row.purpose === 'calibration' &&
      row.status === 'completed' &&
      classes.includes(row.gesture ?? '') &&
      row.metadata.source_kind === 'device' &&
      row.metadata.source_name === 'BITalino' &&
      row.metadata.units === 'ADC counts' &&
      row.metadata.sample_rate_hz === 1000 &&
      [2, 4].includes(row.metadata.channel_map.length) &&
      row.sample_count >= 4000 &&
      row.sample_count <= 30000,
  )
  const key = (row: Recording) => JSON.stringify([row.participant_key, row.metadata])
  const groups = Array.from(new Map(eligible.map((row) => [key(row), row])).entries())
  const current = groups.some(([id]) => id === group) ? group : (groups[0]?.[0] ?? '')
  const rows = eligible.filter((row) => key(row) === current)
  const picked = rows.filter((row) => selected.includes(row.id))
  const counts = Object.fromEntries(
    classes.map((code) => [code, picked.filter((row) => row.gesture === code).length]),
  )
  const ready = classes.every((code) => counts[code] >= 5 && counts[code] <= 20)
  const selectedIds = picked.map((row) => row.id)
  return (
    <Tile className="personal-calibration">
      <h2>Train a personal model</h2>
      <p className="description">
        In Acquisition, use Calibration repetition. Record rest, fist and finger spread separately:
        10 recordings per gesture, 6 seconds each, A1/A2 at 1000 Hz. Hold the labelled pose
        throughout each recording with comfortable effort; relax between repetitions. Keep the
        participant, sensor placement and arm position consistent.
      </p>
      <Button
        kind="ghost"
        size="sm"
        disabled={disabled}
        onClick={() => onPrepare(rows[0]?.metadata.channel_map.length ?? 2)}
      >
        Set up labelled recording
      </Button>
      {groups.length > 0 ? (
        <>
          <Select
            id="calibration-group"
            labelText="Calibration data group"
            value={current}
            disabled={disabled}
            onChange={(event) => {
              setGroup(event.target.value)
              setSelected([])
            }}
          >
            {groups.map(([id, row]) => (
              <SelectItem
                key={id}
                value={id}
                text={`${row.participant_key} · ${row.metadata.channel_map.map((channel) => `A${channel + 1}`).join('/')} · 1000 Hz`}
              />
            ))}
          </Select>
          <div className="actions">
            <Button
              kind="tertiary"
              size="sm"
              disabled={disabled}
              onClick={() => {
                setSelected(
                  classes.flatMap((code) =>
                    rows
                      .filter((row) => row.gesture === code)
                      .sort(
                        (a, b) =>
                          b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id),
                      )
                      .slice(0, 10)
                      .map((row) => row.id),
                  ),
                )
              }}
            >
              Select latest 10 per gesture
            </Button>
            <Button
              kind="ghost"
              size="sm"
              disabled={disabled || !picked.length}
              onClick={() => setSelected([])}
            >
              Clear selection
            </Button>
          </div>
          <p role="status">
            Selected: {classes.map((code) => `${label(code)} ${counts[code]}`).join(' · ')}
          </p>
          <div className="table-wrap calibration-selection">
            <table>
              <caption>Calibration repetitions — select the recordings to use</caption>
              <thead>
                <tr>
                  <th>Select</th>
                  <th>Gesture</th>
                  <th>Created</th>
                  <th>Seconds</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <Checkbox
                        id={`calibration-${row.id}`}
                        hideLabel
                        labelText={`Use ${label(row.gesture!)} ${row.id}`}
                        checked={selected.includes(row.id)}
                        disabled={disabled}
                        onChange={(_, { checked }) =>
                          setSelected((previous) =>
                            checked
                              ? [...previous, row.id]
                              : previous.filter((id) => id !== row.id),
                          )
                        }
                      />
                    </td>
                    <td>{label(row.gesture!)}</td>
                    <td>{new Date(row.created_at).toLocaleString()}</td>
                    <td>{(row.sample_count / row.metadata.sample_rate_hz).toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="description">
            At least 5 repetitions per gesture are required; 10 are recommended. The latest 20% of
            whole repetitions per gesture are held out. One second is trimmed from each edge.
            Training stays on this computer and preserves signal amplitude. This button saves and
            selects the new model; archived trained model files are retained.
          </p>
          <Button disabled={disabled || !ready} onClick={() => onTrain(selectedIds)}>
            Train and use personal model
          </Button>
        </>
      ) : (
        <p className="description">
          No eligible labelled recordings yet. Research recordings and incomplete captures are
          excluded.
        </p>
      )}
      {assessment && (
        <div className="calibration-assessment" aria-label="Personal model evaluation">
          <h3>Selected personal model — {assessment.participant_key}</h3>
          <p>
            Held-out window accuracy: {(assessment.accuracy * 100).toFixed(1)}% · balanced accuracy:{' '}
            {(assessment.balanced_accuracy * 100).toFixed(1)}%
          </p>
          <p>
            Rest predicted as a gesture: {(assessment.rest_false_activation_rate * 100).toFixed(1)}%
          </p>
          <p>
            {assessment.class_order
              .map(
                (code) =>
                  `${label(code)}: ${assessment.train_repetitions[code]} train / ${assessment.test_repetitions[code]} test repetitions`,
              )
              .join(' · ')}
          </p>
          <div className="table-wrap">
            <table>
              <caption>Held-out windows: rows are recorded labels, columns are predictions</caption>
              <thead>
                <tr>
                  <th>Recorded label</th>
                  {assessment.class_order.map((code) => (
                    <th key={code}>{label(code)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {assessment.confusion_matrix.map((row, index) => (
                  <tr key={assessment.class_order[index]}>
                    <th>{label(assessment.class_order[index])}</th>
                    {row.map((value, column) => (
                      <td key={column}>{value}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="description">
            This is a small repetition holdout from the same collection, not a new-session accuracy
            estimate. Test new live movements before relying on predictions. Moving electrodes or
            changing effort can change performance.
          </p>
        </div>
      )}
    </Tile>
  )
}
