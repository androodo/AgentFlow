# Investigation walkthrough

| Time | Action |
| --- | --- |
| 0:00 | Open [127.0.0.1:3001](http://127.0.0.1:3001). Click **Try demo: Checkout Conversion Drop**. |
| 0:20 | Read **What changed?** The checkout completion rate moved from 82.86% to 68.86%. Open a citation beneath the checkout observation. |
| 0:40 | Open `traffic-2025-10-21-mobile` to see the daily source record. Then return to **Findings** for the explanation and caveats. |
| 1:00 | Open **Review draft**, enter an optional note, and approve. Open the final report and download Markdown. |
| 1:20 | Open **Execution details** to inspect the parallel specialists, MCP tool calls, and audit events. |
| 1:40 | Open **Evaluations** and inspect a paired case, including the held-out results. |

The mode banner identifies rule-based and live runs. Model modes require an owner-configured provider and model ID. A live model run can select follow-up checks and rank competing explanations. The report preserves arithmetic from deterministic tools.

## Capture screenshots

```powershell
./scripts/demo.ps1
npm.cmd --prefix web ci
npm.cmd --prefix web exec -- playwright install chromium
$env:AGENTFLOW_CAPTURE_DOCS = '1'
npm.cmd --prefix web test
Remove-Item Env:AGENTFLOW_CAPTURE_DOCS
```

The suite captures the [overview](screenshots/overview.png), [findings](screenshots/findings.png), [workflow](screenshots/workflow.png), [review](screenshots/review.png), [approved report](screenshots/approved-report.png), [evaluations](screenshots/evaluations.png), [dataset introduction](screenshots/dataset.png), and an actual [Markdown export](examples/checkout-conversion-report.md).

## Use the hosted workspace

Start the checkout investigation with OpenAI or select a configured provider from **New investigation**. Browse the evidence and review your draft before downloading the report. [Open AgentFlow](https://agentflow-ho1a.onrender.com)

## Troubleshooting

Use `./scripts/doctor.ps1` for Docker and port checks. Inspect `docker compose ps --all` and `docker compose logs bootstrap mcp api` for startup failures. Inspect **Connections** for optional provider configuration. Missing credentials, unsupported model outputs, unavailable upstream services, and stale review actions return visible errors.
