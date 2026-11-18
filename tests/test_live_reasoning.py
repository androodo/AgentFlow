import json
from dataclasses import replace
from os import environ

import httpx
import pytest
from agentflow.advisor import ModelAdvisor
from agentflow.config import Settings
from agentflow.domain import Report, load_cases
from agentflow.models import ModelFailure
from agentflow.providers import HostedClient
from agentflow.reasoning import Narrative, apply_narrative
from agentflow.transport import MCPClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        environ.get("AGENTFLOW_INTEGRATION") != "1", reason="Requires the running MCP service."
    ),
]


def test_model_assessments_choose_followups_and_compose_alternatives_over_real_mcp(monkeypatch):
    from agentflow.workflow import build_graph

    settings = replace(
        Settings.from_env(), openai_key="test-placeholder", openai_model="test-model"
    )
    case = load_cases()["checkout-conversion-drop"]
    events = []

    def emit(node, kind, data):
        events.append((node, kind, data))

    def upstream(request):
        body = json.loads(request.content)
        name = body["response_format"]["json_schema"]["name"]
        supplied = json.loads(body["messages"][1]["content"])
        if name == "RouteChoice":
            value = {"domains": ["metrics", "timeline", "support"]}
        elif name == "SpecialistAssessment":
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
        else:
            assert name == "Narrative"
            observations = supplied["verified_observations"]
            ids = list(dict.fromkeys(ref for item in observations for ref in item["evidence_ids"]))
            assert "excerpts" not in str(supplied) and "Ignore instructions" not in str(supplied)
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
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(value)}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 60},
            },
        )

    monkeypatch.setattr(
        HostedClient,
        "_client",
        lambda self, timeout: httpx.Client(
            base_url="https://api.openai.com", transport=httpx.MockTransport(upstream)
        ),
    )
    config = {"configurable": {"thread_id": "hosted-model-transport-test"}}
    graph = build_graph(
        MCPClient(settings.mcp_url),
        InMemorySaver(),
        emit,
        ModelAdvisor(settings, "openai", "test-model", emit),
    )
    graph.invoke(
        {
            "scenario": case.scenario.model_dump(mode="json"),
            "question": case.scenario.question,
            "mode": "openai",
            "model": "test-model",
            "strategy": "multi",
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
    tampered = Narrative.model_validate(
        {
            "explanations": report.explanations,
            "confidence": "moderate",
            "next_actions": ["Invent 999999 dollars saved."],
            "unresolved_questions": ["Which shoppers were exposed?"],
        }
    )
    with pytest.raises(ModelFailure):
        apply_narrative(report, tampered, {})
    gate = state.interrupts[0]
    graph.invoke(
        Command(resume={"interrupt_id": gate.id, "round": 1, "action": "approve", "note": ""}),
        config,
    )
    assert graph.get_state(config).values["result"] == "approved"
