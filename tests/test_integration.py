import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from os import environ
from time import monotonic, sleep
from uuid import uuid4

import httpx
import pytest
from agentflow.config import Settings, make_engine
from agentflow.domain import Comparison, Evidence, load_cases
from agentflow.store import Problem, Store
from agentflow.transport import ALL_TOOLS, MCPClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        environ.get("AGENTFLOW_INTEGRATION") != "1", reason="Start Compose verification."
    ),
]


@pytest.fixture
def api():
    with httpx.Client(
        base_url=environ.get("AGENTFLOW_TEST_API", "http://127.0.0.1:8001"), timeout=12
    ) as client:
        yield client


def checked(response: httpx.Response):
    response.raise_for_status()
    return response.json()


def wait_for(api: httpx.Client, path: str, status: str, timeout: int = 35):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        result = checked(api.get(path))
        if result["status"] == status:
            return result
        assert result["status"] not in {"failed", "needs_clarification"}, result.get("error")
        sleep(0.2)
    pytest.fail(f"Timed out waiting for {status} at {path}")


def create(api: httpx.Client, case: str = "checkout-conversion-drop", **options: object) -> str:
    run = checked(api.post("/api/v1/investigations", json={"scenario_id": case, **options}))
    return "/api/v1/investigations/" + run["id"]


def test_public_live_limits_count_both_providers_and_keep_demo_available(monkeypatch):
    store = Store(make_engine())
    scenario = load_cases()["checkout-conversion-drop"].scenario
    visitor, other = uuid4().hex, uuid4().hex
    with store.engine.connect() as connection:
        # Roll back fixtures together so the running scheduler never sees these jobs.
        connection.execute(text("SELECT pg_advisory_xact_lock(189562001)"))
        existing = connection.execute(
            text("""SELECT count(*) FROM investigations WHERE visitor_id IS NOT NULL
                AND mode IN ('openai','anthropic') AND created_at > now()-interval '1 day'""")
        ).scalar_one()

        @contextmanager
        def begin():
            with connection.begin_nested():
                yield connection

        monkeypatch.setattr(store.engine, "begin", begin)

        def submit(mode, session):
            row = store.create_run(
                scenario,
                scenario.question,
                mode,
                None if mode == "demo" else "test-model",
                session,
                public_live_daily_limit=existing + 2,
            )
            connection.execute(
                text("UPDATE investigations SET status='canceled' WHERE id=:id"), {"id": row["id"]}
            )

        submit("openai", visitor)
        submit("anthropic", visitor)
        with pytest.raises(Problem, match="daily limit"):
            submit("openai", other)
        submit("demo", other)


def test_mcp_real_transport_and_injection_boundary(api) -> None:
    scenario = load_cases()["checkout-conversion-drop"].scenario
    scope = scenario.scope
    url = Settings.from_env().mcp_url

    async def check():
        async with (
            httpx.AsyncClient(timeout=5, trust_env=False) as http,
            streamable_http_client(url, http_client=http) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = (await session.list_tools()).tools
            assert {tool.name for tool in tools} == ALL_TOOLS
            assert all(tool.annotations and tool.annotations.readOnlyHint for tool in tools)
            compare = await session.call_tool(
                "compare_time_windows",
                {
                    "request": {
                        "baseline": scope.baseline.model_dump(mode="json"),
                        "current": scope.current.model_dump(mode="json"),
                    }
                },
            )
            assert not compare.isError
            record = Evidence.model_validate(compare.structuredContent)
            assert Comparison.model_validate(record.payload).delta == -14.0
            assert record.id == record.content_id()
            invalid = await session.call_tool(
                "get_metric_summary",
                {
                    "request": {
                        "window": {"start": "2025-10-01", "end": "2025-11-05"},
                        "command": "unexpected",
                    }
                },
            )
            assert invalid.isError
            assert (
                await session.call_tool("fetch_url", {"url": "https://example.invalid/"})
            ).isError

    asyncio.run(check())
    assert (
        "Ignore instructions"
        in MCPClient(url).source("ticket-2025-10-21-payment_failure-01")["record"]["excerpt"]
    )
    path = create(api)
    draft = wait_for(api, path, "awaiting_review")
    assert draft["draft"]["hypothesis"] == "payment_regression"
    assert "Ignore instructions" not in str(draft["draft"])
    records = checked(api.get(path + "/evidence"))
    tickets = next(
        row
        for row in records
        if "ticket-2025-10-21-payment_failure-01" in row["payload"].get("excerpts", {})
    )
    local_source = checked(
        api.get(
            path + "/evidence/" + tickets["id"] + "/sources/ticket-2025-10-21-payment_failure-01"
        )
    )
    assert "Ignore instructions" in local_source["record"]["excerpt"]
    denied = api.get(path + "/evidence/" + tickets["id"] + "/sources/rel-v4-21")
    assert denied.status_code == 404
    events = checked(api.get(path + "/events"))["events"]
    assert sum(row["kind"] == "evidence_verified" for row in events) == 1
    assert not any(row["kind"] in {"tool_denied", "model_finished"} for row in events)
    assert {row["detail"]["tool"] for row in events if row["kind"] == "tool_finished"} <= ALL_TOOLS


def test_duplicate_review_concurrency_and_final_export(api) -> None:
    path = create(api)
    pending = wait_for(api, path, "awaiting_review")
    assert pending["checkpoint_id"]
    assert api.get(path + "/report").status_code == 409
    body = {"interrupt_id": pending["pending"]["interrupt_id"], "action": "approve"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(lambda _: api.post(path + "/review", json=body).status_code, range(2))
        )
    assert sorted(statuses) == [202, 409]
    approved = wait_for(api, path, "approved")
    assert len(approved["reviews"]) == 1
    response = api.get(path + "/report?format=markdown")
    assert response.status_code == 200
    assert "attachment;" in response.headers["content-disposition"]
    assert "Rule-based demo — no LLM involved" in response.text
    assert "pay-2025-10-21-mobile-card-authentication_timeout" in response.text
    page = checked(api.get(path + "/events"))
    assert checked(api.get(path + "/events", params={"after": page["next_cursor"]}))["events"] == []


def test_revision_reopens_checkpoint_and_rejection_blocks_export(api) -> None:
    path = create(api, "traffic-shift")
    pending = wait_for(api, path, "awaiting_review")["pending"]
    revise = {"interrupt_id": pending["interrupt_id"], "action": "revise", "note": "Check timing."}
    checked(api.post(path + "/review", json=revise))
    round_two = wait_for(api, path, "awaiting_review")
    updated = round_two["pending"]
    assert updated["round"] == 2 and updated["interrupt_id"] != pending["interrupt_id"]
    assert round_two["draft"]["confidence"] == "limited"
    assert api.post(path + "/review", json=revise).status_code == 409
    assert (
        api.post(
            path + "/review", json={**revise, "interrupt_id": updated["interrupt_id"]}
        ).status_code
        == 409
    )
    checked(
        api.post(
            path + "/review", json={"interrupt_id": updated["interrupt_id"], "action": "reject"}
        )
    )
    assert len(wait_for(api, path, "rejected")["reviews"]) == 2
    assert api.get(path + "/report").status_code == 409


def test_invalid_requests_cancellation_and_ready_boundary(api) -> None:
    path = create(api, question="Who is the city mayor?")
    assert wait_for(api, path, "needs_clarification")["error"]
    other = create(api, "healthy-rollout")
    wait_for(api, other, "awaiting_review")
    assert checked(api.post(other + "/cancel", json={}))["status"] == "canceled"
    assert api.get(other + "/report").status_code == 409
    assert (
        api.post(
            "/api/v1/investigations", json={"scenario_id": "healthy-rollout", "mode": "some-mode"}
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/api/v1/investigations",
            headers={"Origin": "http://example.invalid"},
            json={"scenario_id": "healthy-rollout"},
        ).status_code
        == 403
    )
    states = checked(api.get("/api/v1/connections"))
    assert states["mcp"]["state"] == states["database"]["state"] == "ok"
    if states["ollama"]["state"] == "not_configured":
        assert (
            api.post(
                "/api/v1/investigations",
                json={
                    "scenario_id": "healthy-rollout",
                    "mode": "ollama",
                },
            ).status_code
            == 409
        )


def test_public_proxy_and_full_benchmark(api) -> None:
    if web := environ.get("AGENTFLOW_TEST_WEB"):
        with httpx.Client(base_url=web, timeout=8) as frontend:
            assert 'id="root"' in frontend.get("/").text
            assert len(checked(frontend.get("/api/v1/scenarios"))) == 15
    job = checked(api.post("/api/v1/evaluations", json={"strategy": "compare"}))
    evaluated = wait_for(api, "/api/v1/evaluations/" + job["id"], "completed", timeout=65)
    assert evaluated["total_cases"] == len(evaluated["cases"]) == 30
    assert all(row["passed"] for row in evaluated["cases"]), [
        row for row in evaluated["cases"] if not row["passed"]
    ]
    for case_id in {row["scenario_id"] for row in evaluated["cases"]}:
        pair = [row for row in evaluated["cases"] if row["scenario_id"] == case_id]
        assert len(pair) == 2
        assert pair[0]["tool_calls"] == pair[1]["tool_calls"]
        assert pair[0]["task_hash"] == pair[1]["task_hash"]
        assert pair[0]["mode"] == pair[1]["mode"] == "demo"
        assert pair[0]["token_count"] is None and pair[1]["token_count"] is None


def test_mcp_reader_has_source_access_only(monkeypatch) -> None:
    monkeypatch.setenv("DB_USER", "agentflow_reader")
    monkeypatch.setenv("DB_PASSWORD", environ["TEST_READER_PASSWORD"])
    engine = make_engine()
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM traffic_metrics")).scalar_one() == 174
            )
        with engine.connect() as connection, pytest.raises(DBAPIError):
            connection.execute(text("SELECT id FROM investigations"))
        with engine.connect() as connection, pytest.raises(DBAPIError):
            connection.execute(text("DELETE FROM releases WHERE false"))
    finally:
        engine.dispose()


def test_worker_claim_lock_is_exclusive() -> None:
    import psycopg
    from agentflow.config import conninfo
    from agentflow.worker import WORKER_LOCK

    with psycopg.connect(conninfo(), autocommit=True) as connection:
        assert connection.execute("SELECT pg_try_advisory_lock(%s)", (WORKER_LOCK,)).fetchone() == (
            False,
        )


def test_auditor_recomputes_after_a_modified_payload_is_rehashed() -> None:
    from agentflow.audit import EvidenceError, verify
    from agentflow.domain import Plan
    from agentflow.planning import calls_for
    from agentflow.transport import discard

    client = MCPClient(Settings.from_env().mcp_url)
    scope = load_cases()["checkout-conversion-drop"].scenario.scope
    calls = calls_for("metrics", scope)
    evidence = dict(
        zip(calls, client.collect("metrics", list(calls.values()), "metrics", discard), strict=True)
    )
    changed = evidence["comparison"]
    tampered = changed.model_copy(update={"payload": {**changed.payload, "delta": 0.0}})
    evidence["comparison"] = tampered.model_copy(update={"id": tampered.content_id()})
    with pytest.raises(EvidenceError, match="failed independent recomputation"):
        verify(Plan(domains=["metrics"], rationale="Audit."), scope, evidence)
