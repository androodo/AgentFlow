import { FlaskConical } from 'lucide-react'
import { useState } from 'react'
import { errorMessage, localDateLabel, useResource, write, type Connection, type Judgment } from './api'
import { Notice, Waiting } from './components'

type CalibrationSummary = { id: string; model: string; status: string; created_at: string; error: string | null }
type Calibration = CalibrationSummary & {
  total: number; label_source: string; reference_version: string; rubric_version: string
  agreement: Record<string, { scored: number; exact_matches: number; mean_absolute_error: number }>
  cases: { id: string; text: string; reference: Record<string, number>; judgment?: Judgment; error?: string }[]
}

export function CalibrationPanel({ connection }: { connection?: Connection }) {
  const [id, setId] = useState<string>()
  const [refresh, setRefresh] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const history = useResource<CalibrationSummary[]>('/calibrations', 0, refresh)
  const selected = id ?? (connection?.state === 'ok' ? history.value?.[0]?.id : undefined)
  const calibration = useResource<Calibration>(selected ? '/calibrations/' + selected : null, 1600)
  const row = calibration.value

  async function runCalibration() {
    setError('')
    setBusy(true)
    try {
      const job = await write<{ id: string }>('/calibrations', {})
      setId(job.id)
      setRefresh((value) => value + 1)
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  return <section className="panel review-panel">
    <h2>Judge calibration</h2>
    <p>{connection?.state === 'ok'
      ? 'Compare model scores with the project’s authored rubric annotations.'
      : connection?.detail ?? 'Checking judge configuration…'}</p>
    {connection?.state === 'ok' && <button className="button secondary small" disabled={busy || row?.status === 'running' || row?.status === 'queued'}
      onClick={() => void runCalibration()}><FlaskConical size={15} aria-hidden /> Run calibration</button>}
    {(history.error || calibration.error || error) && <Notice>{calibration.error || history.error || error}</Notice>}
    {!!history.value?.length && <>
      <label htmlFor="calibration-run">Calibration run</label>
      <select id="calibration-run" value={selected ?? ''} onChange={(event) => setId(event.target.value)}>
        <option value="">Select a saved result</option>
        {history.value.map((item) => <option value={item.id} key={item.id}>{localDateLabel(item.created_at)} · {item.id.slice(0, 6)}</option>)}
      </select>
    </>}
    {selected && !row && !calibration.error && <Waiting label="Loading calibration…" />}
    {row && <div className="calibration-results">
      <p><strong>{row.status === 'completed' ? 'Completed' : row.status}</strong> · {row.cases.length} / {row.total} reviewed</p>
      <p>{row.model} · {row.reference_version}</p>
      <p>{row.label_source}</p>
      {row.error && <Notice>{row.error}</Notice>}
      {Object.keys(row.agreement).length > 0 && <ul className="agreement-list">
        {Object.entries(row.agreement).map(([axis, value]) => <li key={axis}><strong>{axis}</strong>
          <span>{value.exact_matches}/{value.scored} exact · {value.mean_absolute_error} mean absolute error</span></li>)}
      </ul>}
      {row.cases.length > 0 && <details className="payload-details"><summary>Per-snippet scores and rationale</summary>
        {row.cases.map((item) => <details className="calibration-case" key={item.id}>
          <summary>{item.id}{item.error ? ' · failed' : ''}</summary>
          <p>{item.text}</p>
          {item.error ? <Notice>{item.error}</Notice> : item.judgment && <>
            <ul className="agreement-list">{Object.entries(item.reference).map(([axis, reference]) =>
              <li key={axis}><strong>{axis}</strong><span>Ref {reference} · Judge {item.judgment?.scores[axis]}</span></li>)}</ul>
            <p>{item.judgment.rationale}</p>
          </>}
        </details>)}
      </details>}
    </div>}
  </section>
}
