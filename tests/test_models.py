import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import httpx
from agentflow.config import Settings
from agentflow.domain import load_cases
from agentflow.judge import score
from agentflow.models import LangSmithExport, OllamaClient, RouteChoice
from agentflow.transport import discard


def test_ollama_adapter_retries_invalid_schema_and_tracks_measured_usage(monkeypatch) -> None:
    seen: list[str] = []
    events: list[tuple[str, dict[str, Any]]] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["stream"] is False
        assert body["options"]["num_predict"] > 0
        assert "domains" in body["format"]["properties"]
        seen.append(request.url.path)
        value = '{"domains":["unknown"]}' if len(seen) == 1 else '{"domains":["support"]}'
        return httpx.Response(
            200, json={"message": {"content": value}, "eval_count": 7, "prompt_eval_count": 40}
        )

    client = OllamaClient(Settings.from_env())
    monkeypatch.setattr(
        client,
        "_client",
        lambda _: httpx.Client(
            base_url="http://127.0.0.1:11434",
            transport=httpx.MockTransport(upstream),
        ),
    )
    scenario = load_cases()["support-only"].scenario
    result = client.generate(
        RouteChoice,
        "local-model",
        "planner",
        "Route the request.",
        {"question": scenario.question},
        lambda _, kind, data: events.append((kind, data)),
    )
    assert result.domains == ["support"]
    assert len(seen) == 2
    assert [kind for kind, _ in events] == ["model_failed", "model_retry", "model_finished"]
    assert events[-1][1]["eval_count"] == 7


def test_judge_references_are_constrained_by_the_supplied_evidence(monkeypatch) -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["format"]["properties"]["evidence_ids"]["items"]["enum"] == ["ref-funnel"]
        verdict = {
            "scores": {"groundedness": 4, "completeness": 3, "clarity": 5},
            "rationale": "The denominator is visible.",
            "evidence_ids": ["ref-funnel"],
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(verdict)}})

    client = OllamaClient(Settings.from_env())
    monkeypatch.setattr(
        client,
        "_client",
        lambda _: httpx.Client(
            base_url="http://127.0.0.1:11434",
            transport=httpx.MockTransport(upstream),
        ),
    )
    result = score(client, "local-model", "Conversion fell.", {"ref-funnel": "80% to 70%"})
    assert result.evidence_ids == ["ref-funnel"]
    assert result.scores.groundedness == 4


def test_langsmith_opt_in_sends_metadata_only(monkeypatch) -> None:
    from agentflow import models

    deliveries: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        def create_run(self, *args: Any, **kwargs: Any) -> None:
            deliveries.append((args, kwargs))

    monkeypatch.setattr(models, "Client", FakeClient)
    start = datetime.now(UTC)
    disabled = replace(
        Settings.from_env(), langsmith_enabled=False, langsmith_key="local-test-placeholder"
    )
    LangSmithExport(disabled).send("agentflow.investigation", start, {"mode": "demo"}, discard)
    assert not deliveries
    enabled = replace(disabled, langsmith_enabled=True)
    LangSmithExport(enabled).send("agentflow.investigation", start, {"mode": "demo"}, discard)
    args, kwargs = deliveries[0]
    assert args[1] == kwargs["outputs"] == {}
    assert kwargs["extra"] == {"metadata": {"mode": "demo"}}


def test_inline_schema_preserves_required_title_fields_in_nested_assessments():
    from agentflow.models import inline_schema
    from agentflow.reasoning import Narrative

    flat = inline_schema(Narrative.model_json_schema())
    explanation = flat["properties"]["explanations"]["items"]
    assert explanation["properties"]["title"]["type"] == "string"
    assert "title" in explanation["required"]
    assert "$ref" not in json.dumps(flat)
