import { ChevronRight, Database, Fingerprint, ScanSearch } from 'lucide-react'
import { useState } from 'react'
import { count, runPath, useResource, type Comparison, type Evidence } from './api'
import { Empty, Notice, Waiting } from './components'

const toolTitles: Record<string, string> = {
  get_metric_summary: 'Traffic summary',
  compare_time_windows: 'Checkout window comparison',
  get_payment_error_breakdown: 'Payment outcomes',
  list_releases: 'Release timeline',
  list_feature_flag_changes: 'Feature flag changes',
  get_support_category_trends: 'Support ticket trends',
}

function asObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? value as Record<string, unknown> : null
}

function requestLabel(record: Evidence) {
  const window = asObject(record.request.window)
  return window ? String(window.start) + ' → ' + String(window.end) : 'Baseline vs. current'
}

export function ConversionChart({ comparison }: { comparison: Comparison }) {
  if (comparison.baseline.conversion_pct === null || comparison.current.conversion_pct === null) {
    return <div className="chart-unavailable">Comparable conversion is unavailable for this window.</div>
  }
  const change = comparison.delta
  return <div className="conversion-chart" aria-label="Checkout conversion comparison">
    <div className="chart-heading"><strong>Checkout conversion</strong>
      {change !== null && <span className={'pill ' + (change < 0 ? 'bad' : 'neutral')}>
        {change > 0 ? '+' : ''}{change.toFixed(2)} pp</span>}
    </div>
    {[['Baseline', comparison.baseline], ['Current', comparison.current]].map(([label, totals]) => {
      if (typeof totals === 'string' || typeof label !== 'string') return null
      const percent = totals.conversion_pct ?? 0
      return <div className="bar-row" key={label}>
        <span>{label}</span><div className="bar-track"><div className={'bar-fill ' + label.toLowerCase()} style={{ width: percent + '%' }} /></div>
        <strong>{percent.toFixed(2)}%</strong>
        <small>{count(totals.purchases)} of {count(totals.checkout_starts)} checkout starts</small>
      </div>
    })}
  </div>
}

function EvidenceSummary({ record }: { record: Evidence }) {
  if (record.tool === 'compare_time_windows') return <ConversionChart comparison={record.payload as unknown as Comparison} />
  const totals = asObject(record.payload.totals)
  if (totals) return <dl className="evidence-counts">
    <div><dt>Sessions</dt><dd>{count(Number(totals.sessions))}</dd></div>
    <div><dt>Checkout starts</dt><dd>{count(Number(totals.checkout_starts))}</dd></div>
    <div><dt>Purchases</dt><dd>{count(Number(totals.purchases))}</dd></div>
  </dl>
  if (record.tool === 'get_payment_error_breakdown') return <dl className="evidence-counts">
    <div><dt>Attempts</dt><dd>{count(Number(record.payload.total))}</dd></div>
    <div><dt>Failures</dt><dd>{count(Number(record.payload.failures))}</dd></div>
    <div><dt>Days recorded</dt><dd>{String(record.payload.coverage_days)}</dd></div>
  </dl>
  const categories = asObject(record.payload.categories)
  if (categories) return <dl className="evidence-counts">
    <div><dt>Recorded tickets</dt><dd>{String(record.payload.total)}</dd></div>
    {Object.entries(categories).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{String(value)}</dd></div>)}
  </dl>
  const records = record.payload.records
  if (!Array.isArray(records) || !records.length) return <p className="muted">No source rows in this window.</p>
  return <ul className="simple-list">{records.map((row) => <li key={String(row.id)}>
    <strong>{String(row.version ?? row.flag)}</strong> {row.description ? String(row.description) : String(row.rollout_percent) + '% rollout · ' + String(row.segment)}
  </li>)}</ul>
}

export function EvidenceView({ runId, evidence, selection, onSelect }: {
  runId: string; evidence: Evidence[]; selection: string | null; onSelect: (id: string) => void
}) {
  const selected = evidence.find((row) => row.id === selection) ?? evidence[0]
  const [source, setSource] = useState<{ ev: string; id: string }>()
  const active = source?.ev === selected?.id ? source?.id : undefined
  const path = active && selected
    ? runPath(runId) + '/evidence/' + selected.id + '/sources/' + encodeURIComponent(active) : null
  const record = useResource<{ table: string; record: Record<string, unknown> }>(path)
  if (!selected) return <Empty title="Evidence is being collected" text="Audited source records appear when the workflow saves its draft." />
  return <section className="evidence-layout" aria-label="Evidence explorer">
    <div className="panel evidence-menu">
      <div className="section-heading"><div><h2>Evidence explorer</h2><p>{evidence.length} verified records</p></div></div>
      {evidence.map((row) => <button key={row.id} aria-pressed={row.id === selected.id}
        onClick={() => onSelect(row.id)} className="evidence-choice">
        <ScanSearch size={17} aria-hidden /><span><strong>{toolTitles[row.tool] ?? row.tool}</strong><small>{requestLabel(row)}</small></span>
        <ChevronRight size={17} aria-hidden />
      </button>)}
    </div>
    <div className="panel evidence-detail">
      <div className="section-heading"><div><h2>{toolTitles[selected.tool] ?? selected.tool}</h2><p>{requestLabel(selected)}</p></div></div>
      <span className="evidence-id"><Fingerprint size={16} aria-hidden />{selected.id}</span>
      <EvidenceSummary record={selected} />
      <details className="payload-details"><summary>MCP tool request and response</summary>
        <pre>{JSON.stringify({ tool: selected.tool, request: selected.request, payload: selected.payload }, null, 2)}</pre>
      </details>
      <h3><Database size={17} aria-hidden /> Source records <span className="muted">({selected.sources.length})</span></h3>
      {selected.sources.length === 0 && <p className="muted">No rows were returned for this request.</p>}
      <ul className="source-list">
        {selected.sources.map((row) => <li key={row.id}><button aria-pressed={row.id === active}
          onClick={() => setSource({ ev: selected.id, id: row.id })}><code>{row.id}</code><ChevronRight size={15} aria-hidden /></button></li>)}
      </ul>
      {path && !record.value && !record.error && <Waiting label="Reading the source over MCP…" />}
      {record.error && <Notice>{record.error}</Notice>}
      {record.value && <div className="source-record">
        <strong>{record.value.table}</strong><pre>{JSON.stringify(record.value.record, null, 2)}</pre>
      </div>}
    </div>
  </section>
}
