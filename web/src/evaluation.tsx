import { Activity, Cable, Database, Download, FlaskConical, Play, RefreshCw, Server, Waypoints } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  errorMessage, evaluationLink, localDateLabel, modelAvailable, useResource, write,
  type Connection, type Connections, type Evaluation, type EvaluationSummary, type Mode, type Strategy, type Workspace,
} from './api'
import { ModeOptions } from './provider-options'
import { CalibrationPanel } from './calibration'
import { Empty, ModeBanner, Notice, PageHeading, Waiting } from './components'

const strategyLabels: Record<Strategy, string> = {
  compare: 'Compare both', single: 'Single-agent baseline', multi: 'Multi-agent graph',
}
const connectionInfo = [
  { key: 'api', title: 'FastAPI', subtitle: 'Investigation and review API', icon: Server },
  { key: 'database', title: 'PostgreSQL', subtitle: 'Data, traces, and checkpoints', icon: Database },
  { key: 'mcp', title: 'Northstar MCP', subtitle: 'Read-only tools over Streamable HTTP', icon: Cable },
  { key: 'ollama', title: 'Ollama', subtitle: 'Optional live local inference', icon: FlaskConical },
  { key: 'openai', title: 'OpenAI', subtitle: 'Hosted model API', icon: FlaskConical },
  { key: 'anthropic', title: 'Claude', subtitle: 'Anthropic model API', icon: FlaskConical },
  { key: 'langsmith', title: 'LangSmith', subtitle: 'Opt-in trace metadata export', icon: Waypoints },
  { key: 'judge', title: 'LLM judge', subtitle: 'Optional report-quality rubric', icon: Activity },
] as const

const healthLabels: Record<Connection['state'], string> = {
  ok: 'Connected', unavailable: 'Unavailable', not_configured: 'Not configured', configured: 'Configured',
}

export function ConnectionsPage() {
  const [refresh, setRefresh] = useState(0)
  const [tests, setTests] = useState<Record<string, Connection>>({})
  const [testing, setTesting] = useState('')
  const workspace = useResource<Workspace>('/workspace')
  async function testModel(provider: string) {
    setTesting(provider)
    try {
      const result = await write<Connection>('/connections/test', { provider })
      setTests((previous) => ({ ...previous, [provider]: result }))
    } catch (reason) {
      setTests((previous) => ({ ...previous, [provider]: { state: 'unavailable', detail: errorMessage(reason) } }))
    } finally { setTesting('') }
  }
  const connections = useResource<Connections>('/connections', 15000, refresh)
  return <>
    <PageHeading title="Connections" subtitle="Inspect the services and optional integrations available to this workspace."
      actions={<button className="button secondary" onClick={() => setRefresh(refresh + 1)}>
        <RefreshCw size={16} aria-hidden /> Refresh checks</button>} />
    {connections.error && <Notice>{connections.error}</Notice>}
    {!connections.value && !connections.error && <Waiting label="Checking the local services…" />}
    {connections.value && <div className="connection-grid">{connectionInfo.map(({ key, title, subtitle, icon: Icon }) => {
      const status = tests[key] ?? connections.value![key]
      return <section className="panel connection-card" key={key}>
        <div><span className="icon-tile"><Icon size={20} aria-hidden /></span>
          <span className={'pill ' + (status.state === 'ok' ? 'good' : status.state === 'unavailable' ? 'bad' : 'neutral')}>
            <span className="dot" />{healthLabels[status.state]}
          </span></div>
        <h2>{title}</h2><p>{subtitle}</p><small>{status.detail}</small>
        {['ollama', 'openai', 'anthropic'].includes(key) && !workspace.value?.public_demo &&
          <button className="button secondary small" disabled={!!testing || status.state === 'not_configured'}
            onClick={() => void testModel(key)}>{testing === key ? 'Checking…' : 'Test model access'}</button>}
      </section>
    })}</div>}
    {!workspace.value?.public_demo && <section className="panel connection-setup">
      <h2>Configure a model on the server</h2>
      <p>For OpenAI, set <code>OPENAI_API_KEY</code> and <code>OPENAI_MODEL</code>.
        For Claude, set <code>ANTHROPIC_API_KEY</code> and <code>ANTHROPIC_MODEL</code>.
        Restart the API, test access here, then choose the provider in New Investigation.</p>
      <p>Use your local <code>.env</code> file or your hosting provider’s secret settings.</p>
    </section>}
  </>
}

function EvaluationResults({ result }: { result: Evaluation }) {
  const complete = result.status === 'completed'
  return <>
    <div className="panel evaluation-status">
      <div><strong>{strategyLabels[result.strategy]}</strong><p>{result.dataset_version} · {result.cases.length} of {result.total_cases} cases</p></div>
      {complete ? <a className="button secondary small" href={evaluationLink(result.id)} download><Download size={16} aria-hidden /> Export results</a>
        : <span className={'pill ' + (result.status === 'failed' ? 'bad' : 'active')} role="status">{result.status}</span>}
    </div>
    <ModeBanner mode={result.mode} model={result.model} />
    {result.judge_model && <p className="muted bench-judge">Quality scoring uses local Ollama · {result.judge_model}</p>}
    {result.error && <Notice>{result.error}</Notice>}
    <div className="evaluation-metrics">{(['single', 'multi'] as const).map((strategy) => {
      const stats = result.summaries[strategy]
      if (!stats) return null
      return <section className="panel stat-card" key={strategy}>
        <div className="eyebrow">{strategyLabels[strategy]}</div>
        <strong>{stats.passed}<span> / {stats.completed} passed</span></strong>
        <p>{stats.median_duration_ms} ms median · {stats.tool_calls} MCP calls</p>
        {!!stats.holdout_completed && <p>Held-out cases · {stats.holdout_passed}/{stats.holdout_completed} passed</p>}
      </section>
    })}</div>
    {result.cases.length > 0 && <section className="panel table-panel">
      <div className="section-heading"><div><h2>Scenario results</h2><p>Open a row for reference answers and individual checks.</p></div></div>
      {result.cases.map((row) => <details className="evaluation-case" key={row.scenario_id + row.strategy}>
        <summary><span><strong>{row.title}</strong><small>{strategyLabels[row.strategy]} · {row.suite === 'holdout' ? 'Held-out case · ' : ''}{row.duration_ms} ms</small></span>
          <span className={'pill ' + (row.passed ? 'good' : 'bad')}>{row.passed ? 'Passed' : 'Failed'}</span></summary>
        <div className="case-details">
          <p>{row.question}</p>
          {row.error && <Notice>{row.error}</Notice>}
          <ul className="check-grid">{Object.entries(row.checks).map(([name, passed]) => <li key={name}>
            <span>{name.replaceAll('_', ' ')}</span>
            <span className={'pill ' + (passed === null ? 'neutral' : passed ? 'good' : 'bad')}>{passed === null ? 'N/A' : passed ? 'Pass' : 'Fail'}</span>
          </li>)}</ul>
          <p className="muted">Version {row.version} · {row.tool_calls} tool calls · {row.token_count === null ? 'Tokens N/A' : row.token_count + ' tokens'}</p>
          <code className="hash">Task {row.task_hash}</code>
          {row.judge && <details className="payload-details"><summary>LLM judge · {row.judge.model}</summary>
            {row.judge.error ? <Notice>{row.judge.error}</Notice> : row.judge.judgment && <>
              <ul className="check-grid">{Object.entries(row.judge.judgment.scores).map(([axis, score]) =>
                <li key={axis}>{axis}<span className="pill neutral">{score}/5</span></li>)}</ul>
              <p>{row.judge.judgment.rationale}</p>
              <p className="hash">{row.judge.judgment.evidence_ids.join(' · ')}</p>
            </>}
          </details>}
          <details className="payload-details"><summary>Reference and observed values</summary>
            <pre>{JSON.stringify({ expected: row.expected, observed: row.observed }, null, 2)}</pre></details>
        </div>
      </details>)}
    </section>}
  </>
}

export function EvaluationsPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const connections = useResource<Connections>('/connections')
  const workspace = useResource<Workspace>('/workspace')
  const runs = useResource<EvaluationSummary[]>('/evaluations', 3500)
  const evaluation = useResource<Evaluation>(id ? '/evaluations/' + encodeURIComponent(id) : null, 1000)
  const [strategy, setStrategy] = useState<Strategy>('compare')
  const [mode, setMode] = useState<Mode>('demo')
  const [judge, setJudge] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const effectiveMode = mode

  async function run(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const job = await write<{ id: string }>('/evaluations', { strategy, mode: effectiveMode, judge: judge && connections.value?.judge.state === 'ok' })
      navigate('/evaluations/' + job.id)
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }
  return <>
    <PageHeading title="Evaluations" subtitle="Compare sequential and parallel investigations on the same versioned cases." />
    <div className="evaluation-layout">
      <div className="evaluation-main">
        <form className="panel eval-form" onSubmit={run}>
          <div><label htmlFor="strategy">Experiment</label>
            <select id="strategy" value={strategy} onChange={(event) => setStrategy(event.target.value as Strategy)}>
              {Object.entries(strategyLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
            </select></div>
          <div><label htmlFor="evaluation-mode">Execution mode</label>
            <select id="evaluation-mode" value={effectiveMode} onChange={(event) => setMode(event.target.value as Mode)}>
              <ModeOptions connections={connections.value} liveAllowed={workspace.value?.live_models ?? false} />
            </select></div>
          <button className="button primary" disabled={busy || !workspace.value?.run_benchmarks || !modelAvailable(connections.value, mode)}><Play size={16} aria-hidden />{busy ? 'Starting…' : 'Run benchmark'}</button>
          {connections.value?.judge.state === 'ok' && <label className="judge-toggle">
            <input type="checkbox" checked={judge} onChange={(event) => setJudge(event.target.checked)} />
            Score report quality with the configured judge
          </label>}
        </form>
        {workspace.value?.public_demo && <p className="public-evaluation-note">Saved benchmark results show the project’s verified cases. New benchmark runs are managed by the owner.</p>}
        {error && <Notice>{error}</Notice>}
        {evaluation.error && <Notice>{evaluation.error}</Notice>}
        {!id && <Empty title="Select an experiment" text="The benchmark checks arithmetic, provenance, scope, uncertainty, tool limits, and approval." />}
        {id && !evaluation.value && !evaluation.error && <Waiting label="Loading benchmark…" />}
        {evaluation.value && <EvaluationResults result={evaluation.value} />}
      </div>
      <aside className="evaluation-aside">
        <section className="panel review-panel">
          <h2>Recent benchmarks</h2>
          {runs.error && <Notice>{runs.error}</Notice>}
          {!runs.value && !runs.error && <Waiting />}
          {runs.value?.length === 0 && <p className="muted">No benchmark runs yet.</p>}
          <div className="benchmark-list">{runs.value?.map((row) =>
            <Link to={'/evaluations/' + row.id} key={row.id} aria-current={row.id === id ? 'page' : undefined}>
              <strong>{strategyLabels[row.strategy]}</strong>
              <small>{localDateLabel(row.created_at)} · {row.id === evaluation.value?.id ? evaluation.value.status : row.status}</small>
            </Link>,
          )}</div>
        </section>
        {!workspace.value?.public_demo && <CalibrationPanel connection={connections.value?.judge} />}
      </aside>
    </div>
  </>
}
