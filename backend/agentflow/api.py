import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from os import environ
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from agentflow.access import COOKIE, authorize_path, identity, public_write_allowed, reserve_run
from agentflow.api_models import (
    ComponentStatus,
    Connections,
    EvaluationRequest,
    EventPage,
    JobCreated,
    ReviewRequest,
    RunSummary,
    RunView,
    StartRequest,
)
from agentflow.benchmark import Benchmarks
from agentflow.bootstrap import generate_rows
from agentflow.config import DATASET_VERSION, DEMO_LABEL, ROOT, Settings, make_engine
from agentflow.domain import Evidence, Model, RecordRequest, Report, Scenario, load_cases
from agentflow.judge import Calibrations
from agentflow.models import LangSmithExport, OllamaClient
from agentflow.providers import client_for
from agentflow.reporting import markdown
from agentflow.store import Problem, Row, Store
from agentflow.transport import MCPClient, ToolUnavailable
from agentflow.worker import Worker

settings = Settings.from_env()
store = Store(make_engine())
client = MCPClient(settings.mcp_url)
cases = load_cases()
ollama = OllamaClient(settings)
traces = LangSmithExport(settings)
calibrations = Calibrations(store, ollama)
benchmark = Benchmarks(store, client, cases, ollama, traces)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    worker = Worker(store, client, benchmark, calibrations, ollama, traces)
    if settings.embedded_worker:
        worker.thread.start()
    try:
        yield
    finally:
        worker.stop.set()
        if worker.thread.is_alive():
            worker.thread.join(timeout=2)
        store.engine.dispose()


app = FastAPI(
    title="AgentFlow",
    version="1.0.0",
    lifespan=lifespan,
    description="Local evidence-based operations analysis of the fictional Northstar Shop.",
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "127.0.0.1",
        "localhost",
        "api",
        "web",
        "testserver",
        *([str(urlsplit(settings.public_origin).hostname)] if settings.public_origin else []),
    ],
)


def problem_response(code: str, message: str, status: int, **detail: object) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **detail}}, status_code=status)


@app.middleware("http")
async def enforce_mutation_boundary(request: Request, call_next) -> Response:
    request.state.visitor = None
    cookie = None
    if settings.public_demo:
        request.state.visitor, cookie = identity(request, settings)
        try:
            public_write_allowed(request, settings)
            await run_in_threadpool(authorize_path, request, store)
        except Problem as exc:
            return problem_response(exc.code, exc.message, exc.status)
    if request.method == "POST":
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site" or (
            origin and origin != (settings.public_origin or str(request.base_url).rstrip("/"))
        ):
            return problem_response("invalid_origin", "Use the AgentFlow local origin.", 403)
        size = request.headers.get("content-length", "")
        if not size.isdecimal() or len(size) > 6 or int(size) > 16384:
            return problem_response("request_size", "Send a JSON body of up to 16 KiB.", 413)
        if request.headers.get("content-type", "").partition(";")[0] != "application/json":
            return problem_response("content_type", "Send application/json.", 415)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if cookie:
        response.set_cookie(
            COOKIE,
            cookie,
            httponly=True,
            secure=settings.public_origin.startswith("https://"),
            samesite="lax",
            max_age=86400,
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    return response


@app.exception_handler(Problem)
async def handle_problem(_: Request, exc: Problem) -> JSONResponse:
    return problem_response(exc.code, exc.message, exc.status)


@app.exception_handler(RequestValidationError)
async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    detail = [
        {"path": [str(item) for item in error["loc"]], "message": error["msg"]}
        for error in exc.errors()
    ]
    return problem_response(
        "invalid_request", "Check the highlighted request fields.", 422, fields=detail
    )


@app.exception_handler(HTTPException)
async def handle_http(_: Request, exc: HTTPException) -> JSONResponse:
    return problem_response("http_error", str(exc.detail), exc.status_code)


@app.exception_handler(SQLAlchemyError)
async def handle_database(_: Request, _exc: SQLAlchemyError) -> JSONResponse:
    return problem_response("database_unavailable", "PostgreSQL is temporarily unavailable.", 503)


def base_connections() -> tuple[ComponentStatus, ComponentStatus]:
    try:
        store.one("SELECT id FROM investigations LIMIT 1")
        database = ComponentStatus(state="ok", detail="PostgreSQL application schema reachable.")
    except SQLAlchemyError:
        database = ComponentStatus(
            state="unavailable", detail="Unable to query the PostgreSQL application schema."
        )
    mcp = (
        ComponentStatus(
            state="ok", detail="Streamable HTTP initialized and the tool registry matched."
        )
        if client.ready()
        else ComponentStatus(state="unavailable", detail="MCP handshake or tool discovery failed.")
    )
    return database, mcp


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"api": "ok"}


@app.get("/readyz", response_model=None)
def ready() -> JSONResponse:
    database, mcp = base_connections()
    status = 200 if database.state == mcp.state == "ok" else 503
    return JSONResponse(
        {
            "api": "ok",
            "database": database.state,
            "mcp": mcp.state,
            "dataset_version": DATASET_VERSION,
        },
        status_code=status,
    )


@app.get("/api/v1/connections")
def connections() -> Connections:
    database, mcp = base_connections()
    return Connections(
        api=ComponentStatus(state="ok", detail="FastAPI v1 is responding."),
        database=database,
        mcp=mcp,
        ollama=ollama.status(settings.ollama_model),
        judge=ollama.status(settings.judge_model, judge=True),
        langsmith=traces.status(),
        openai=client_for(settings, "openai").status(settings.openai_model),
        anthropic=client_for(settings, "anthropic").status(settings.anthropic_model),
    )


@app.get("/api/v1/scenarios")
def scenarios() -> list[Scenario]:
    return [case.scenario for case in cases.values()]


def require_model(*, judge: bool = False, provider: str = "ollama") -> str:
    model = settings.judge_model if judge else settings.model_for(provider)
    adapter = client_for(settings, provider)
    status = (
        adapter.status(model, probe=True)
        if provider != "ollama"
        else adapter.status(model, judge=judge)
    )
    if status.state != "ok":
        raise Problem("model_unavailable", status.detail, 409)
    return model


def mode_label(row: Row) -> str:
    return {
        "demo": DEMO_LABEL,
        "ollama": "Live local Ollama",
        "openai": "Live OpenAI",
        "anthropic": "Live Claude",
    }[row["mode"]]


SUMMARY_FIELDS = (
    "id",
    "scenario",
    "question",
    "mode",
    "model",
    "status",
    "created_at",
    "updated_at",
)


def summary_fields(row: Row) -> Row:
    return {**{key: row[key] for key in SUMMARY_FIELDS}, "mode_label": mode_label(row)}


def run_view(row: Row) -> RunView:
    return RunView.model_validate(
        {
            **summary_fields(row),
            **{key: row[key] for key in ("checkpoint_id", "pending", "draft", "error")},
            "reviews": row.get("reviews", []),
        }
    )


@app.get("/api/v1/investigations")
def list_runs(request: Request, limit: Annotated[int, Query(ge=1, le=50)] = 15) -> list[RunSummary]:
    rows = store.all(
        "SELECT * FROM investigations WHERE (CAST(:visitor AS text) IS NULL OR visitor_id=:visitor) ORDER BY created_at DESC LIMIT :limit",
        {"limit": limit, "visitor": request.state.visitor},
    )
    return [RunSummary.model_validate(summary_fields(row)) for row in rows]


@app.post("/api/v1/investigations", status_code=202)
def start_run(payload: StartRequest, request: Request) -> RunView:
    case = cases.get(payload.scenario_id)
    if not case:
        raise Problem("scenario_not_found", "Choose a scenario from the Northstar library.", 404)
    if settings.public_demo:
        if (
            payload.question
            or payload.mode == "ollama"
            or (payload.mode != "demo" and not settings.public_live_daily_limit)
        ):
            raise Problem("public_demo_scope", "Choose a seeded scenario and an enabled mode.", 403)
        reserve_run(
            store,
            settings,
            request.state.visitor,
            request.client.host if request.client else "unknown",
        )
    model = require_model(provider=payload.mode) if payload.mode != "demo" else None
    scenario = case.scenario
    return run_view(
        store.create_run(
            scenario,
            payload.question or scenario.question,
            payload.mode,
            model,
            request.state.visitor,
            public_live_daily_limit=settings.public_live_daily_limit,
        )
    )


@app.get("/api/v1/investigations/{run_id}")
def get_run(run_id: UUID) -> RunView:
    return run_view(store.get_run(run_id))


@app.get("/api/v1/investigations/{run_id}/events")
def events(
    run_id: UUID, after: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0
) -> EventPage:
    rows = store.events(run_id, after)
    return EventPage.model_validate(
        {"events": rows, "next_cursor": rows[-1]["id"] if rows else after}
    )


@app.post("/api/v1/investigations/{run_id}/review", status_code=202)
def review(run_id: UUID, payload: ReviewRequest) -> RunView:
    store.queue_review(run_id, payload.interrupt_id, payload.action, payload.note)
    return run_view(store.get_run(run_id))


@app.post("/api/v1/investigations/{run_id}/cancel")
def cancel(run_id: UUID, _payload: Model) -> RunView:
    store.cancel(run_id)
    return run_view(store.get_run(run_id))


@app.get("/api/v1/investigations/{run_id}/evidence")
def run_evidence(run_id: UUID) -> list[Evidence]:
    store.get_run(run_id)
    rows = store.all("SELECT record FROM evidence WHERE run_id=:id ORDER BY id", {"id": run_id})
    return [Evidence.model_validate(row["record"]) for row in rows]


@app.get("/api/v1/investigations/{run_id}/evidence/{evidence_id}/sources/{source_id}")
def source(run_id: UUID, evidence_id: str, source_id: str) -> Row:
    values = {"id": run_id, "ev": evidence_id}
    row = store.one("SELECT record FROM evidence WHERE run_id=:id AND id=:ev", values)
    if not row or source_id not in {
        ref.id for ref in Evidence.model_validate(row["record"]).sources
    }:
        raise Problem(
            "source_not_found", "This source is outside the selected evidence record.", 404
        )
    try:
        return client.source(RecordRequest(evidence_id=source_id).evidence_id)
    except ToolUnavailable as exc:
        raise Problem("source_unavailable", str(exc), 503) from exc


@app.get("/api/v1/investigations/{run_id}/report", response_model=Report)
def get_report(run_id: UUID, format: Literal["json", "markdown"] = "json") -> Report | Response:
    run = store.get_run(run_id)
    row = store.one("SELECT report FROM reports WHERE run_id=:id", {"id": run_id})
    if run["status"] != "approved" or row is None:
        raise Problem("report_pending_approval", "A finalized report requires human approval.", 409)
    report = Report.model_validate(row["report"])
    if format == "markdown":
        return PlainTextResponse(
            markdown(str(run_id), report, run_evidence(run_id), run["reviews"]),
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="agentflow-{report.scenario_id}-{run_id}.md"'
            },
        )
    return report


@app.get("/api/v1/evaluations")
def list_evaluations() -> list[Row]:
    return store.all("SELECT * FROM evaluations ORDER BY created_at DESC LIMIT 12")


@app.post("/api/v1/evaluations", status_code=202)
def evaluate(payload: EvaluationRequest) -> JobCreated:
    model = require_model(provider=payload.mode) if payload.mode != "demo" else None
    judge_model = require_model(judge=True) if payload.judge else None
    return JobCreated(id=benchmark.create(payload.strategy, payload.mode, model, judge_model))


@app.get("/api/v1/evaluations/{job_id}")
def evaluation(job_id: UUID, format: Literal["view", "json"] = "view") -> JSONResponse:
    data = jsonable_encoder(benchmark.get(job_id))
    headers = (
        {"Content-Disposition": f'attachment; filename="agentflow-evaluation-{job_id}.json"'}
        if format == "json"
        else None
    )
    return JSONResponse(data, headers=headers)


@app.get("/api/v1/calibrations")
def list_calibrations() -> list[Row]:
    return store.all(
        "SELECT id,model,status,created_at,completed_at,error FROM calibrations ORDER BY created_at DESC LIMIT 12"
    )


@app.post("/api/v1/calibrations", status_code=202)
def start_calibration(_payload: Model) -> JobCreated:
    return JobCreated(id=calibrations.create(require_model(judge=True)))


@app.get("/api/v1/calibrations/{job_id}")
def calibration(job_id: UUID) -> Row:
    return calibrations.get(job_id)


@app.get("/api/v1/workspace")
def workspace() -> Row:
    sizes: dict[str, int] = {}
    for filename in ("profiles.json", "holdout-profiles.json"):
        rows = generate_rows(json.loads((ROOT / "data" / filename).read_text(encoding="utf-8")))
        for table, values in rows.items():
            sizes[table] = sizes.get(table, 0) + len(values)
    return {
        "public_demo": settings.public_demo,
        "custom_questions": not settings.public_demo,
        "run_benchmarks": not settings.public_demo,
        "live_models": not settings.public_demo or settings.public_live_daily_limit > 0,
        "dataset": {
            "name": "Northstar Shop",
            "fictional": True,
            "version": DATASET_VERSION,
            "description": "A fictional online retailer with web and mobile shopping. Every record is synthetic.",
            "tables": [
                {
                    "name": "Checkout traffic",
                    "rows": sizes["traffic_metrics"],
                    "purpose": "Daily sessions, checkout starts, and purchases.",
                },
                {
                    "name": "Payment outcomes",
                    "rows": sizes["payment_events"],
                    "purpose": "Card and wallet attempts, failures, and timeouts.",
                },
                {
                    "name": "Release history",
                    "rows": sizes["releases"],
                    "purpose": "When software changes reached shoppers.",
                },
                {
                    "name": "Feature rollouts",
                    "rows": sizes["feature_flags"],
                    "purpose": "Which checkout changes were enabled, and for whom.",
                },
                {
                    "name": "Support tickets",
                    "rows": sizes["support_tickets"],
                    "purpose": "Fictional customer complaints and category counts.",
                },
            ],
            "scenario_count": len(cases),
        },
    }


class ProviderTest(Model):
    provider: Literal["ollama", "openai", "anthropic"]


@app.post("/api/v1/connections/test")
def test_provider(payload: ProviderTest) -> ComponentStatus:
    model = settings.model_for(payload.provider)
    adapter = client_for(settings, payload.provider)
    if payload.provider == "ollama":
        return adapter.status(model)
    return adapter.status(model, probe=True)


if directory := environ.get("AGENTFLOW_STATIC_DIR"):
    static_root = Path(directory).resolve()
    app.mount("/assets", StaticFiles(directory=static_root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path.startswith(("api/", "mcp")):
            raise HTTPException(404, "Route not found.")
        return FileResponse(static_root / "index.html")
