import json
from contextlib import contextmanager
from dataclasses import replace
from os import environ

import httpx
import pytest
from agentflow.advisor import ModelAdvisor
from agentflow.benchmark import Benchmarks
from agentflow.config import Settings, make_engine
from agentflow.domain import Report, load_cases
from agentflow.judge import Calibrations
from agentflow.models import LangSmithExport, ModelFailure, OllamaClient
from agentflow.providers import HostedClient
from agentflow.reasoning import Narrative, apply_narrative
from agentflow.store import Store
from agentflow.transport import MCPClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from sqlalchemy import text

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        environ.get("AGENTFLOW_INTEGRATION") != "1", reason="Requires the running MCP service."
    ),
]


@pytest.mark.parametrize(
    ("provider", "model", "strategy"),
    [
        ("openai", "gpt-6-luna", "multi"),
        ("anthropic", "claude-haiku-5-5", "single"),
    ],
)
def test_hosted_investigation_survives_rejected_followup_and_revises_over_real_mcp(
    monkeypatch, provider, model, strategy
):
    from agentflow.workflow import build_graph

    settings = replace(
        Settings.from_env(), openai_key="test-placeholder", anthropic_key="test-placeholder"
    )
    case = load_cases()["checkout-conversion-drop"]
    events = []
    revisions = []

    def emit(node, kind, data):
        events.append((node, kind, data))

    def upstream(request):
        body = json.loads(request.content)
        if provider == "openai":
            spec = body["response_format"]["json_schema"]
            name, schema = spec["name"], spec["schema"]
            supplied = json.loads(body["messages"][1]["content"])
        else:
            assert "tools" not in body and body["thinking"] == {"type": "disabled"}
            assert body["output_config"]["format"]["type"] == "json_schema"
            schema = body["output_config"]["format"]["schema"]
            name = schema["title"]
            supplied = json.loads(body["messages"][0]["content"])
        if name == "RouteChoice":
            value = {"domains": ["metrics", "timeline", "support"]}
        elif name == "SpecialistAssessment":
            observation = schema["properties"]["observation"]
            if provider == "openai":
                assert observation["pattern"] == "^[^0-9]*$"
            else:
                assert "pattern" not in observation and "minLength" not in observation
                assert "Do not include digits" in observation["description"]
            domain = supplied["domain"]
            focus = {"metrics": "comparison", "timeline": "releases", "support": "tickets_current"}[
                domain
            ]
            options = supplied["follow_up_options"]
            value = {
                "focus": focus,
                "observation": "The available records show an operational change.",
                "alternative": "Exposure differences and reporting changes could also explain the signal.",
                "follow_up": next(iter(options), "none"),
            }
            if domain == "metrics" and not options:
                # Reproduce the failure after a successful initial assessment and tool read.
                value["observation"] = "Checkout conversion shifted by 13.9 percentage points."
        elif name == "Judgment":
            value = {
                "scores": {"groundedness": 4, "completeness": 3, "clarity": 5},
                "rationale": "The cited checkout evidence supports the cautious interpretation.",
                "evidence_ids": list(supplied["evidence"])[:1],
            }
        else:
            assert name == "Narrative"
            if provider == "anthropic":
                expectations = schema["properties"]["explanations"]
                assert "maxItems" not in expectations and "minItems" not in expectations
                assert "Return exactly 2 items." in expectations["description"]
                explanation = schema["$defs"]["Explanation"]["properties"]
                assert explanation["supporting_evidence"]["items"]["enum"]
            assert any(key.startswith("followup_") for key in supplied["evidence"])
            observations = supplied["verified_observations"]
            ids = list(dict.fromkeys(ref for item in observations for ref in item["evidence_ids"]))
            assert "excerpts" not in str(supplied) and "Ignore instructions" not in str(supplied)
            assert "13.9 percentage points" not in str(supplied)
            revisions.append(supplied["reviewer_feedback"])
            value = {
                "explanations": [
                    {
                        "hypothesis": "payment_regression",
                        "title": "Payment failures are the leading explanation",
                        "assessment": "Authentication failures align with the checkout decline.",
                        "supporting_evidence": ids[:2],
                        "contradicting_evidence": [],
                        "uncertainty": "Shopper exposure is required to establish the relationship.",
                    },
                    {
                        "hypothesis": "mix_shift",
                        "title": "A different shopper mix remains possible",
                        "assessment": "Different cohorts may have different purchase intent.",
                        "supporting_evidence": ids[:1],
                        "contradicting_evidence": ids[1:2],
                        "uncertainty": "Compare matched cohorts to assess this explanation.",
                    },
                ],
                "confidence": "moderate",
                "next_actions": ["Compare flag exposure across shoppers."],
                "unresolved_questions": ["Do failures concentrate among exposed shoppers?"],
            }
            if provider == "anthropic" and len(revisions) == 1:
                value["explanations"][0]["uncertainty"] = "The timing does not prove causality."
        result = (
            {
                "choices": [{"message": {"content": json.dumps(value)}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 60},
            }
            if provider == "openai"
            else {
                "content": [{"type": "text", "text": json.dumps(value)}],
                "usage": {"input_tokens": 120, "output_tokens": 60},
            }
        )
        return httpx.Response(200, json=result)

    monkeypatch.setattr(
        HostedClient,
        "_client",
        lambda self, timeout: httpx.Client(
            base_url="https://api.openai.com"
            if provider == "openai"
            else "https://api.anthropic.com",
            transport=httpx.MockTransport(upstream),
        ),
    )
    config = {"configurable": {"thread_id": "hosted-model-transport-test"}}
    graph = build_graph(
        MCPClient(settings.mcp_url),
        InMemorySaver(),
        emit,
        ModelAdvisor(settings, provider, model, emit),
    )
    graph.invoke(
        {
            "scenario": case.scenario.model_dump(mode="json"),
            "question": case.scenario.question,
            "mode": provider,
            "model": model,
            "strategy": strategy,
            "review_round": 1,
        },
        config,
    )
    state = graph.get_state(config)
    assert len(state.interrupts) == 1
    report = Report.model_validate(state.values["draft"])
    assert report.analysis_source == "model" and len(report.explanations) == 2
    assert report.comparison.delta == -14.0
    assert sum(kind == "followup_selected" for _, kind, _ in events) == 3
    assert sum(kind == "tool_finished" for _, kind, _ in events) == 12
    assert sum(kind == "evidence_verified" for _, kind, _ in events) == 1
    skips = [data for _, kind, data in events if kind == "specialist_output_skipped"]
    assert len(skips) == 1 and skips[0]["followup"]
    assert sum(kind == "model_failed" for _, kind, _ in events) == 2 + (provider == "anthropic")
    tampered = Narrative.model_validate(
        {
            "explanations": report.explanations,
            "confidence": "moderate",
            "next_actions": ["Review the payment logs."],
            "unresolved_questions": ["Which shoppers were exposed?"],
        }
    )
    with pytest.raises(ModelFailure):
        apply_narrative(report, tampered, {})
    gate = state.interrupts[0]
    note = "Reconsider the timing of the change."
    graph.invoke(
        Command(resume={"interrupt_id": gate.id, "round": 1, "action": "revise", "note": note}),
        config,
    )
    revised = graph.get_state(config)
    assert revisions == (["", note] if provider == "openai" else ["", "", note])
    assert revised.values["draft"]["review_round"] == 2
    assert revised.values["draft"]["analysis_source"] == "model"
    graph.invoke(
        Command(
            resume={
                "interrupt_id": revised.interrupts[0].id,
                "round": 2,
                "action": "approve",
                "note": "",
            }
        ),
        config,
    )
    assert graph.get_state(config).values["result"] == "approved"

    store = Store(make_engine())
    ollama = OllamaClient(settings)
    benchmark = Benchmarks(
        store,
        MCPClient(settings.mcp_url),
        {case.scenario.id: case},
        ollama,
        LangSmithExport(settings),
    )
    calibrations = Calibrations(store, ollama)
    with store.engine.connect() as connection:
        # The scheduler on the main API cannot see these test jobs, which are rolled back.
        transaction = connection.begin()

        @contextmanager
        def read():
            yield connection

        @contextmanager
        def write():
            with connection.begin_nested():
                yield connection

        monkeypatch.setattr(store.engine, "connect", read)
        monkeypatch.setattr(store.engine, "begin", write)
        job_id = benchmark.create(strategy, provider, model, model, provider)
        job = benchmark.get(job_id)
        assert job["judge_provider"] == provider
        result = benchmark.run_case(job, case, strategy)
        assert result["passed"], result
        assert result["judge"]["provider"] == provider
        assert result["judge"]["judgment"]["scores"] == {
            "groundedness": 4,
            "completeness": 3,
            "clarity": 5,
        }
        calibration_id = calibrations.create(model, provider)
        connection.execute(
            text("UPDATE calibrations SET created_at='2000-01-01T00:00:00Z' WHERE id=:id"),
            {"id": calibration_id},
        )
        assert calibrations.step()
        calibration = calibrations.get(calibration_id)
        assert calibration["provider"] == provider
        assert calibration["cases"][0]["judgment"]["scores"]["groundedness"] == 4
        transaction.rollback()
