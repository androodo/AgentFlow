import { expect, test, type Page } from '@playwright/test'
import { mkdir, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const docs = resolve(process.cwd(), '../docs')
const capture = process.env.AGENTFLOW_CAPTURE_DOCS === '1'

async function screenshot(page: Page, name: string) {
  if (!capture) return
  const target = resolve(docs, 'screenshots')
  await mkdir(target, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: resolve(target, name + '.png'), animations: 'disabled' })
}

test('checkout demo traces evidence, requires approval, and downloads Markdown', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Operations workspace' })).toBeVisible()
  const tryDemo = page.getByRole('button', { name: 'Try demo: Checkout Conversion Drop' })
  await expect(tryDemo).toBeVisible()
  await screenshot(page, 'overview')
  await expect(page.locator('.recent-list, .empty').first()).toBeVisible()
  await tryDemo.click()
  await expect(page.getByRole('button', { name: 'Review draft' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'What changed?', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'What might explain it?' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Release investigator Completed' })).toHaveCount(0)
  await screenshot(page, 'findings')
  await page.getByRole('button', { name: 'Execution details', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Release investigator Completed' })).toBeVisible()
  await expect(page.getByText('compare_time_windows', { exact: true })).toBeVisible()
  await expect(page.getByText('Rule-based demo — no LLM involved', { exact: true })).toBeVisible()
  await screenshot(page, 'workflow')

  await page.getByRole('button', { name: 'Final report' }).click()
  await expect(page.getByText('Final report requires approval')).toBeVisible()
  await page.getByRole('button', { name: 'Open review' }).click()
  await expect(page.getByText('Payment authentication is the leading hypothesis', { exact: true }).first()).toBeVisible()
  const conversion = page.locator('.finding').filter({ has: page.getByRole('heading', { name: 'Checkout conversion', exact: true }) })
  await conversion.getByRole('button', { name: /^Open citation ev-/ }).click()
  await expect(page.getByRole('heading', { name: 'Checkout window comparison' })).toBeVisible()
  await page.getByRole('button', { name: 'traffic-2025-10-21-mobile', exact: true }).click()
  await expect(page.locator('.source-record')).toContainText('"purchases": 72')
  await page.getByRole('button', { name: 'Review draft' }).click()
  await expect(page.getByRole('button', { name: 'Approve report' })).toBeEnabled()
  if (capture) await page.locator('.review-layout').evaluate((layout) => layout.scrollIntoView({ block: 'start' }))
  await screenshot(page, 'review')
  await page.getByLabel('Reviewer note').fill('Verified the funnel denominators and payment evidence.')
  await page.getByRole('button', { name: 'Approve report' }).click()
  await page.getByRole('button', { name: 'Open final report' }).click()
  await expect(page.getByText('Approved report', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Decision history' })).toBeVisible()
  const downloading = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download Markdown' }).click()
  const download = await downloading
  expect(download.suggestedFilename()).toMatch(/^agentflow-checkout-conversion-drop-.*\.md$/)
  const output = info.outputPath('checkout-report.md')
  await download.saveAs(output)
  const report = await readFile(output, 'utf8')
  expect(report).toContain('## Evidence')
  expect(report).toContain('Rule-based demo — no LLM involved')
  expect(report).toContain('**UTC scope:**')
  expect(report).toContain('Round 1 · approve')
  expect(errors).toEqual([])
  if (capture) await page.locator('.report-toolbar').evaluate((toolbar) => toolbar.scrollIntoView({ block: 'start' }))
  await screenshot(page, 'approved-report')
  if (capture) {
    const examples = resolve(docs, 'examples')
    await mkdir(examples, { recursive: true })
    await download.saveAs(resolve(examples, 'checkout-conversion-report.md'))
  }
})

test('evaluation runs the paired suite and shows measured results', async ({ page }) => {
  await page.goto('/evaluations')
  await expect(page.getByRole('heading', { name: 'Evaluations', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Run benchmark' }).click()
  await expect(page.getByRole('link', { name: 'Export results' })).toBeVisible({ timeout: 65_000 })
  await expect(page.getByText('30 of 30 cases', { exact: false })).toBeVisible()
  await expect(page.locator('.benchmark-list [aria-current="page"]')).toContainText('completed')
  await expect(page.locator('.stat-card').filter({ hasText: '15 / 15 passed' })).toHaveCount(2)
  await screenshot(page, 'evaluations')
  await page.locator('.evaluation-case > summary').filter({ hasText: 'Checkout Conversion Drop' }).first().click()
  await expect(page.locator('.evaluation-case[open] .payload-details > summary').filter({ hasText: 'Reference and observed values' })).toHaveText('Reference and observed values')
})

test('mobile layout stays within the viewport and opens a second scenario', async ({ browser, baseURL }) => {
  const page = await browser.newPage({ baseURL, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  try {
    await page.goto('/')
    await expect(page.getByRole('button', { name: 'Try demo: Checkout Conversion Drop' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    await page.getByRole('region', { name: 'Scenario library' }).getByRole('link', { name: /Traffic Mix Shift/ }).click()
    await expect(page.getByRole('combobox', { name: 'Scenario', exact: true })).toHaveValue('traffic-shift')
    await page.getByRole('button', { name: 'Start investigation' }).click()
    await page.getByRole('button', { name: 'Review draft' }).click()
    await expect(page.getByText('Traffic mix best explains the aggregate decline', { exact: true }).first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  } finally {
    await page.close()
  }
})


test('dataset introduction explains the fictional retailer and source records', async ({ page }) => {
  await page.goto('/data')
  await expect(page.getByRole('heading', { name: 'About the data', exact: true })).toBeVisible()
  await expect(page.getByText('Every record is synthetic and reproducible.', { exact: false })).toBeVisible()
  await expect(page.locator('.dataset-tables > section')).toHaveCount(5)
  await expect(page.getByRole('heading', { name: 'Payment outcomes', exact: true })).toBeVisible()
  await screenshot(page, 'dataset')
  await page.getByRole('link', { name: 'Investigate this case' }).click()
  await expect(page.getByRole('combobox', { name: 'Scenario', exact: true })).toHaveValue('checkout-conversion-drop')
})
