# Render deployment

AgentFlow is deployed on Render with external PostgreSQL. The web container serves React and FastAPI, runs the worker, and starts a separate MCP process on loopback. PostgreSQL retains review checkpoints across restarts and idle shutdowns. [Open the hosted workspace](https://agentflow-ho1a.onrender.com)

## Configure the database

For a new instance, create a dedicated Neon project and database. Copy its **direct** PostgreSQL connection string with the supplied TLS settings. The worker uses a PostgreSQL session lock and needs a direct endpoint. At startup, the database owner applies migrations, seeds the source data, and creates restricted roles for the API and MCP processes. [Neon connection guide](https://neon.com/docs/connect/connect-from-any-app)

## Deploy the blueprint

1. Sign in to Render with GitHub and choose **New → Blueprint**.
2. Select the AgentFlow repository. Render reads the root `render.yaml`.
3. Confirm the web service uses the **Free** plan and the build file `deploy/Dockerfile`.
4. Set `ADMIN_DATABASE_URL` to the Neon direct connection string in Render's secret settings.
5. Apply the blueprint. Render generates the application, reader, and visitor-signing secrets. Startup runs migrations and both seed manifests, initializes checkpoints, then starts the service.
6. Wait for the service to become healthy. Open the resulting service URL and start a checkout investigation.

The public origin is derived from `RENDER_EXTERNAL_URL`. For a custom domain, set `AGENTFLOW_PUBLIC_ORIGIN` to the exact HTTPS origin and redeploy. Use a single web-service instance. [Render blueprints](https://render.com/docs/blueprint-spec)

## Verify the deployment

```powershell
python scripts/verify-public.py --url https://YOUR-SERVICE.onrender.com
```

The smoke script exercises a deployment that allows rule-based runs. On a live-only deployment, start a case through **New investigation**, review the draft, and download Markdown. A second browser session has its own investigations.

The free service can spin down after 15 minutes without incoming traffic and takes time to wake on the next visit. The database can also suspend while idle. Account usage limits still apply. Render's free PostgreSQL databases expire after 30 days, which is why this blueprint expects an external database. [Render free-service limits](https://render.com/docs/free)

## Public access and model use

Public visitors can investigate seeded cases, inspect their sources, review their own drafts, and download approved reports. A signed cookie identifies the browser session. Public investigations expire after one day.

Configured OpenAI and Claude runs share a daily limit. The deployment can also allow rule-based runs. Benchmark and calibration execution is available in the owner workspace. See [model setup](MODELS.md).

## Test the hosting image locally

```powershell
docker compose -f compose.yml -f compose.hosted.yml --profile hosted up --build -d --wait hosted-app
python scripts/verify-public.py --restart-local
```

The local hosted preview opens at [127.0.0.1:3011](http://127.0.0.1:3011). Override `HOSTED_PORT` if necessary. This preview uses the same Dockerfile and startup path as Render. Stop it with `docker compose -f compose.yml -f compose.hosted.yml --profile hosted stop hosted-app`.
