from collections.abc import Callable
from functools import wraps
from time import perf_counter
from typing import Annotated, Any, Protocol, TypedDict

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from agentflow.audit import verify
from agentflow.domain import Decision, Domain, Evidence, Mode, Plan, Report, Scenario, Strategy
from agentflow.followups import followup_call
from agentflow.models import ModelOutputFailure
from agentflow.planning import calls_for, rule_plan
from agentflow.reasoning import SpecialistAssessment
from agentflow.reporting import compose, verify_citations
from agentflow.transport import Emit, MCPClient

Payload = dict[str, Any]


def merge_parallel(left: dict[str, Payload], right: dict[str, Payload]) -> dict[str, Payload]:
    # Parallel specialists own distinct evidence keys; never replace the whole map.
    return left | right


class Flow(TypedDict, total=False):
    scenario: Payload
    question: str
    mode: Mode
    model: str | None
    strategy: Strategy
    plan: Payload
    evidence: Annotated[dict[str, Payload], merge_parallel]
    focus: Annotated[dict[str, Payload], merge_parallel]
    draft: Payload
    review_round: int
    last_review: Payload
    result: str


class Advisor(Protocol):
    def plan(self, question: str, scenario: Scenario) -> Plan: ...
    def inspect(
        self, domain: Domain, evidence: dict[str, Evidence], scope, *, final: bool = False
    ) -> SpecialistAssessment: ...
    def edit(
        self,
        report: Report,
        evidence: dict[str, Evidence],
        focus: list[dict],
        question: str,
        revision_note: str,
    ) -> Report: ...


def build_graph(
    client: MCPClient,
    checkpointer: BaseCheckpointSaver,
    emit: Emit,
    advisor: Advisor | None = None,
) -> CompiledStateGraph:
    def tracked(name: str, fn: Callable[[Flow], Flow]) -> Callable[[Flow], Flow]:
        @wraps(fn)
        def invoke(state: Flow) -> Flow:
            start = perf_counter()
            emit(name, "node_started", {})
            try:
                update = fn(state)
            except Exception as exc:
                emit(
                    name,
                    "node_failed",
                    {
                        "error_type": type(exc).__name__,
                        "duration_ms": round((perf_counter() - start) * 1000, 1),
                    },
                )
                raise
            emit(name, "node_finished", {"duration_ms": round((perf_counter() - start) * 1000, 1)})
            return update

        return invoke

    def plan(state: Flow) -> Flow:
        scenario = Scenario.model_validate(state["scenario"])
        result = (
            advisor.plan(state["question"], scenario) if advisor else rule_plan(state["question"])
        )
        emit(
            "planner",
            "plan_selected",
            {
                "domains": result.domains,
                "rationale": result.rationale,
                "clarification": result.clarification,
            },
        )
        return {"plan": result.model_dump(mode="json")}

    def after_plan(state: Flow) -> list[str]:
        result = Plan.model_validate(state["plan"])
        if not result.domains:
            return [END]
        return ["single"] if state["strategy"] == "single" else list(result.domains)

    def gather(state: Flow, domain: Domain, node: str) -> Flow:
        scenario = Scenario.model_validate(state["scenario"])
        requests = calls_for(domain, scenario.scope)
        found = client.collect(domain, list(requests.values()), node, emit)
        records = dict(zip(requests, found, strict=True))
        focus = {}
        if advisor:

            def inspect(*, final: bool = False) -> SpecialistAssessment | None:
                try:
                    return advisor.inspect(domain, records, scenario.scope, final=final)
                except ModelOutputFailure:
                    # Keep the verified source records. Never pass rejected prose to the composer.
                    emit(
                        node,
                        "specialist_output_skipped",
                        {
                            "reason": "The specialist assessment could not be validated.",
                            "followup": final,
                        },
                    )
                    return None

            assessment = inspect()
            # The model selects a recipe label; Python owns its tool, scope, and call budget.
            if assessment and assessment.follow_up != "none":
                key, call = followup_call(domain, assessment.follow_up, scenario.scope)
                emit(
                    node,
                    "followup_selected",
                    {"recipe": assessment.follow_up, "reason": assessment.alternative},
                )
                records[key] = client.collect(domain, [call], node, emit)[0]
                assessment = inspect(final=True) or assessment
            if assessment:
                focus = {
                    **assessment.model_dump(mode="json"),
                    "evidence_id": records[assessment.focus].id,
                }
                emit(node, "specialist_focus", focus)
        update: Flow = {
            "evidence": {key: value.model_dump(mode="json") for key, value in records.items()}
        }
        if focus:
            update["focus"] = {domain: focus}
        return update

    def specialist(domain: Domain) -> Callable[[Flow], Flow]:
        def work(state: Flow) -> Flow:
            return gather(state, domain, domain)

        return work

    def single(state: Flow) -> Flow:
        evidence: dict[str, Payload] = {}
        focus: dict[str, Payload] = {}
        for domain in Plan.model_validate(state["plan"]).domains:
            update = gather(state, domain, "single")
            evidence.update(update["evidence"])
            focus.update(update.get("focus", {}))
        return {"evidence": evidence, "focus": focus}

    def evidence_of(state: Flow) -> dict[str, Evidence]:
        return {key: Evidence.model_validate(value) for key, value in state["evidence"].items()}

    def audit(state: Flow) -> Flow:
        evidence = evidence_of(state)
        plan_data = Plan.model_validate(state["plan"])
        scenario = Scenario.model_validate(state["scenario"])
        verify(plan_data, scenario.scope, evidence)
        emit("audit", "evidence_verified", {"records": len(evidence), "domains": plan_data.domains})
        return {}

    def report(state: Flow) -> Flow:
        evidence = evidence_of(state)
        draft = compose(
            Scenario.model_validate(state["scenario"]),
            state["mode"],
            state.get("model"),
            evidence,
            state["review_round"],
            state.get("last_review", {}).get("note", ""),
        )
        if advisor:
            draft = advisor.edit(
                draft,
                evidence,
                list(state.get("focus", {}).values()),
                state["question"],
                state.get("last_review", {}).get("note", ""),
            )
        verify_citations(draft, evidence)
        return {"draft": draft.model_dump(mode="json")}

    def review(state: Flow) -> Flow:
        # This function restarts on Command(resume=...). Keep it free of side effects.
        decision = Decision.model_validate(
            interrupt({"round": state["review_round"], "kind": "human_review"})
        )
        if decision.round != state["review_round"]:
            raise ValueError("Decision does not match the active review round.")
        outcomes = {"approve": "approved", "reject": "rejected", "revise": "revision"}
        return {
            "last_review": decision.model_dump(mode="json"),
            "result": outcomes[decision.action],
        }

    def after_review(state: Flow) -> str:
        return "revision" if state["result"] == "revision" else END

    def revision(state: Flow) -> Flow:
        if state["review_round"] >= 2:
            raise ValueError("The investigation already used its revision.")
        return {"review_round": state["review_round"] + 1, "result": ""}

    graph = StateGraph(Flow)
    graph.add_node("planner", RunnableLambda(tracked("planner", plan)))
    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner", after_plan, ["metrics", "timeline", "support", "single", END]
    )
    for domain in ("metrics", "timeline", "support"):
        graph.add_node(domain, RunnableLambda(tracked(domain, specialist(domain))))
        graph.add_edge(domain, "audit")
    graph.add_node("single", RunnableLambda(tracked("single", single)))
    graph.add_edge("single", "audit")
    graph.add_node("audit", RunnableLambda(tracked("audit", audit)))
    graph.add_node("report", RunnableLambda(tracked("report", report)))
    graph.add_node("review", RunnableLambda(review))
    graph.add_node("revision", RunnableLambda(tracked("revision", revision)))
    graph.add_edge("audit", "report")
    graph.add_edge("report", "review")
    graph.add_conditional_edges("review", after_review, ["revision", END])
    graph.add_edge("revision", "audit")
    return graph.compile(checkpointer=checkpointer)
