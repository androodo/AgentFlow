import { Check, ClipboardCheck, Copy, Download, FileText, Link2, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { reportLink, timeLabel, type Report, type ReviewAction, type Run } from './api'
import { Empty, Notice, ScopeLabel } from './components'
import { ReportAlternatives } from './summary'
import { ConversionChart } from './evidence'

export function ReportBody({ report, onEvidence }: { report: Report; onEvidence: (id: string) => void }) {
  return <article className="panel report-panel">
    <header className="report-header"><span className="icon-tile"><FileText size={20} aria-hidden /></span>
      <div><span className="report-kicker">Incident assessment</span><h2>{report.headline}</h2></div>
      <span className="pill neutral">{report.confidence} confidence</span>
    </header>
    <ScopeLabel scope={report.scope} />
    {report.comparison && <ConversionChart comparison={report.comparison} />}
    <ReportAlternatives report={report} onEvidence={onEvidence} />
    <div className="findings">
      {report.findings.map((finding) => <section key={finding.title} className={'finding ' + finding.kind}>
        <span className="finding-kind">{finding.kind}</span><h3>{finding.title}</h3><p>{finding.text}</p>
        <div className="citations">
          {finding.evidence_ids.map((id, i) => <button key={id} type="button" className="citation" title={id}
            aria-label={'Open citation ' + id} onClick={() => onEvidence(id)}>
            <Link2 size={13} aria-hidden /> Source {i + 1}</button>)}
        </div>
      </section>)}
    </div>
    {[
      { title: 'Limitations', rows: report.limitations },
      { title: 'Unresolved questions', rows: report.unresolved_questions },
      { title: 'Next actions', rows: report.next_actions },
    ].map(({ title, rows }) => <section className="report-section" key={title}><h3>{title}</h3>
      <ul>{rows.map((row) => <li key={row}>{row}</li>)}</ul></section>)}
  </article>
}

export function ReviewHistory({ run }: { run: Run }) {
  return <section className="panel review-panel">
    <div className="section-heading"><div><h2>Decision history</h2><p>Persisted review ledger · UTC</p></div></div>
    {run.reviews.length === 0
      ? <p className="muted">No decisions recorded yet.</p>
      : <ol className="review-history">{run.reviews.map((row) => <li key={row.round}>
        <div><strong>Round {row.round}</strong><span>{timeLabel(row.created_at)} UTC</span></div>
        <span className={'pill ' + (row.action === 'approve' ? 'good' : row.action === 'reject' ? 'bad' : 'warning')}>
          {{ approve: 'Approved', reject: 'Rejected', revise: 'Revision requested' }[row.action]}
        </span>
        {row.note && <p>{row.note}</p>}
      </li>)}</ol>}
  </section>
}

export function ReviewView({ run, busy, error, onDecision, onEvidence }: {
  run: Run; busy: boolean; error: string; onDecision: (action: ReviewAction, note: string) => void
  onEvidence: (id: string) => void
}) {
  const [note, setNote] = useState('')
  const [noteError, setNoteError] = useState('')
  const pending = run.status === 'awaiting_review' ? run.pending : null
  function submit(action: ReviewAction) {
    if (action === 'revise' && !note.trim()) {
      setNoteError('Add a reviewer note to request revision.')
      return
    }
    setNoteError('')
    onDecision(action, note.trim())
  }
  return <div className="review-layout">
    {run.draft ? <ReportBody report={run.draft} onEvidence={onEvidence} />
      : <Empty title="Draft pending" text="The audit and report nodes must complete before the draft is available." />}
    <aside className="review-sidebar">
      <section className="panel review-panel" aria-labelledby="review-title">
        <span className="icon-tile"><ClipboardCheck size={20} aria-hidden /></span>
        <h2 id="review-title">Human review</h2>
        {pending ? <>
          <p>Round {pending.round} · Checkpoint saved. Review the findings and citations before deciding.</p>
          {run.checkpoint_id && <details className="checkpoint"><summary>Checkpoint ID</summary><code>{run.checkpoint_id}</code></details>}
          <label htmlFor="review-note">Reviewer note <span className="muted">(optional for approve or reject)</span></label>
          <textarea id="review-note" rows={3} value={note} maxLength={600} onChange={(event) => {
            setNote(event.target.value); setNoteError('')
          }} placeholder="Add context for the decision" />
          {error && <Notice>{error}</Notice>}
          {noteError && <Notice>{noteError}</Notice>}
          <div className="review-actions">
            <button className="button primary" disabled={busy} onClick={() => submit('approve')}>
              <Check size={17} aria-hidden /> Approve report
            </button>
            {pending.round === 1 && <button className="button secondary" disabled={busy} onClick={() => submit('revise')}>Request revision</button>}
            <button className="button danger" disabled={busy} onClick={() => submit('reject')}>Reject report</button>
          </div>
        </> : <p>{run.status === 'approved' ? 'Approved. The final report is available to export.'
          : run.status === 'rejected' ? 'The reviewer rejected this draft.'
          : ['reviewing', 'review_queued'].includes(run.status) ? 'The worker is applying the persisted decision.'
          : 'Actions become available when the graph reaches its review checkpoint.'}</p>}
      </section>
      <ReviewHistory run={run} />
    </aside>
  </div>
}

export function ApprovedReport({ run, report, onEvidence }: { run: Run; report: Report; onEvidence: (id: string) => void }) {
  const [copyStatus, setCopyStatus] = useState('')
  const [error, setError] = useState('')
  async function copy() {
    setError('')
    try {
      const response = await fetch(reportLink(run.id))
      if (!response.ok) throw new Error('The Markdown report could not be retrieved.')
      await navigator.clipboard.writeText(await response.text())
      setCopyStatus('Copied')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Clipboard access failed.')
    }
  }
  return <>
    <div className="panel report-toolbar">
      <div><ShieldCheck size={22} aria-hidden /><div><strong>Approved report</strong>
        <small>Review round {report.review_round} · {run.mode_label}</small></div></div>
      <div>
        <button className="button secondary" onClick={() => void copy()}><Copy size={16} aria-hidden />{copyStatus || 'Copy Markdown'}</button>
        <a className="button primary" href={reportLink(run.id)} download><Download size={16} aria-hidden />Download Markdown</a>
      </div>
    </div>
    {error && <Notice>{error}</Notice>}
    <div className="review-layout"><ReportBody report={report} onEvidence={onEvidence} /><ReviewHistory run={run} /></div>
  </>
}
