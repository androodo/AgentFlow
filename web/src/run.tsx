import { ArrowRight, Ban, ClipboardCheck, Fingerprint } from 'lucide-react'
import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import {
  errorMessage, runPath, useResource, write, type EventPage, type Evidence, type Report, type ReviewAction, type Run,
} from './api'
import { ActivityView, GraphMap } from './activity'
import { Back, Empty, ModeBanner, Notice, PageHeading, ScopeLabel, StatusPill, Waiting } from './components'
import { EvidenceView } from './evidence'
import { InvestigationSummary } from './summary'
import { ApprovedReport, ReviewView } from './reports'

const tabs = [
  { id: 'summary', label: 'Findings' }, { id: 'evidence', label: 'Evidence' },
  { id: 'review', label: 'Review' }, { id: 'report', label: 'Final report' },
  { id: 'activity', label: 'Execution details' },
]
const working = ['queued', 'running', 'review_queued', 'reviewing']
const cancelable = ['queued', 'running', 'awaiting_review']

export function RunDetail() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const [filter, setFilter] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [submitted, setSubmitted] = useState('')
  const activeTab = tabs.find(({ id: tab }) => tab === params.get('tab'))?.id ?? 'summary'
  const path = runPath(id)
  const investigation = useResource<Run>(path, 1100, refresh)
  const run = investigation.value
  const eventData = useResource<EventPage>(run ? path + '/events' : null, 1200, refresh)
  const evidence = useResource<Evidence[]>(activeTab === 'evidence' && run ? path + '/evidence' : null, run?.draft ? 0 : 1500, refresh)
  const finalReport = useResource<Report>(activeTab === 'report' && run?.status === 'approved' ? path + '/report' : null, 0, refresh)

  function goTo(tab: string, selected?: string) {
    setParams(selected ? { tab, evidence: selected } : { tab }, { preventScrollReset: true })
  }
  const openEvidence = (selected: string) => goTo('evidence', selected)

  async function decide(action: ReviewAction, note: string) {
    if (!run?.pending || busy) return
    const interruptId = run.pending.interrupt_id
    setBusy(true)
    setError('')
    try {
      await write<Run>(path + '/review', { action, note, interrupt_id: interruptId })
      setSubmitted(interruptId)
      setRefresh((value) => value + 1)
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    setBusy(true)
    setError('')
    try {
      await write<Run>(path + '/cancel', {})
      setRefresh((value) => value + 1)
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  if (!run) return <><Back to="/" label="Overview" />{investigation.error
    ? <Notice action={<button className="button secondary small" onClick={() => setRefresh(refresh + 1)}>Retry</button>}>{investigation.error}</Notice>
    : <Waiting label="Loading investigation…" />}</>

  const events = eventData.value?.events ?? []
  const isWorking = working.includes(run.status)
  return <>
    <Back to="/" label="Overview" />
    <PageHeading title={run.scenario.title} subtitle={run.question}
      actions={<div className="heading-actions">
        <StatusPill status={run.status} />
        {run.status === 'awaiting_review' && activeTab !== 'review' && <button className="button primary" onClick={() => goTo('review')}>
          <ClipboardCheck size={17} aria-hidden /> Review draft
        </button>}
        {run.status === 'approved' && activeTab !== 'report' &&
          <button className="button primary" onClick={() => goTo('report')}>Open final report <ArrowRight size={16} aria-hidden /></button>}
      </div>} />
    <div className="run-metadata"><ModeBanner mode={run.mode} model={run.model} /><ScopeLabel scope={run.scenario.scope} />
      {cancelable.includes(run.status) && <button className="button subtle small" onClick={() => void cancel()} disabled={busy}>
        <Ban size={15} aria-hidden />Cancel investigation
      </button>}
    </div>
    {(investigation.error || run.error || (activeTab !== 'review' && error)) &&
      <Notice>{investigation.error ?? run.error ?? error}</Notice>}
    <nav className="tabs" aria-label="Investigation views">
      {tabs.map((tab) => <button key={tab.id} className={activeTab === tab.id ? 'active' : ''}
        aria-current={activeTab === tab.id ? 'page' : undefined} onClick={() => goTo(tab.id)}>{tab.label}</button>)}
    </nav>
    {activeTab === 'summary' && <InvestigationSummary run={run} events={events} onEvidence={openEvidence}
      onReview={() => goTo('review')} onDetails={() => goTo('activity')} />}
    {activeTab === 'activity' && <>
      <GraphMap run={run} events={events} onNode={(node) => setFilter(node)} />
      {eventData.error && <Notice>{eventData.error}</Notice>}
      {!eventData.value && isWorking && <Waiting label="Waiting for workflow events…" />}
      <ActivityView events={events} filter={filter} onFilter={setFilter} />
    </>}
    {activeTab === 'evidence' && (evidence.error ? <Notice>{evidence.error}</Notice> : evidence.value
      ? <EvidenceView runId={run.id} evidence={evidence.value} selection={params.get('evidence')} onSelect={openEvidence} />
      : <Waiting label="Loading evidence…" />)}
    {activeTab === 'review' && <ReviewView run={run} busy={busy || submitted === run.pending?.interrupt_id}
      error={error} onDecision={(action, note) => void decide(action, note)} onEvidence={openEvidence} />}
    {activeTab === 'report' && (run.status === 'approved'
      ? finalReport.error ? <Notice>{finalReport.error}</Notice> : finalReport.value
        ? <ApprovedReport report={finalReport.value} run={run} onEvidence={openEvidence} />
        : <Waiting label="Loading the approved report…" />
      : <Empty title="Final report requires approval" text="Review the cited draft before exporting."
        action={<button className="button secondary" onClick={() => goTo('review')}>Open review</button>} />)}
    <details className="run-identifiers"><summary>Investigation ID</summary><div className="run-id"><Fingerprint size={15} aria-hidden /><code>{run.id}</code></div></details>
  </>
}
