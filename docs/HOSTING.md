# Recruiter hosting on Render

The repository includes a free Render web-service blueprint and a single-container build. That container serves React and FastAPI, runs the worker, and starts a separate MCP process on loopback. PostgreSQL lives outside the container so review checkpoints survive restarts and idle shutdowns.

The deployment files have been exercised locally with a PostgreSQL container. A public Render URL still requires a Render account and a database connection configured by the owner.

## Create the free database

Create a free Neon project and database dedicated to AgentFlow. Copy its **direct** PostgreSQL connection string from the connection dialog. Disable the pooling toggle. Include the TLS settings supplied by Neon.

Use a role that can create application roles, source tables, and the checkpoint schema during bootstrap. The startup task creates separate application and source-reader roles. Once bootstrap completes, the running API and MCP processes use those restricted roles. The server holds the administrative URL only for startup. Session advisory locks require the direct endpoint. [Neon connections](https://neon.com/docs/connect/connect-from-any-app)

Neon's free tier is subject to its current storage and compute quotas. The public demo expires visitor investigations after one day and bounds new jobs. [Neon plans](https://neon.com/docs/introduction/plans)

## Connect the repository

The project already has a local commit history. On GitHub, create an empty repository named `agentflow` under `androodo`. Leave the README, license, and .gitignore initialization options unchecked so the remote starts empty. A private repository can back a public Render service.

Then run these commands in PowerShell:

```powershell
Set-Location 'C:\My CS Projects\AgentFlow'

# Connect the empty repository you created.
git remote add origin https://github.com/androodo/agentflow.git

# Publish the existing local commit history.
git push -u origin main
```

Run `git remote -v` first if you already added a remote. If `origin` exists and is correct, skip `git remote add`. The authenticated GitHub account must be able to push to that repository.

The ignore rules exclude local credentials, virtual environments, build outputs, and browser traces. A private source repository can back a public Render web service.

## Deploy the blueprint

1. Sign in to Render with GitHub and choose **New → Blueprint**.
2. Select the AgentFlow repository. Render reads the root `render.yaml`.
3. Confirm the web service uses the **Free** plan and the build file `deploy/Dockerfile`.
4. Set `ADMIN_DATABASE_URL` to the Neon direct connection string in Render's secret settings.
5. Apply the blueprint. Render generates the application, reader, and visitor-signing secrets. Startup runs migrations and both seed manifests, initializes checkpoints, then starts the service.
6. Wait for the service to become healthy. Open the resulting `https://...onrender.com` URL and click the checkout demo.

The public origin is derived from `RENDER_EXTERNAL_URL`. For a custom domain, set `AGENTFLOW_PUBLIC_ORIGIN` to the exact HTTPS origin and redeploy. Use a single web-service instance. [Render blueprints](https://render.com/docs/blueprint-spec)

## Verify the link

```powershell
python scripts/verify-public.py --url https://YOUR-SERVICE.onrender.com
```

Then open the link in a private browser window, investigate a case, review it, and download Markdown. Another browser session should see its own investigations.

The free service can spin down after 15 minutes without incoming traffic and takes time to wake on the next visit. The database can also suspend while idle. Account usage limits still apply. Render's free PostgreSQL databases expire after 30 days, which is why this blueprint expects an external database. [Render free-service limits](https://render.com/docs/free)

## Public access and model use

Public visitors can start seeded demo investigations, inspect their sources, approve or revise their own draft, and download their report. A signed cookie identifies their browser session. Work expires after one day. This provides isolation for a portfolio demonstration. Reviewer identity is represented by that browser session.

Public mode defaults to the rule-based demo and keeps owner actions behind that deployment boundary. OpenAI and Claude are optional for seeded public runs with server credentials and a daily live-run limit. Local Ollama is available in the owner workspace. See [model setup](MODELS.md).

## Test the hosting image locally

```powershell
docker compose -f compose.yml -f compose.hosted.yml --profile hosted up --build -d --wait recruiter
python scripts/verify-public.py --restart-local
```

The local recruiter preview opens at [127.0.0.1:3011](http://127.0.0.1:3011). Override `RECRUITER_PORT` if necessary. This preview uses the same Dockerfile and startup path as Render. Stop it with `docker compose -f compose.yml -f compose.hosted.yml --profile hosted stop recruiter`.
