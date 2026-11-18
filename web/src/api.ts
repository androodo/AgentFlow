import { useEffect, useState } from 'react'

export type Mode = 'demo' | 'ollama' | 'openai' | 'anthropic'
export const modeNames: Record<Mode, string> = { demo: 'Rule-based demo', ollama: 'Local Ollama', openai: 'OpenAI', anthropic: 'Claude' }
export type Workspace = {
  public_demo: boolean; custom_questions: boolean; run_benchmarks: boolean; live_models: boolean
  investigation_modes?: Mode[] | null
  dataset: { name: string; fictional: boolean; description: string; version: string; scenario_count: number
    tables: { name: string; rows: number; purpose: string }[] }
}
export type Explanation = { title: string; assessment: string; uncertainty: string; supporting_evidence: string[]; contradicting_evidence: string[] }
export function modelAvailable(connections: Connections | undefined, mode: Mode) {
  return mode === 'demo' || connections?.[mode]?.state === 'ok' || connections?.[mode]?.state === 'configured'
}
export const demoLabel = 'Rule-based demo — no LLM involved'
export type Window = { start: string; end: string }
export type Scope = { day: string; segment: 'all' | 'web' | 'mobile'; baseline: Window; current: Window }
export type Scenario = {
  id: string; title: string; description: string; question: string; scope: Scope; version: number; task_hash: string; suite: 'development' | 'holdout'
}
export type Status =
  | 'queued' | 'running' | 'awaiting_review' | 'review_queued' | 'reviewing' | 'approved'
  | 'rejected' | 'failed' | 'canceled' | 'needs_clarification'
export type ReviewAction = 'approve' | 'reject' | 'revise'
export type Review = { action: ReviewAction; created_at: string; note: string; round: number; interrupt_id: string }
export type Totals = {
  sessions: number; checkout_starts: number; purchases: number; conversion_pct: number | null
  observed_days: number; complete: boolean
}
export type Comparison = { baseline: Totals; current: Totals; delta: number | null }
export type Finding = { kind: 'observation' | 'hypothesis'; title: string; text: string; evidence_ids: string[] }
export type Report = {
  title: string; headline: string; confidence: string; hypothesis: string; scope: Scope; mode: Mode; mode_label: string
  findings: Finding[]; limitations: string[]; unresolved_questions: string[]; next_actions: string[]
  comparison: Comparison | null; review_round: number; scenario_id: string; explanations?: Explanation[]; analysis_source?: string
}
export type RunSummary = {
  id: string; scenario: Scenario; question: string; mode: Mode; mode_label: string; model: string | null
  status: Status; created_at: string; updated_at: string
}
export type Run = RunSummary & {
  checkpoint_id: string | null; pending: { round: number; interrupt_id: string } | null
  draft: Report | null; reviews: Review[]; error: string | null
}
export type RunEvent = { id: number; occurred_at: string; node: string; kind: string; detail: Record<string, unknown> }
export type EventPage = { events: RunEvent[]; next_cursor: number }
export type Evidence = {
  id: string; tool: string; request: Record<string, unknown>; sources: { id: string; table: string }[]
  payload: Record<string, unknown>
}
export type Connection = { state: 'ok' | 'unavailable' | 'not_configured' | 'configured'; detail: string }
export type Connections = Record<'api' | 'database' | 'mcp' | 'ollama' | 'openai' | 'anthropic' | 'langsmith' | 'judge', Connection>
export type Strategy = 'single' | 'multi' | 'compare'
export type EvaluationSummary = {
  id: string; status: 'queued' | 'running' | 'completed' | 'failed'; strategy: Strategy
  mode: Mode; model: string | null; created_at: string; completed_at: string | null; error: string | null
}
export type Judgment = { scores: Record<string, number>; rationale: string; evidence_ids: string[] }
type BenchmarkResult = {
  suite?: string; scenario_id: string; title: string; strategy: 'single' | 'multi'; mode: Mode; version: number
  task_hash: string; passed: boolean; model: string | null; started_at: string; duration_ms: number
  tool_calls: number; token_count: number | null; checks: Record<string, boolean | null>
  judge?: { model: string; judgment?: Judgment; error?: string }
  expected: Record<string, unknown>; observed: Record<string, unknown> | null; error: string | null; question: string
}
export type Evaluation = EvaluationSummary & {
  dataset_version: string; total_cases: number; cases: BenchmarkResult[]; judge_model?: string | null
  summaries: Partial<Record<'single' | 'multi', {
    holdout_completed?: number; holdout_passed?: number; completed: number; passed: number; median_duration_ms: number; tool_calls: number
  }>>
}

const prefix = '/api/v1'
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(prefix + path, options)
  const body = await response.json().catch(() => undefined)
  if (!response.ok) throw new ApiError(body?.error?.message ?? 'Unable to reach the AgentFlow API.', response.status)
  if (body === undefined) throw new ApiError('The API returned an invalid response.', response.status)
  return body as T
}

export function write<T>(path: string, payload: unknown) {
  return request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}

export function useResource<T>(path: string | null, interval = 0, refresh = 0) {
  const [state, setState] = useState<{ path: string; value?: T; error?: string }>()
  useEffect(() => {
    if (!path) return
    const abort = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function fetchResource(currentPath: string) {
      try {
        const value = await request<T>(currentPath, { signal: abort.signal })
        if (!abort.signal.aborted) setState({ path: currentPath, value })
      } catch (reason) {
        if (!abort.signal.aborted) {
          setState((previous) => ({
            path: currentPath,
            value: previous?.path === currentPath ? previous.value : undefined,
            error: errorMessage(reason),
          }))
        }
      } finally {
        if (!abort.signal.aborted && interval) timer = setTimeout(() => void fetchResource(currentPath), interval)
      }
    }
    void fetchResource(path)
    return () => { abort.abort(); clearTimeout(timer) }
  }, [path, interval, refresh])
  return path && state?.path === path ? state : { value: undefined, error: undefined }
}

export const runPath = (id: string) => '/investigations/' + encodeURIComponent(id)
export const reportLink = (id: string) => prefix + runPath(id) + '/report?format=markdown'
export const evaluationLink = (id: string) => prefix + '/evaluations/' + encodeURIComponent(id) + '?format=json'
export const errorMessage = (reason: unknown) => reason instanceof Error ? reason.message : 'Something went wrong.'
export const count = (number: number) => new Intl.NumberFormat('en-US').format(number)
export const dateLabel = (date: string) => new Intl.DateTimeFormat('en-US', {
  month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC',
}).format(new Date(date))
export const localDateLabel = (timestamp: string) => new Intl.DateTimeFormat('en-US', {
  month: 'short', day: 'numeric', year: 'numeric',
}).format(new Date(timestamp))
export const timeLabel = (date: string) => new Intl.DateTimeFormat('en-US', {
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23', timeZone: 'UTC',
}).format(new Date(date))
