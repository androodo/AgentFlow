import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { chromium, expect } from '@playwright/test'

const [baseURL, directory, paceInput = '1'] = process.argv.slice(2)
const pace = Number(paceInput)
assert(baseURL && directory && Number.isFinite(pace) && pace > 0 && pace <= 2)
const origin = new URL(baseURL)
assert.equal(origin.hostname, '127.0.0.1', 'This recording runs only against isolated local services.')
assert.equal(origin.protocol, 'http:')
await mkdir(directory, { recursive: true })
const browser = await chromium.launch({ headless: true })
const dimensions = { width: 1600, height: 900 }
const context = await browser.newContext({
  baseURL, viewport: dimensions, recordVideo: { dir: directory, size: dimensions },
  acceptDownloads: true, reducedMotion: 'reduce',
})
const started = performance.now()
const page = await context.newPage()
const errors = []
page.on('pageerror', error => errors.push(error.message))
page.setDefaultTimeout(14000)
const video = page.video()
const beats = []
const chapters = []
const elapsed = () => (performance.now() - started) / 1000

async function hold(ms) {
  await new Promise(resolve => setTimeout(resolve, ms * pace))
}

async function beat(label, caption, ms, chapter = false) {
  const start = elapsed()
  if (beats.length) beats.at(-1).end = start
  beats.push({ title: label, caption, start, end: start })
  if (chapter) chapters.push({ title: label, at: start })
  console.log(label)
  await hold(ms)
}

async function click(locator) {
  await locator.scrollIntoViewIfNeeded()
  const box = await locator.boundingBox()
  assert(box)
  await page.mouse.move(box.x + Math.min(box.width / 2, 170), box.y + box.height / 2, { steps: 8 })
  await hold(350)
  await locator.click({ position: { x: Math.min(box.width / 2, 170), y: box.height / 2 } })
}

async function frame(locator, offset = 140) {
  await locator.waitFor({ state: 'visible' })
  await locator.evaluate((el, y) => window.scrollBy({ top: el.getBoundingClientRect().top - y, behavior: 'instant' }), offset)
}

const button = name => page.getByRole('button', { name, exact: true })
const heading = name => page.getByRole('heading', { name, exact: true })

// The pointer overlay records real browser movement without interfering with input.
await context.addInitScript(() => {
  let cursor, timer
  function move(event) {
    if (!document.body) return
    if (!cursor?.isConnected) {
      cursor = document.createElement('div')
      cursor.setAttribute('aria-hidden', 'true')
      cursor.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483647;width:16px;height:16px;border:2px solid #6d4aff;border-radius:100%;box-shadow:0 0 0 2px white;background:#9a7aff30;transform:translate(-50%,-50%)'
      document.body.append(cursor)
    }
    cursor.style.left = event.clientX + 'px'
    cursor.style.top = event.clientY + 'px'
    cursor.style.visibility = 'visible'
    clearTimeout(timer)
    timer = setTimeout(() => { cursor.style.visibility = 'hidden' }, 1400)
  }
  window.addEventListener('pointermove', move, { passive: true })
})

async function card(title, subtitle, takeaway) {
  await page.goto('about:blank')
  // Editorial title and end cards. All investigation screens are captured from the real app.
  await page.setContent(
    '<meta charset="utf-8"><style>' +
    'body{margin:0;display:grid;place-items:center;height:100vh;color:#f9f8ff;background:radial-gradient(ellipse at 78% 16%,#33235e 0%,#171a2d 48%,#111321 78%);font:28px "Segoe UI",sans-serif}' +
    'main{width:78%;border-left:4px solid #a896ff;padding:0 0 0 54px}' +
    '.brand{color:#d0c3ff;font-size:30px;font-weight:650;margin:0 0 28px}' +
    'h1{font-size:68px;letter-spacing:-2.5px;line-height:1.05;margin:0;max-width:1040px}' +
    'p{color:#d5d8ec;font-size:29px;line-height:1.4;max-width:1050px;margin:30px 0}' +
    '.mode{color:#eee8ff;background:#30284b;display:inline-block;padding:12px 20px;border:1px solid #685791;border-radius:8px;font-size:21px;margin:7px 0 0}' +
    '</style><main><div class="brand">AgentFlow</div><h1>' + title +
    '</h1><p>' + subtitle + '</p><div class="mode">' + takeaway + '</div></main>',
  )
}

try {
  await card('Multi-agent operations analysis', 'From a checkout incident to a verified, reviewable report.', 'LangGraph + MCP · Synthetic data · Rule-based run with no LLM')
  chapters.push({ title: 'Opening', at: 0 })
  await hold(6500)

  await page.goto('/')
  await expect(heading('Operations workspace')).toBeVisible()
  const launch = button('Try demo: Checkout Conversion Drop')
  await expect(launch).toBeEnabled()
  await beat('Start an investigation', 'Northstar Shop is fictional. This run uses synthetic records and explicit rules, with no LLM calls.', 10000, true)
  const accepted = page.waitForResponse(response => response.url().endsWith('/api/v1/investigations') && response.request().method() === 'POST')
  await click(launch)
  const response = await accepted
  assert.equal(response.status(), 202)
  const { id, mode } = await response.json()
  assert.equal(mode, 'demo')
  await expect(button('Review draft')).toBeVisible({ timeout: 35000 })
  const trace = await (await page.request.get('/api/v1/investigations/' + id + '/events')).json()
  assert(trace.events.some(event => event.kind === 'evidence_verified'))
  assert(!trace.events.some(event => event.kind === 'model_finished'))
  await writeFile(join(directory, 'investigation_events.json'), JSON.stringify(trace, null, 2))
  await expect(page.getByText('Rule-based demo — no LLM involved', { exact: true })).toBeVisible()
  const chart = page.getByLabel('Checkout conversion comparison')
  await expect(chart).toContainText('82.86%')
  await expect(chart).toContainText('68.86%')
  await page.screenshot({ path: join(directory, 'agentflow_preview.png'), animations: 'disabled' })
  await beat('Checkout Conversion Drop', 'Across the two windows, checkout conversion fell from 82.86% to 68.86%, a drop of 14 percentage points.', 11000)

  await click(button('Execution details'))
  await frame(page.getByRole('heading', { name: 'Investigation workflow' }), 165)
  for (const node of ['Metrics analyst', 'Release investigator', 'Support investigator']) {
    await expect(button(node + ' Completed')).toBeVisible()
  }
  await beat('Workflow and MCP calls', 'LangGraph routes the question to independent metrics, release, and support branches.', 11000, true)
  await click(button('Metrics analyst Completed'))
  const comparisonEvent = page.locator('.activity-list li').filter({ hasText: 'compare_time_windows' })
  await click(comparisonEvent.getByText('Request and provenance', { exact: true }))
  await frame(comparisonEvent, 190)
  await expect(comparisonEvent).toContainText('"evidence_id"')
  await beat('Read-only tool transport', 'The trace shows a real MCP request, its date windows, and the evidence ID returned by the service.', 10500)
  await page.getByLabel('Filter by agent').selectOption('audit')
  const audit = page.getByText(/evidence records passed validation/).first()
  await frame(audit, 300)
  await beat('Evidence audit', 'The audit recomputes the figures and checks scope and provenance before drafting a report.', 6500)

  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await click(button('Findings'))
  const conversion = page.locator('.summary-layout .fact-list li').filter({ has: page.getByText('Checkout conversion', { exact: true }) })
  await click(conversion.getByRole('button', { name: /^Open citation ev-/ }).first())
  await expect(heading('Checkout window comparison')).toBeVisible()
  const traffic = button('traffic-2025-10-21-mobile')
  await click(traffic)
  const source = page.locator('.source-record')
  await expect(source).toContainText('"purchases": 72')
  await frame(source, 460)
  await beat('Trace a finding to its source', 'The checkout citation opens the comparison and the original mobile traffic record for October 21.', 11000, true)
  await click(page.getByRole('button', { name: /^Release timeline/ }))
  const release = button('rel-v4-21')
  await click(release)
  await expect(source).toContainText('rel-v4-21')
  await frame(heading('Release timeline'), 155)
  await beat('Check the release record', 'Release history identifies the deployment. The timing supports a hypothesis and leaves causality uncertain.', 10500)
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await click(button('Findings'))
  await expect(heading('What might explain it?')).toBeVisible()
  await frame(heading('What might explain it?'), 415)
  await beat('State the uncertainty', 'Payment authentication failures are the leading hypothesis. Exposure data or a controlled test would help establish cause.', 9000)

  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await click(button('Final report'))
  await expect(page.getByText('Final report requires approval', { exact: true })).toBeVisible()
  await beat('Human review', 'The draft is saved at a PostgreSQL-backed review checkpoint. Export is locked until approval.', 6500, true)
  await click(button('Open review'))
  await expect(heading('Human review')).toBeVisible()
  await click(page.getByText('Checkpoint ID', { exact: true }))
  await frame(heading('Human review'), 220)
  await beat('Inspect the saved checkpoint', 'The reviewer can approve, reject, or request a revision. The decision is recorded against this checkpoint.', 9500)
  await page.getByLabel('Reviewer note').fill('Checked the conversion denominators and release timing.')
  await click(button('Approve report'))
  await expect(button('Open final report')).toBeVisible()
  await click(button('Open final report'))
  await expect(page.getByText('Approved report', { exact: true })).toBeVisible()
  await frame(page.locator('.report-toolbar'), 170)
  await beat('Approved report', 'The saved decision unlocks a report with source links, caveats, and recommended next actions.', 9500, true)
  const pendingDownload = page.waitForEvent('download')
  await click(page.getByRole('link', { name: 'Download Markdown', exact: true }))
  const download = await pendingDownload
  await download.saveAs(join(directory, 'checkout_report.md'))
  const report = await readFile(join(directory, 'checkout_report.md'), 'utf8')
  assert(report.includes('## Evidence') && report.includes('traffic-2025-10-21-mobile') && report.includes('Round 1 · approve'))
  await beat('Markdown export verified', 'The downloaded report includes the source evidence and the recorded approval.', 5700)

  await click(page.getByRole('link', { name: 'Evaluations', exact: true }))
  await expect(heading('Evaluations')).toBeVisible()
  await click(button('Run benchmark'))
  await beat('Reproducible evaluation', 'Run the same seeded cases with the sequential baseline and the parallel graph.', 5000, true)
  await expect(page.getByRole('link', { name: 'Export results' })).toBeVisible({ timeout: 65000 })
  await expect(page.getByText('30 of 30 cases', { exact: false })).toBeVisible()
  await expect(page.locator('.stat-card').filter({ hasText: '15 / 15 passed' })).toHaveCount(2)
  await frame(page.locator('.evaluation-status'), 140)
  await beat('Compare the measured results', 'Both strategies passed the deterministic checks on these fixtures. This comparison uses no LLM judge.', 10500)
  assert.deepEqual(errors, [])

  beats.at(-1).end = elapsed()
  await card('Evidence before conclusions', 'LangGraph orchestration · read-only MCP tools · evidence auditing · durable human review · reproducible evaluations', 'Run shown: synthetic Northstar Shop data · no LLM involved')
  chapters.push({ title: 'Engineering takeaway', at: elapsed() })
  await hold(6500)
  await writeFile(join(directory, 'timing.json'), JSON.stringify({ beats, chapters, duration: elapsed(), chromium: browser.version() }, null, 2))
  await context.close()
  await video.saveAs(join(directory, 'capture.webm'))
} catch (error) {
  await page.screenshot({ path: join(directory, 'last-frame.png') }).catch(() => {})
  await writeFile(join(directory, 'capture-error.log'), error.stack ?? String(error)).catch(() => {})
  throw error
} finally {
  await browser.close()
}

