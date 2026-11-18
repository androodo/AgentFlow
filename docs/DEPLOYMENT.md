# Local deployment

For the hosted deployment, use the [Render hosting guide](HOSTING.md). For OpenAI and Claude credentials, use [model setup](MODELS.md).

Start Docker Desktop using Linux containers and WSL 2 on Windows. Both the demonstration and its data load run without external credentials. The initial build needs registry access for Python, Node, Nginx, and PostgreSQL images and packages. Port overrides in `.env` are `WEB_PORT`, `API_PORT`, and `MCP_PORT`. PostgreSQL remains on the project network. Keep `.env` private and change local database passwords before reusing the stack for anything shared.

Run `docker compose down` to stop containers with the database volume retained. Back up PostgreSQL using ordinary PostgreSQL tools if you need to preserve local reviews and reports. Seed data loads transactionally at startup. New source fixtures require a new dataset version and migration plan.

## Opt in to local Ollama

1. Install Ollama and explicitly pull a small supported model. The example below uses a compact model. You can use an already installed local model.
2. From the repository root, update `.env` with `OLLAMA_MODEL=qwen3:1.7b`. If you also want judging, set `OLLAMA_JUDGE_MODEL` to the tag of an installed local model.
3. Rerun `./scripts/demo.ps1` and open **Connections**. The app checks `/api/tags` to confirm the model is installed. Choose **Live local Ollama** in New Investigation.

```powershell
ollama pull qwen3:1.7b
ollama list
docker compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=3).status)"
```

On Docker Desktop, the default backend origin is `http://host.docker.internal:11434`. If the container cannot reach Ollama, confirm the host service is running and check Windows firewall and Docker Desktop networking. Ollama's binding is controlled by the host `OLLAMA_HOST` setting and needs a service restart to take effect. Prefer the narrowest interface and firewall rules that permit local container access. A host-native AgentFlow backend can instead use `http://127.0.0.1:11434`. The default first run uses no inference. [Ollama Windows guidance](https://docs.ollama.com/windows), [Ollama FAQ](https://docs.ollama.com/faq)

The graph makes at most nine logical model calls per investigation, including a requested revision, with up to two attempts per step. Each request has explicit context and output limits and a timeout. Replayed steps around a worker crash can use additional attempts. Machine and model performance affect time to checkpoint. Live failures are visible in the run timeline. [Structured output API](https://docs.ollama.com/capabilities/structured-outputs)

## Opt in to LangSmith

Set `AGENTFLOW_LANGSMITH=true` and `LANGSMITH_API_KEY` only when you intend to send metadata to LangSmith. Optionally set `LANGSMITH_PROJECT`. The external export contains local run and checkpoint IDs, scenario IDs, mode, model, and outcome metadata. Questions, ticket text, evidence payloads, and reviewer notes stay in local storage. Local traces are always in PostgreSQL. [LangSmith tracing configuration](https://docs.langchain.com/langsmith/trace-without-env-vars)

## Hosted approach

A hosted deployment would require HTTPS, authenticated users and reviewers, per-source and per-run authorization, secret management, backup/restore, and scoped network policies. Replace the loopback origin rule with an explicit deployment allowlist before serving through HTTPS. Allow browser API origins narrowly if you separate the UI host. Remote MCP exposure and model access require independent authentication and limits. Keep one scheduler until you design and verify distributed claim and fan-out behavior.
