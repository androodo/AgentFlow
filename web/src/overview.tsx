import { Activity, ArrowRight, GitBranch, Headphones, Plus, ScanSearch, ShoppingBag, Workflow } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  dateLabel, errorMessage, localDateLabel, modelAvailable, modeNames, runPath, useResource, write,
  type Connections, type Mode, type Run, type RunSummary, type Scenario, type Workspace,
} from './api'
import { Back, Empty, ModeBanner, Notice, PageHeading, ScopeLabel, StatusPill, Waiting } from './components'
import { ModeOptions } from './provider-options'

const featuredId = 'checkout-conversion-drop'
const featuredCases = ['traffic-shift', 'release-after-drop', 'support-contradiction']

function publicModesFor(workspace?: Workspace): Mode[] | undefined {
  return workspace?.public_demo ? workspace.investigation_modes ?? ['demo'] : undefined
}

function ScenarioCard({ scenario }: { scenario: Scenario }) {
  const Icon = scenario.id.includes('support') ? Headphones : scenario.id.includes('release') ? GitBranch : Activity
  return <Link className="scenario-card" to={'/new?scenario=' + encodeURIComponent(scenario.id)}>
    <div className="scenario-card-top"><span className="icon-tile"><Icon size={18} aria-hidden /></span>
      <span>{dateLabel(scenario.scope.day)}</span></div>
    <h3>{scenario.title}</h3><p>{scenario.description}</p>
    <span className="scenario-action">Investigate <ArrowRight size={14} aria-hidden /></span>
  </Link>
}

export function Overview() {
  const navigate = useNavigate()
  const scenarios = useResource<Scenario[]>('/scenarios')
  const workspace = useResource<Workspace>('/workspace')
  const runs = useResource<RunSummary[]>('/investigations?limit=8', 5000)
  const [all, setAll] = useState(false)
  const [launching, setLaunching] = useState(false)
  const [error, setError] = useState('')
  const featured = scenarios.value?.find((scenario) => scenario.id === featuredId)
  const library = all ? scenarios.value ?? [] : featuredCases.flatMap((id) => scenarios.value?.find((row) => row.id === id) ?? [])
  const publicModes = publicModesFor(workspace.value)
  const primaryMode = publicModes ? publicModes[0] : 'demo'
  const launchLabel = primaryMode === 'demo' ? 'Try demo: Checkout Conversion Drop' :
    primaryMode ? 'Investigate with ' + modeNames[primaryMode] : 'No investigation mode available'

  async function launchInvestigation() {
    if (!workspace.value || !primaryMode) return
    setLaunching(true)
    setError('')
    try {
      const run = await write<Run>('/investigations', { scenario_id: featuredId, mode: primaryMode })
      navigate(runPath(run.id))
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setLaunching(false)
    }
  }

  return <>
    <PageHeading title="Operations workspace" subtitle="Find out what changed, check the evidence, and decide what to do next."
      actions={<Link className="button secondary" to="/new"><Plus size={17} aria-hidden />New investigation</Link>} />
    <section className="retailer-context">
      <span className="icon-tile"><ShoppingBag size={20} aria-hidden /></span>
      <p><strong>Meet Northstar Shop.</strong> A fictional retailer with web and mobile shopping.
        All records are synthetic, so you can explore incidents safely.</p>
      <Link to="/data">Explore the data <ArrowRight size={15} aria-hidden /></Link>
    </section>
    {scenarios.error && <Notice>{scenarios.error}</Notice>}
    {workspace.error && <Notice>{workspace.error}</Notice>}
    {!scenarios.value && !scenarios.error && <Waiting label="Loading the scenario library…" />}
    {featured && <section className="hero incident-hero" aria-labelledby="featured-title">
      <div className="hero-copy">
        <div className="eyebrow">Start with a business question</div>
        <h2 id="featured-title">Why are fewer shoppers finishing checkout?</h2>
        <p>A mobile checkout update went live. Purchases fell. Follow the payment records, release history,
          and customer complaints to see which explanation the evidence supports.</p>
        <button className="button primary" disabled={!workspace.value || !primaryMode || launching} onClick={() => void launchInvestigation()}>
          {launching ? 'Starting investigation…' : launchLabel}<ArrowRight size={17} aria-hidden />
        </button>
        {workspace.value && primaryMode === 'demo' && <div className="hero-meta"><span>Rule-based demo — no LLM involved</span></div>}
      </div>
      <div className="incident-story" aria-label="The investigation steps">
        <div><Activity size={21} aria-hidden /><span><strong>Understand the change</strong><small>Compare checkout before and after the update.</small></span></div>
        <div><ScanSearch size={21} aria-hidden /><span><strong>Follow the evidence</strong><small>Check payments, release timing, and support.</small></span></div>
        <div><Workflow size={21} aria-hidden /><span><strong>Review the assessment</strong><small>Inspect citations and approve your report.</small></span></div>
      </div>
    </section>}
    {error && <Notice>{error}</Notice>}
    <section className="section" aria-labelledby="library">
      <div className="section-heading"><div><h2 id="library">Scenario library</h2>
        <p>Each case asks a different question about the same fictional retailer.</p></div>
        {!!scenarios.value?.length && <button className="button secondary small" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? 'Show featured cases' : 'View all ' + scenarios.value.length + ' cases'}<ArrowRight size={15} aria-hidden />
        </button>}
      </div>
      <div className="scenario-grid">{library.map((scenario) => <ScenarioCard key={scenario.id} scenario={scenario} />)}</div>
    </section>
    <section className="section" aria-labelledby="recent">
      <div className="section-heading"><div><h2 id="recent">Your investigations</h2><p>Continue reviewing findings or open an approved report.</p></div></div>
      {runs.error && <Notice>{runs.error}</Notice>}
      {!runs.value && !runs.error && <Waiting label="Loading investigations…" />}
      {runs.value?.length === 0 && <Empty title="Your first investigation starts here" text="Try the checkout case above. You can check every finding against its source." />}
      {!!runs.value?.length && <div className="panel recent-list">
        {runs.value.map((run) => <Link to={runPath(run.id)} key={run.id} className="recent-row">
          <span className="icon-tile"><Workflow size={17} aria-hidden /></span><div><strong>{run.scenario.title}</strong>
            <small>{modeNames[run.mode]} · {localDateLabel(run.created_at)}</small></div>
          <StatusPill status={run.status} /><ArrowRight size={16} aria-hidden />
        </Link>)}
      </div>}
    </section>
  </>
}

export function NewInvestigation() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const library = useResource<Scenario[]>('/scenarios')
  const workspace = useResource<Workspace>('/workspace')
  const publicDemo = workspace.value?.public_demo
  const connections = useResource<Connections>(publicDemo === false ? '/connections' : null, 15000)
  const [selected, setSelected] = useState(params.get('scenario') ?? featuredId)
  const [question, setQuestion] = useState<string>()
  const [selectedMode, setMode] = useState<Mode>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const scenario = library.value?.find((row) => row.id === selected) ?? library.value?.[0]
  const publicModes = publicModesFor(workspace.value)
  const mode = publicModes ? (selectedMode && publicModes.includes(selectedMode) ? selectedMode : publicModes[0]) : selectedMode ?? 'demo'
  const canRun = workspace.value && mode && (publicModes || mode === 'demo' ||
    (workspace.value.live_models && modelAvailable(connections.value, mode)))

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!scenario || busy || !mode || !canRun) return
    setBusy(true)
    setError('')
    try {
      const run = await write<Run>('/investigations', {
        scenario_id: scenario.id, question: publicDemo ? null : question?.trim() || null, mode,
      })
      navigate(runPath(run.id))
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  return <>
    <Back to="/" label="Overview" />
    <PageHeading title="New investigation" subtitle="Choose an incident and ask a question about the retailer's records." />
    {library.error && <Notice>{library.error}</Notice>}
    {workspace.error && <Notice>{workspace.error}</Notice>}
    {!library.value && !library.error && <Waiting label="Loading scenarios…" />}
    {scenario && <form className="form-layout" onSubmit={submit}>
      <div className="panel form-panel">
        <label htmlFor="scenario">Scenario</label>
        <select id="scenario" value={scenario.id} onChange={(event) => {
          setSelected(event.target.value); setQuestion(undefined)
        }}>
          {library.value?.map((row) => <option key={row.id} value={row.id}>{row.title}</option>)}
        </select>
        <p className="field-hint">{scenario.description}</p>
        <label htmlFor="question">Investigation question</label>
        <textarea id="question" rows={4} maxLength={600} minLength={8} readOnly={publicDemo}
          value={question ?? scenario.question} onChange={(event) => setQuestion(event.target.value)}
          aria-describedby="question-hint" />
        <p className="field-hint" id="question-hint">{publicDemo
          ? 'This public demo uses the seeded questions. Each browser has its own review session.'
          : 'Ask about checkout, releases, or support within this incident.'}</p>
        {workspace.value && (mode ? <>
          <label htmlFor="mode">Execution mode</label>
          <select id="mode" value={mode} onChange={(event) => setMode(event.target.value as Mode)}>
            <ModeOptions connections={connections.value} liveAllowed={workspace.value.live_models} publicModes={publicModes} />
          </select>
        </> : <Notice>Live investigations are currently unavailable.</Notice>)}
        {publicModes?.some(value => value !== 'demo') && <p className="field-hint">Live investigations have a daily limit.</p>}
        {!publicDemo && <p className="field-hint">OpenAI, Claude, and local Ollama use server configuration.
          <Link to="/connections"> Check model connections</Link></p>}
        {error && <Notice>{error}</Notice>}
        <button type="submit" className="button primary" disabled={busy || !canRun}>
          {busy ? 'Starting investigation…' : 'Start investigation'} <ArrowRight size={17} aria-hidden />
        </button>
      </div>
      <aside className="panel form-aside"><span className="icon-tile"><ScanSearch size={18} aria-hidden /></span>
        <h2>The data you’ll investigate</h2><p>Synthetic checkout, payment, deployment, and support records from Northstar Shop.</p>
        <ScopeLabel scope={scenario.scope} />{workspace.value && mode && <ModeBanner mode={mode} />}
        <p>AgentFlow will compare the records and prepare a cited assessment for your review.</p>
        <Link to="/data" className="back-link">Understand this dataset →</Link>
      </aside>
    </form>}
  </>
}
