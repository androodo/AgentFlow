import { Activity, CalendarClock, ClipboardCheck, FileText, Headphones, ScanSearch, Workflow } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { timeLabel, type Run, type RunEvent } from './api'
import { Empty } from './components'

type NodeInfo = { id: string; label: string; icon: LucideIcon }
const nodes: NodeInfo[] = [
  { id: 'planner', label: 'Planner', icon: Workflow },
  { id: 'metrics', label: 'Metrics analyst', icon: Activity },
  { id: 'timeline', label: 'Release investigator', icon: CalendarClock },
  { id: 'support', label: 'Support investigator', icon: Headphones },
  { id: 'audit', label: 'Evidence audit', icon: ScanSearch },
  { id: 'report', label: 'Report composer', icon: FileText },
  { id: 'review', label: 'Human review', icon: ClipboardCheck },
]

const kinds: Record<string, string> = {
  queued: 'Investigation queued', worker_started: 'Worker started', worker_recovered: 'Worker recovered',
  node_started: 'Started', node_finished: 'Finished', node_failed: 'Failed',
  plan_selected: 'Investigation plan selected', tool_finished: 'MCP tool returned', tool_failed: 'MCP tool failed',
  tool_retry: 'Retrying MCP transport', tool_denied: 'Tool request denied', model_finished: 'Model response validated',
  specialist_focus: 'Specialist selected evidence', trace_exported: 'LangSmith metadata exported',
  specialist_output_skipped: 'Unverified specialist text omitted',
  trace_export_failed: 'LangSmith export failed', model_failed: 'Model call failed', model_retry: 'Model request retry',
  evidence_verified: 'Evidence verified', awaiting_review: 'Checkpoint saved for review',
  decision_recorded: 'Review decision recorded', approved: 'Report finalized', rejected: 'Draft rejected',
  failed: 'Investigation failed', canceled: 'Investigation canceled', needs_clarification: 'Clarification requested',
}

function nodeState(node: string, run: Run, events: RunEvent[]) {
  const isReview = node === 'review'
  if (isReview && run.status === 'awaiting_review') return { key: 'waiting', label: 'Awaiting review' }
  if (isReview && ['review_queued', 'reviewing'].includes(run.status)) return { key: 'active', label: 'Applying decision' }
  if (isReview && run.status === 'approved') return { key: 'done', label: 'Approved' }
  if (isReview && run.status === 'rejected') return { key: 'error', label: 'Rejected' }
  const last = events.findLast((event) => event.node === node && event.kind.startsWith('node_'))
  if (last?.kind === 'node_finished') return { key: 'done', label: 'Completed' }
  if (last?.kind === 'node_failed') return { key: 'error', label: 'Failed' }
  if (last?.kind === 'node_started') return { key: 'active', label: 'Running' }
  const domains = events.findLast((event) => event.kind === 'plan_selected')?.detail.domains
  if (Array.isArray(domains) && ['metrics', 'timeline', 'support'].includes(node) && !domains.includes(node))
    return { key: 'skipped', label: 'Skipped' }
  return { key: 'idle', label: 'Pending' }
}

export function GraphMap({ run, events, onNode }: { run: Run; events: RunEvent[]; onNode: (id: string) => void }) {
  function renderNode({ id, label, icon: Icon }: NodeInfo) {
    const state = nodeState(id, run, events)
    return <button key={id} className={'graph-node graph-' + state.key} onClick={() => onNode(id)}>
      <span className="graph-icon"><Icon size={18} aria-hidden /></span>
      <span><strong>{label}</strong><small><span className="dot" />{state.label}</small></span>
    </button>
  }
  return <section className="panel graph-panel" aria-labelledby="graph-title">
    <div className="section-heading">
      <div><h2 id="graph-title">Investigation workflow</h2><p>Open a node to see its recorded activity.</p></div>
      <span className="graph-tag"><Workflow size={15} aria-hidden /> LangGraph</span>
    </div>
    <div className="graph-map">
      <div className="graph-cell">{renderNode(nodes[0])}</div>
      <div className="graph-branches">{nodes.slice(1, 4).map(renderNode)}</div>
      {nodes.slice(4).map((node) => <div className="graph-cell" key={node.id}>{renderNode(node)}</div>)}
    </div>
  </section>
}

function Detail({ event }: { event: RunEvent }) {
  const { detail } = event
  const text = [detail.tool, detail.rationale, detail.error, detail.reason, detail.action, detail.model, detail.focus]
    .filter((item): item is string => typeof item === 'string')
  return <>
    {text.length > 0 && <p>{text.join(' · ')}</p>}
    {event.kind === 'evidence_verified' && <p>{String(detail.records)} evidence records passed validation.</p>}
    {event.kind === 'tool_finished' && <details className="trace-parameters"><summary>Request and provenance</summary>
      <pre>{JSON.stringify({ request: detail.request, evidence_id: detail.evidence_id }, null, 2)}</pre></details>}
  </>
}

export function ActivityView({ events, filter, onFilter }: {
  events: RunEvent[]; filter: string; onFilter: (value: string) => void
}) {
  const filtered = (filter ? events.filter((event) => event.node === filter) : events).toReversed()
  return <section className="panel activity-panel" aria-labelledby="activity-title">
    <div className="section-heading"><div><h2 id="activity-title">Activity log</h2><p>Recorded node, tool, and checkpoint events · UTC</p></div>
      <select aria-label="Filter by agent" value={filter} onChange={(event) => onFilter(event.target.value)}>
        <option value="">All activity</option>
        {nodes.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}
        <option value="revision">Revision</option><option value="workflow">Workflow</option>
      </select>
    </div>
    {filtered.length === 0 && <Empty title="No events in this view" text="Events appear as the workflow reaches this step." />}
    {filtered.length > 0 && <ol className="activity-list">
      {filtered.map((event) => <li key={event.id}>
        <span className="activity-marker" />
        <div className="activity-detail"><span className="activity-node">{nodes.find(({ id }) => id === event.node)?.label ?? event.node}</span>
          <strong>{kinds[event.kind] ?? event.kind.replaceAll('_', ' ')}</strong><Detail event={event} /></div>
        <div className="time-column"><time dateTime={event.occurred_at}>{timeLabel(event.occurred_at)}</time>
          {typeof event.detail.duration_ms === 'number' && <span>{event.detail.duration_ms} ms</span>}</div>
      </li>)}
    </ol>}
  </section>
}
