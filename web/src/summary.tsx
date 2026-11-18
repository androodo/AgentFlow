import { ArrowRight, CheckCircle2, Clock3, HelpCircle, Link2, SearchCheck } from 'lucide-react'
import { type Report, type Run, type RunEvent } from './api'
import { ConversionChart } from './evidence'

export function InvestigationSummary({ run, events, onEvidence, onReview, onDetails }: {
  run: Run; events: RunEvent[]; onEvidence: (id: string) => void; onReview: () => void; onDetails: () => void
}) {
  const report = run.draft
  if (!report) {
    const stages = [
      { name: 'Choose the relevant data', node: 'planner' },
      { name: 'Check the business records', node: 'audit' },
      { name: 'Prepare findings for review', node: 'report' },
    ]
    return <section className="panel investigation-progress">
      <span className="icon-tile"><SearchCheck size={24} aria-hidden /></span>
      <h2>{run.status === 'failed' ? 'The investigation needs attention' : 'Investigating your question'}</h2>
      <p>Checking the selected retailer records and comparing the evidence.</p>
      <ol>{stages.map(({ name, node }) => {
        const done = events.some((event) => event.node === node && event.kind === 'node_finished')
        return <li key={node}>{done ? <CheckCircle2 size={19} aria-hidden /> : <Clock3 size={19} aria-hidden />}
          <span>{name}</span><small>{done ? 'Done' : 'Pending'}</small></li>
      })}</ol>
      <button className="button secondary" onClick={onDetails}>View execution details <ArrowRight size={16} aria-hidden /></button>
    </section>
  }
  const hypotheses = report.findings.filter((item) => item.kind === 'hypothesis')
  const observations = report.findings.filter((item) => item.kind === 'observation')
  const leading = hypotheses[0]
  return <div className="summary-layout">
    <section className="panel assessment-lead">
      <div className="assessment-kicker"><SearchCheck size={17} aria-hidden />
        {report.analysis_source === 'model' ? 'Model assessment · evidence checked' : 'Demo assessment · evidence checked'}
        <span className="pill neutral">{report.confidence} confidence</span>
      </div>
      <h2>{report.headline}</h2>
      {leading && <p>{leading.text}</p>}
      {run.status === 'awaiting_review' && <button className="button primary" onClick={onReview}>
        Review findings <ArrowRight size={17} aria-hidden /></button>}
    </section>
    <section className="summary-columns">
      <div className="panel summary-section">
        <h2>What changed?</h2>
        {report.comparison && <ConversionChart comparison={report.comparison} />}
        <ul className="fact-list">{observations.map((item) => <li key={item.title}>
          <strong>{item.title}</strong><p>{item.text}</p>
          <CitationLinks ids={item.evidence_ids} onEvidence={onEvidence} />
        </li>)}</ul>
      </div>
      <div className="summary-right">
        <section className="panel summary-section">
          <h2>What might explain it?</h2>
          {report.explanations?.length ? <ol className="hypothesis-list">
            {report.explanations.map((item, index) => <li key={index}>
              <span className="hypothesis-rank">{index === 0 ? 'Leading hypothesis' : 'Alternative explanation'}</span>
              <h3>{item.title}</h3><p>{item.assessment}</p>
              <CitationLinks ids={item.supporting_evidence} onEvidence={onEvidence} />
              {item.contradicting_evidence.length > 0 && <div className="contradiction"><strong>Evidence against</strong>
                <CitationLinks ids={item.contradicting_evidence} onEvidence={onEvidence} /></div>}
              <div className="uncertainty"><HelpCircle size={15} aria-hidden /><p>{item.uncertainty}</p></div>
            </li>)}
          </ol> : <><p>{leading?.text}</p><div className="uncertainty"><HelpCircle size={16} aria-hidden />
            <p>{report.limitations[0]}</p></div></>}
        </section>
        <section className="panel summary-section">
          <h2>What should happen next?</h2>
          <ul className="next-action-list">{report.next_actions.map((action) => <li key={action}>{action}</li>)}</ul>
          <details className="assessment-limits"><summary>Evidence gaps and limitations</summary>
            <ul>{[...report.unresolved_questions, ...report.limitations].map((text, i) => <li key={i}>{text}</li>)}</ul>
          </details>
        </section>
      </div>
    </section>
  </div>
}

export function CitationLinks({ ids, onEvidence }: { ids: string[]; onEvidence: (id: string) => void }) {
  return <div className="citations">{ids.map((id, i) => <button key={id} type="button" className="citation"
    title={id} aria-label={'Open citation ' + id} onClick={() => onEvidence(id)}>
    <Link2 size={13} aria-hidden />Evidence {i + 1}</button>)}</div>
}

export function ReportAlternatives({ report, onEvidence }: { report: Report; onEvidence: (id: string) => void }) {
  if (!report.explanations?.length) return null
  return <section className="report-section"><h3>Competing explanations</h3>
    {report.explanations.map((item, index) => <div className="report-alternative" key={index}>
      <strong>{item.title}</strong><p>{item.assessment}</p><p className="muted">{item.uncertainty}</p>
      <CitationLinks ids={item.supporting_evidence} onEvidence={onEvidence} />
    </div>)}</section>
}
