import { AlertCircle, ArrowRight, CircleHelp, FlaskConical, LoaderCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { dateLabel, demoLabel, modeNames, type Mode, type Scope, type Status } from './api'

const statuses: Record<Status, { name: string; tone: string }> = {
  queued: { name: 'Queued', tone: 'neutral' },
  running: { name: 'Running', tone: 'active' },
  awaiting_review: { name: 'Awaiting review', tone: 'warning' },
  review_queued: { name: 'Decision queued', tone: 'active' },
  reviewing: { name: 'Applying decision', tone: 'active' },
  approved: { name: 'Approved', tone: 'good' },
  rejected: { name: 'Rejected', tone: 'bad' },
  failed: { name: 'Failed', tone: 'bad' },
  canceled: { name: 'Canceled', tone: 'neutral' },
  needs_clarification: { name: 'Needs clarification', tone: 'warning' },
}

export function StatusPill({ status }: { status: Status }) {
  const { name, tone } = statuses[status]
  return <span className={'pill ' + tone}><span className="dot" />{name}</span>
}

export function PageHeading({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return <header className="page-heading">
    <div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{actions}
  </header>
}

export function ModeBanner({ mode = 'demo', model }: { mode?: Mode; model?: string | null }) {
  return <div className="mode-banner">
    <FlaskConical size={16} aria-hidden />
    <span>{mode === 'demo' ? demoLabel : 'Live ' + modeNames[mode] + (model ? ' · ' + model : '')}</span>
  </div>
}

export function Waiting({ label = 'Loading…' }: { label?: string }) {
  return <div className="empty" role="status"><LoaderCircle className="spin" size={21} aria-hidden />{label}</div>
}

export function Notice({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return <div className="notice" role="alert"><AlertCircle size={18} aria-hidden /><span>{children}</span>{action}</div>
}

export function Empty({ title, text, action }: { title: string; text: string; action?: ReactNode }) {
  return <div className="empty">
    <CircleHelp size={24} aria-hidden /><strong>{title}</strong><p>{text}</p>{action}
  </div>
}

export function ScopeLabel({ scope }: { scope: Scope }) {
  return <span className="scope-label">{dateLabel(scope.baseline.start)}–{dateLabel(scope.baseline.end)}
    <ArrowRight size={13} aria-hidden />{dateLabel(scope.current.start)}–{dateLabel(scope.current.end)} · UTC · {scope.segment}
  </span>
}

export function Back({ to, label }: { to: string; label: string }) {
  return <Link to={to} className="back-link">← {label}</Link>
}
