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

The auditor recomputes funnel counts and percentage-point differences from source rows. It checks hashes, source references, windows, and allowed follow-up recipes. Generated hypotheses must cite supplied IDs. Numeric literals in factual prose are checked against those cited facts. Numerical observations are composed from audited facts. These checks cover arithmetic, numeric literals, scope, and citation integrity. Semantic groundedness still requires review.

A run can make up to nine logical model calls, including a revision, with two bounded attempts per call. Each call has an output budget, a response-size cap, and a timeout. Provider-reported token counts are recorded when supplied. OpenAI or Claude usage requires a funded provider account and is billed by that provider. Public recruiter mode executes the free deterministic demo.

## Current verification boundary

The hosted adapters have request/response contract tests against simulated provider boundaries, including strict parsing, authentication failures, retries, and measured usage fields. A graph integration test uses simulated hosted responses with the actual MCP service to verify follow-up collection, citation validation, competing explanations, and approval. Live hosted calls await the owner's provider credentials.

The reference judge currently uses the configured local Ollama judge model. Its authored reference labels are available for independent human review.
