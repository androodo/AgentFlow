# Model configuration

The owner workspace offers the credential-free demo, local Ollama, OpenAI, and Anthropic Claude. Set the selected provider's model and credential on the server. The React app receives availability and provider/model labels.

| Provider | Environment variables | Connection check |
| --- | --- | --- |
| Ollama | `OLLAMA_MODEL`, optionally `OLLAMA_URL` | Installed model list from the configured local host |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL` | Read model access through the official OpenAI API |
| Claude | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Read model access through the official Anthropic API |

For local Docker, edit `.env` and run `docker compose up -d --force-recreate api`. Open **Connections**, test model access, then select the provider in **New investigation**. Use an exact model ID available to your account. The model needs structured output support for this request format.

OpenAI requests use Chat Completions with a strict JSON-schema response format. Claude requests use a forced `submit_assessment` schema tool. Both parse the result into Pydantic models. Provider URLs are fixed in the backend. Local Ollama uses its direct chat endpoint with a JSON schema. [OpenAI structured outputs](https://platform.openai.com/docs/guides/structured-outputs), [Claude tool use](https://docs.claude.com/en/docs/agents-and-tools/tool-use/implement-tool-use), [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)

## What a live run does

The model selects relevant domains from the question and the chosen incident scope. Each selected specialist receives a projection of verified operational facts, analyzes the signal and a competing explanation, and can choose one named follow-up recipe. Python maps that label to an allowlisted tool call with fixed dates and segment bounds. A specialist then assesses its expanded evidence.

The report composer ranks competing explanations, identifies evidence supporting and contradicting each, writes uncertainty, and proposes next actions. It receives the actual tool results and code-generated observations. Gold/reference benchmark answers stay outside model prompts.

The auditor recomputes funnel counts and percentage-point differences from source rows. It checks hashes, source references, windows, and allowed follow-up recipes. Generated hypotheses must cite supplied IDs and use qualitative prose. Exact figures come from the audited observations. If a specialist still returns unusable prose after a retry, the workflow omits that response and keeps its verified tool results for the composer. The activity log records the skipped response and the failure category. Semantic groundedness still requires review.

A run can make up to nine logical model calls, including a revision, with two bounded attempts per call. Each call has an output budget, a response-size cap, and a timeout. Provider-reported token counts are recorded when supplied. OpenAI or Claude usage requires API access and is billed by that provider.

## Enable live runs on Render

On the AgentFlow web service, open **Environment**. Keep `AGENTFLOW_PUBLIC_DEMO=true` to preserve visitor isolation and seeded questions. To offer OpenAI, set `OPENAI_API_KEY` and `OPENAI_MODEL=gpt-6-luna`. To offer Claude, set `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL=claude-haiku-5-5`. Save keys in Render's server environment. Configure one provider or both.

Set `AGENTFLOW_PUBLIC_LIVE_DAILY_LIMIT=5` to allow up to five live starts across both providers in a rolling 24-hour window. Each browser session can start up to two. The default is zero, and values above 20 are capped at 20. Actual charges depend on provider, tokens, retries, and review revisions.

OpenAI is the public default when configured. To offer only hosted models, set `AGENTFLOW_PUBLIC_LIVE_ONLY=true` alongside a positive live limit and at least one configured provider. This removes the rule-based option from the public form and blocks direct demo starts through the public API. When no provider is configured, visitors cannot start an investigation in live-only mode. Remove the live-only setting and redeploy to restore the free option.

Deploy the latest commit and open **New investigation → Execution mode** on the public site. Select the configured provider and complete one seeded case to validate model access and report generation. Check measured usage in the provider dashboard. [Render environment variables](https://render.com/docs/configure-environment-variables)

## Enable model judging and calibration

In the owner workspace, set `AGENTFLOW_JUDGE_PROVIDER=openai` or `AGENTFLOW_JUDGE_PROVIDER=anthropic` to use that provider's configured model for report-quality scoring and judge calibration. For local judging, keep `AGENTFLOW_JUDGE_PROVIDER=ollama` and set `OLLAMA_JUDGE_MODEL`. The job stores both the selected provider and the model so a restart resumes with the same pair.

In **Evaluations**, select a live provider to benchmark it and optionally enable **Score report quality with the configured judge**. Use **Run calibration** to compare judge scores with the project-authored references. These actions may make multiple billable requests and remain owner-only. Public visitors can inspect saved benchmark results.

See [verification](VERIFICATION.md) for the distinction between simulated provider contracts and funded model runs.
