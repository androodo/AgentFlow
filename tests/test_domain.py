import json
from datetime import date

import pytest
from agentflow.audit import EvidenceError, verify
from agentflow.bootstrap import generate_rows
from agentflow.calculations import compare_traffic, percentage
from agentflow.config import ROOT, Settings
from agentflow.domain import (
    CompareRequest,
    MetricRequest,
    Plan,
    TrafficRow,
    TrafficSummary,
    Window,
    load_cases,
)
from agentflow.planning import rule_plan
from agentflow.source_data import evidence
from agentflow.transport import Call, MCPClient, ToolContractError, ToolUnavailable, discard
from pydantic import ValidationError


def test_fixture_repeatability_and_reference_case_versions() -> None:
    profiles = json.loads((ROOT / "data" / "profiles.json").read_text())
    rows = generate_rows(profiles)
    assert rows == generate_rows(profiles)
    assert {table: len(items) for table, items in rows.items()} == {
        "releases": 11,
        "feature_flags": 6,
        "traffic_metrics": 138,
        "payment_events": 516,
        "support_tickets": 141,
    }
    cases = load_cases()
    assert len(cases) == 15
    assert sum(entry.scenario.suite == "holdout" for entry in cases.values()) == 3
    assert len({entry.scenario.task_hash for entry in cases.values()}) == 15
    for entry in cases.values():
        assert set(rule_plan(entry.scenario.question).domains) == set(entry.domains)


def test_rate_and_coverage_depend_on_actual_counts() -> None:
    before = [
        TrafficRow(
            day=date(2025, 10, 20), segment="mobile", sessions=10, checkout_starts=10, purchases=7
        )
    ]
    after = [
        TrafficRow(
            day=date(2025, 10, 21), segment="mobile", sessions=12, checkout_starts=12, purchases=8
        )
    ]
    request = CompareRequest(
        baseline=Window(start=before[0].day, end=before[0].day),
        current=Window(start=after[0].day, end=after[0].day),
        segment="mobile",
    )
    assert compare_traffic(before, after, request).delta == -3.3333
    assert compare_traffic(before, [], request).delta is None
    assert (
        compare_traffic(before, after, request.model_copy(update={"segment": "all"})).delta is None
    )
    assert percentage(0, 0) is None
    assert percentage(0, 8) == 0


@pytest.mark.parametrize(
    "start,end",
    [
        ("2025-10-20", "2025-10-19"),
        ("2025-10-19", "2025-11-05"),
        ("2025-01-01", "2025-01-02"),
    ],
)
def test_bounded_window(start: str, end: str) -> None:
    with pytest.raises(ValidationError):
        Window.model_validate({"start": start, "end": end})


def test_tool_registry_refuses_arbitrary_names_and_retries_transport_once() -> None:
    client = MCPClient("http://127.0.0.1:1/mcp")
    case = load_cases()["checkout-conversion-drop"].scenario
    request = MetricRequest(window=case.scope.current)
    with pytest.raises(ToolContractError, match="allowlist"):
        client.collect("support", [Call("fetch_url", request)], "support", discard)
    events: list[str] = []
    with pytest.raises(ToolUnavailable, match="unavailable"):
        client.collect(
            "metrics",
            [Call("get_metric_summary", request)],
            "metrics",
            lambda _, kind, __: events.append(kind),
        )
    assert events.count("tool_retry") == 1


def test_hash_and_provenance_prevent_unreviewed_evidence() -> None:
    scenario = load_cases()["checkout-conversion-drop"].scenario
    request = MetricRequest(window=scenario.scope.current)
    payload = TrafficSummary.model_validate(
        {
            "totals": {
                "sessions": 900,
                "checkout_starts": 100,
                "purchases": 90,
                "conversion_pct": 90,
                "observed_days": 3,
                "complete": True,
            },
            "rows": [],
        }
    )
    bad = evidence("get_metric_summary", request, [], payload)
    assert bad.id == bad.content_id()
    with pytest.raises(EvidenceError, match="missing or outside"):
        verify(Plan(domains=["metrics"], rationale="Compare."), scenario.scope, {"unexpected": bad})
    assert rule_plan("Who is the city mayor?").clarification
    assert not Settings.from_env().judge_model or Settings.from_env().ollama_url
