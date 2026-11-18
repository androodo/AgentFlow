from agentflow.config import Settings
from agentflow.domain import DOMAINS, Domain, Evidence, Plan, Report, Scenario, Scope
from agentflow.followups import options_for
from agentflow.models import SYSTEMS, RouteChoice
from agentflow.planning import CLARIFICATION, RATIONALES
from agentflow.providers import client_for
from agentflow.reasoning import (
    Narrative,
    SpecialistAssessment,
    apply_narrative,
    narrative_valid,
    numbers_grounded,
    projection,
    prose_valid,
)
from agentflow.transport import Emit


class ModelAdvisor:
    def __init__(self, settings: Settings, provider: str, model: str, emit: Emit) -> None:
        self.client = client_for(settings, provider)
        self.model, self.emit = model, emit

    def plan(self, question: str, scenario: Scenario) -> Plan:
        route = self.client.generate(
            RouteChoice,
            self.model,
            "planner",
            SYSTEMS["planner"],
            {"question": question, "scope": scenario.scope.model_dump(mode="json")},
            self.emit,
            valid=lambda value: len(set(value.domains)) == len(value.domains),
        )
        domains = [domain for domain in DOMAINS if domain in route.domains]
        return Plan(
            domains=domains,
            rationale=" ".join(RATIONALES[domain] for domain in domains),
            clarification=CLARIFICATION if not domains else None,
        )

    def inspect(
        self,
        domain: Domain,
        evidence: dict[str, Evidence],
        scope: Scope,
        *,
        final: bool = False,
    ) -> SpecialistAssessment:
        options = {} if final else options_for(domain, scope)
        return self.client.generate(
            SpecialistAssessment,
            self.model,
            domain,
            SYSTEMS["specialist"],
            {"domain": domain, "evidence": projection(evidence), "follow_up_options": options},
            self.emit,
            constraints={
                "focus": {"enum": sorted(evidence)},
                "follow_up": {"enum": ["none", *options]},
            },
            valid=lambda value: (
                value.focus in evidence
                and value.follow_up in ("none", *options)
                and prose_valid(value.observation)
                and numbers_grounded(value.observation, evidence)
                and prose_valid(value.alternative)
                and numbers_grounded(value.alternative, evidence)
            ),
        )

    def edit(
        self,
        report: Report,
        evidence: dict[str, Evidence],
        focus: list[dict],
        question: str,
        revision_note: str,
    ) -> Report:
        observations = [
            item.model_dump(mode="json") for item in report.findings if item.kind == "observation"
        ]
        narrative = self.client.generate(
            Narrative,
            self.model,
            "report",
            SYSTEMS["report"],
            {
                "question": question,
                "verified_observations": observations,
                "evidence": projection(evidence),
                "specialist_assessments": focus,
                "reviewer_feedback": revision_note,
            },
            self.emit,
            constraints={
                "$defs.Explanation.properties.supporting_evidence.items": {
                    "enum": sorted(row.id for row in evidence.values())
                },
                "$defs.Explanation.properties.contradicting_evidence.items": {
                    "enum": sorted(row.id for row in evidence.values())
                },
            },
            valid=lambda value: narrative_valid(value, evidence),
        )
        return apply_narrative(report, narrative, evidence)
