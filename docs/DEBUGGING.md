# Debugging AgentFlow

Start with the run's **Findings** and **Execution details** pages. Each run has its own graph thread, evidence, event stream, and review checkpoint.

## Find the responsible code

| Symptom or change | Start here | Boundary to preserve |
| --- | --- | --- |
| Seed counts, missing days, or fixture versions | `backend/agentflow/bootstrap.py`, `source_data.py`, `data/` | Seed data must stay reproducible; missing days mean unknown coverage. |
| Incorrect rate or before/after delta | `backend/agentflow/calculations.py`, `audit.py` | Use counts and denominators, then recompute independently. |
| MCP connectivity or tool contracts | `mcp-server/server.py`, `backend/agentflow/transport.py` | Tools stay typed, bounded, and read-only. |
| Specialist routing or a follow-up | `workflow.py`, `advisor.py`, `followups.py` | The model selects an approved label; code builds the actual request. |
| A rejected model response | `models.py`, `providers.py`, `reasoning.py` | Check the model stage and failure reason in Execution details. Investigative prose must be qualitative and use the supplied IDs in citation fields. |
| A stuck run after restart | `worker.py`, `store.py`, `workflow.py` | Keep the worker's session lock and the existing graph thread. |
| Review conflict or missing export | `store.py` methods `queue_review` and `synchronize` | Persist one decision per interrupt; export only after durable approval. |
| A public visitor sees a 404 or 429 | `access.py`, `store.py`, API middleware | Check the same visitor cookie, ownership, and resource limits. |
| Findings, charts, or review controls | `web/src/summary.tsx`, `run.tsx`, `reports.tsx` | Display persisted API state and keep citations navigable. |
| Hosting startup or TLS/database settings | `deploy/serve.py`, `config.py`, `render.yaml` | Use a direct database endpoint and restricted runtime roles. |

Backend filenames without a directory above are under `backend/agentflow/`.

## Inspect a local run

From PowerShell in the repository root:

```powershell
# Check containers and the actual database/MCP readiness.
docker compose ps
Invoke-RestMethod http://127.0.0.1:8001/readyz

# Inspect configuration status; secrets are not returned.
Invoke-RestMethod http://127.0.0.1:8001/api/v1/connections

# Copy a run ID from the URL or the collapsed run details in the app.
$runId = 'YOUR-RUN-ID'
Invoke-RestMethod "http://127.0.0.1:8001/api/v1/investigations/$runId"
Invoke-RestMethod "http://127.0.0.1:8001/api/v1/investigations/$runId/events"

# Read recent API/worker and independent MCP service logs.
docker compose logs --tail 100 api mcp
```

For the hosted preview, inspect `docker compose -f compose.yml -f compose.hosted.yml --profile hosted logs --tail 100 hosted-app`. Its URL is port 3011. Public requests need the same signed visitor cookie as the browser that created the run; a fresh PowerShell request has a different visitor identity.

## Recognize expected states

- `awaiting_review` is a persisted human interrupt. Use **Review draft** to approve, reject, or request the one allowed revision.
- `review_queued` means the decision is already stored and is waiting for the worker. Resubmitting that interrupt should conflict.
- A 409 on a second review protects the existing decision. Refresh the current run instead of deleting ledger rows.
- An unavailable MCP service makes `/readyz` fail while `/healthz` can remain healthy. Restore MCP, inspect the failed run, and start a new investigation.
- `configured` for a provider means its settings exist. The owner's **Test access** checks model access without generating an assessment. An actual run separately validates inference output.
- The tested small local `llama3.2:latest` produced unsupported figures in the richer workflow. Its bounded failure is recorded in [verification](VERIFICATION.md). Use the deterministic demo while configuring a suitable hosted model.

A successful numeric-literal check does not establish that the model interpreted a number correctly. Read the cited evidence and preserve human review.

## Run the relevant check

```powershell
# Complete local verification: Python, MCP, restart/review proof, build, and browser flows.
./scripts/verify.ps1

# Backend checks using the running local stack.
docker compose --profile verify run --build --rm --no-deps verify

# Frontend build and browser flows.
npm.cmd --prefix web run build
npm.cmd --prefix web test

# Visitor isolation and restart/resume for the local hosting preview.
python scripts/verify-public.py --restart-local
```

The restart proof temporarily restarts the hosted application service. For an isolated worker recovery proof, stop the owner API first and restore it afterward, as recorded in [verification](VERIFICATION.md).

## Use the commit history

The initial history is divided into data/contracts, MCP/evidence, models/graph, API/persistence, interface, runtime/deployment, and documentation. Each commit message describes its responsibility and the invariants it introduces. It is a subsystem map; run the complete stack from the final commit in the series.

```powershell
git log --oneline --decorate
git show COMMIT_HASH --stat
git log --oneline -- backend/agentflow/workflow.py
git blame backend/agentflow/workflow.py
```

Use a new branch for fixes and add focused regression coverage for behavior changes. Keep local keys in ignored environment files and record checks actually executed in `docs/VERIFICATION.md`.
