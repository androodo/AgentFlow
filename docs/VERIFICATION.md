# Verification

## November 18, 2026 public live-mode update

Docker verification passed 25 backend tests. The new PostgreSQL check confirmed that OpenAI and Claude share the public limit and that a visitor can still start the rule-based demo after the live quota is used. The frontend production build passed, and the rebuilt recruiter container passed the anonymous-session and export checks with live access disabled by default. Funded calls to the recommended models have yet to be tested.

## November 17, 2026 update

The updated application was exercised on Windows and Docker Desktop. The default mode remained credential-free.

- The final Python suite passed 24 tests, including the real MCP transport, model-selected follow-up recipes over that transport, strict OpenAI/Claude adapter contracts, numeric/citation checks, review concurrency, and the additive holdout fixtures.
- Ruff lint and formatting passed. Mypy reported no issues in 24 backend/MCP source files. The frontend passed TypeScript checking and the Vite build.
- All four browser tests passed, covering the new findings-first screen, execution details, evidence lookup, approval and download, the paired 15-case benchmark, mobile layout, and the dataset introduction.
- The deterministic benchmark passed all 15 cases per strategy, including three separately authored held-out cases. The benchmark references remain project-authored.
- A fresh PostgreSQL instance was bootstrapped twice using a database owner with CREATEDB and CREATEROLE privileges and no superuser status. Migrations, both seed manifests, restricted service roles, and checkpointer initialization passed. The checkpoint schema grants avoid requiring role-switch privileges.
- The public container passed separate visitor-session checks, cross-session read/review/report rejection, approval-gated exports, duplicate-review rejection, paid-model restrictions, and per-session rate limits. A separate check stopped the local owner API, restarted the recruiter container at its parked review checkpoint, then resumed and exported once using the same visitor cookie.
- Two bootstrap runs retained identical source data. The updated source snapshot SHA-256 is `f1fb660d86a0349d07039d0044f9cca41cbbe4a289b15d1379c4d006c140a9a8`.
- The default API retained its human interrupt through restart and exported once after approval. A deliberate MCP outage degraded readiness, caused a bounded failed attempt, and recovered on restart.

Commands executed for this update include `./scripts/verify.ps1`, `docker compose --profile verify run --build --rm --no-deps verify`, `npm.cmd --prefix web test`, the Render-image build through `compose.hosted.yml`, and `python scripts/verify-public.py`. The recruiter image also passed three browser flows for checkout, mobile layout, and the dataset introduction. The isolated restart check used `python scripts/verify-public.py --restart-local`.

Live OpenAI and Claude inference awaits provider credentials. Their HTTP schemas, parsing, retries, and failure handling were tested against simulated external provider boundaries. The actual MCP server, graph, evidence auditing, and review gate were used in the model integration test.

The installed `llama3.2:latest` was tested on the richer workflow. It produced unsupported figures for ticket and release data and failed grounding validation after the bounded retry. Earlier attempts also exposed nested-schema compatibility and output/time-budget failures. The adapter now inlines referenced schemas, preserves required title fields, serializes CPU-constrained local inference, and gives correction feedback. The richer checkout assessment has not passed with this installed small model. These failures remain distinct from the passing deterministic demo and provider-contract tests.

The free Render blueprint and external PostgreSQL deployment image are prepared. External deployment is pending the owner's Render and Neon account connections. Hosted GitHub Actions and live LangSmith delivery remain unverified.

Maintenance comments and a debugging guide were added after the functional verification. They explain parallel state updates, model input boundaries, schema title preservation, worker session locks, durable review replay, public capacity checks, and restricted deployment roles. No application behavior was changed by those edits. Ruff lint and formatting were then rerun over the backend, MCP, tests, and deployment source: all checks passed and 31 files were already formatted.

## November 16, 2026 initial implementation

Verified on November 16, 2026 Pacific time using Windows, Docker Desktop's Linux engine 29.6.2, Docker Compose 5.3.1, host Python 3.13.1 and Node 22.13.1. The default stack had blank model settings and no provider key. It returned healthy web, API, PostgreSQL, and MCP services. Ollama, the judge, and LangSmith were unconfigured in the default profile.

## Executed commands and results

| Command | Observed result |
| --- | --- |
| `./scripts/doctor.ps1` | Docker, three published ports, host memory, disk, Python, Node, and optional Ollama checks completed. |
| `./scripts/verify.ps1` | Built and started the stack through `demo.ps1`. Ran the Python suite, bootstrap/restart/outage proof, frontend build and three Chromium tests. |
| `docker compose --profile verify run --build --rm --no-deps verify` | Ruff lint passed. Ruff formatting was clean. Mypy reported no issues in 19 source files, pip reported no broken requirements, and pytest passed 18 tests. |
| `python scripts/proof.py` | Two bootstrap invocations left all source rows identical. The API restarted at a persisted interrupt, approved once, and exported a cited report. During a deliberate MCP stop, API liveness stayed healthy, readiness degraded, and a real tool attempt retried then failed. MCP readiness recovered after restart. |
| `npm.cmd --prefix web run build` | TypeScript checked successfully and Vite built the production bundle. |
| `npm.cmd --prefix web test` | Three Chromium tests passed. These cover checkout evidence through Markdown download, the paired benchmark dashboard, and a second scenario at mobile width. |
| `bash scripts/verify.sh` | Git Bash on Windows ran the Compose, Python, bootstrap/restart/outage, frontend build, and browser steps. It passed 18 Python and three Chromium tests. |
| `docker compose up --build -d --no-deps --wait web` and `npm.cmd --prefix web test` | Rebuilt the final UI and repeated the capture suite after synchronizing the selected benchmark's status with its detail view. |

The verification container executes these package checks.

```sh
python -m ruff check backend mcp-server tests
python -m ruff format --check backend mcp-server tests
python -m mypy backend mcp-server
python -m pip check
python -m pytest -q -p no:cacheprovider
```

The source snapshot SHA-256 after both bootstrap runs was `774ab1836f9e04364127072ea5f23da23121e9678874cf519f2f56d802202296`. The initial seed populated 11 releases, 6 flag changes, 138 daily funnel rows, 516 payment cohorts, and 141 tickets.

Python integration checks include actual MCP discovery and schema enforcement, source-only SQL grants, injected-ticket isolation, independent arithmetic recomputation even after a payload was rehashed, malformed inputs, cancellation, a revised checkpoint, rejection, simultaneous duplicate review, report approval, and a singleton worker lock. The paired demo benchmark returned 12/12 passes per strategy with 89 measured MCP calls per strategy. These are synthetic fixture results.

## Optional model checks

The host's already-installed `llama3.2:latest` was enabled temporarily by setting `OLLAMA_MODEL`, `OLLAMA_JUDGE_MODEL`, and `OLLAMA_TIMEOUT_SECONDS=65` and running `docker compose up --build -d --wait --wait-timeout 120 api`. The API checked `/api/tags` from its Docker network. One live checkout investigation completed validated planner, metrics, timeline, support, and composer calls, then exported after approval. Its persisted ID was `d5b5b4a1-f636-449b-b9c8-4306a964d13b`.

A real calibration job scored 20/20 authored snippets. The exact match counts for groundedness, completeness, and clarity were 8/20, 4/20, and 5/20. Mean absolute errors were 1.40, 1.50, and 1.15 respectively. These compare the model to project-authored annotations on this small set. Independently human-reviewed reference ratings remain pending.

The checkout case also ran through both live benchmark variants using `docker compose exec -T -e OLLAMA_TIMEOUT_SECONDS=65 api python -` and the repository's benchmark runner. Both variants passed the deterministic checks, made nine MCP calls, recorded model token usage, and returned validated report-quality judgments. This was a single paired case.

Before final verification the Compose API returned to the default no-model configuration. No model was downloaded for this test.

## Corrections and coverage limits

- The initial browser suite used ambiguous selectors for scenario and evaluator controls. Scoped selectors resolved those failures. The final run also checks that a completed benchmark has the same status in its detail and recent-runs list.
- A small model initially returned a specialist focus outside that branch's candidates. The response schema now limits choices to the branch's exact labels, and the repeated live checkout test completed.
- The initial verification container used a Ruff cache flag value rejected by the installed release. The corrected flags passed the documented scripts.
- LangSmith's metadata allowlist and opt-in behavior passed a local SDK-boundary test. Delivery to a live LangSmith account and execution on hosted GitHub Actions remain unverified. The complete 12-case live-model benchmark remains available to run locally.
- Review storage and the scheduler were exercised on one local PostgreSQL instance. The tests cover a parked checkpoint restart and a tool outage. Deployments across replicas, deep chaos testing, and production loads are outside the tested scope.

The five [screenshots](screenshots/) and [exported Markdown report](examples/checkout-conversion-report.md) were captured from the live local app with `AGENTFLOW_CAPTURE_DOCS=1` using Playwright.
