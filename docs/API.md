# AgentFlow API

The web app proxies `/api/v1` to FastAPI on the local Compose network. [OpenAPI](http://127.0.0.1:8001/docs) lists request and response models. All writes accept `application/json` up to 16 KiB. An application error has the form `{"error":{"code":"review_conflict","message":"This checkpoint is no longer accepting a review."}}`. Validation errors include field paths. UUIDs distinguish investigations, evaluations, and calibration jobs.

| Method and path | Contract |
| --- | --- |
| `GET /healthz` | API process liveness |
| `GET /readyz` | Database schema and MCP initialization/registry check, HTTP 503 with a degraded dependency |
| `GET /api/v1/connections` | Core services and optional configuration states |
| `GET /api/v1/workspace` | Dataset introduction and public/owner capabilities |\n| `POST /api/v1/connections/test` | Read model access using a server-configured provider. Accepts `{"provider":"openai"}`, `anthropic`, or `ollama`. |\n| `GET /api/v1/scenarios` | Versioned scenario titles, safe defaults, segment, UTC windows, and task hashes |
| `GET /api/v1/investigations?limit=15` | Newest runs, capped at 50 |
| `POST /api/v1/investigations` | Queue `{"scenario_id":"checkout-conversion-drop","mode":"demo"}`. An optional bounded `question` overrides the scenario question. Owner workspaces can select `ollama`, `openai`, or `anthropic`; public mode accepts seeded demo questions. |
| `GET /api/v1/investigations/{id}` | Status, checkpoint ID, pending interrupt, draft and review history |
| `GET /api/v1/investigations/{id}/events?after=0` | At most 200 ascending events and `next_cursor`. Poll using the last returned cursor. |
| `GET /api/v1/investigations/{id}/evidence` | Audited MCP payloads with request and source IDs |
| `GET /api/v1/investigations/{id}/evidence/{evidence_id}/sources/{source_id}` | One cited source record retrieved over MCP after membership validation |
| `POST /api/v1/investigations/{id}/review` | Queue a persisted decision for `{"interrupt_id":"…","action":"approve","note":""}`. Actions include `reject` and `revise`. Revision requires a note and opens a second checkpoint. |
| `POST /api/v1/investigations/{id}/cancel` | Send `{}` to cancel a queued, running, or awaiting-review run. |
| `GET /api/v1/investigations/{id}/report` | Approved structured report. Use `?format=markdown` for an attachment. |
| `GET /api/v1/evaluations` | Recent experiment jobs |
| `POST /api/v1/evaluations` | Queue a `single`, `multi`, or `compare` experiment. Optional `mode` and `judge` require the corresponding local model. |
| `GET /api/v1/evaluations/{id}` | Per-case progress, failures, measured summaries and optional judge results. Use `?format=json` for an attachment. |
| `GET /api/v1/calibrations` | Recent judge calibration jobs |
| `POST /api/v1/calibrations` | Send `{}` with a configured judge to enqueue calibration. |
| `GET /api/v1/calibrations/{id}` | Calibration progress, successful scores, errors and disagreement details |

Writes that start asynchronous work return HTTP 202. Poll the run or job until a checkpoint or terminal state. `failed` and `needs_clarification` include an explanation. A stale review, duplicate review, extra revision, unavailable model, or export without approval returns HTTP 409.

See [MCP server](../mcp-server/README.md) for the independent transport and source tool contract.
